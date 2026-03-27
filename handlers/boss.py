"""Boss-only handlers: task creation, history, room management."""
import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import config
from database import get_async_session_maker, init_db
from database.models import Room, Task, Template
from states import BossStates
from keyboards.inline import (
    main_menu_kb,
    choose_employee_kb,
    send_clear_back_kb,
    back_kb,
    history_back_kb,
    room_management_kb,
    after_send_kb,
    history_detail_back_kb,
)
from utils.helpers import format_area, format_employee_name, format_date_group, CLEANING_TYPES, format_cleaning_type, safe_answer
from utils.room_linen_config import (
    AUTO_LINEN_BY_LAYOUT_ROOMS,
    JOINED_DOUBLE_KIT,
    LINEN_COLOR_MAX_BEDS,
    LINEN_VARIANT_SHORT,
    SEPARATED_15_FULL,
    build_color_variant_full_kit,
    cleaning_needs_linen_flow,
    describe_queue_item_extra,
    format_bed_layout_label,
    format_linen_lines,
    room_key_from_name,
    room_needs_bed_layout,
    room_needs_color_linen,
    scale_linen_kit,
)

router = Router()

# Только начальник (BOSS_ID) может использовать бота
router.message.filter(lambda msg: msg.from_user is not None and msg.from_user.id == config.BOSS_ID)
router.callback_query.filter(lambda cq: cq.from_user is not None and cq.from_user.id == config.BOSS_ID)


# --- Main menu text ---
def main_menu_text() -> str:
    return (
        f"👋 Здравствуйте, {config.BOSS_NAME}!\n\n"
        "Выберите действие:"
    )


# --- Choosing rooms screen (text + keyboards built from state) ---
async def build_rooms_screen(
    session: AsyncSession,
    employee_key: str,
    selected_rooms: list,
    comment: str | None,
) -> tuple[str, object]:
    """Returns (text, reply_markup). reply_markup is combined: queue + rooms grid + send/clear/back."""
    from aiogram.types import InlineKeyboardMarkup
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton

    current_total = sum(r["area"] for r in selected_rooms)
    limit = config.AREA_LIMIT
    emp_name = format_employee_name(employee_key)

    lines = [
        f"👤 Задание для: {emp_name}",
        f"🏠 Лимит: {format_area(current_total)} / {format_area(limit)} м²",
        "",
        "🏠 ДОСТУПНЫЕ ПОМЕЩЕНИЯ:",
    ]

    result = await session.execute(select(Room).where(Room.is_active == True).order_by(Room.name))
    rooms = list(result.scalars().all())
    selected_ids = {r["id"] for r in selected_rooms}

    # Table header
    lines.append("Помещение\tПлощадь")
    for r in rooms:
        lines.append(f"{r.name}\t{format_area(r.area)}")

    lines.append("")
    lines.append("📋 ОЧЕРЕДЬ УБОРКИ:")
    if not selected_rooms:
        lines.append("(пока пусто)")
    else:
        for i, r in enumerate(selected_rooms, 1):
            ct = format_cleaning_type(r.get("cleaning_type", "current"))
            extra = describe_queue_item_extra(r)
            lines.append(f"{i}. {r['name']} — {format_area(r['area'])} м² ({ct}){extra}")

    text = "\n".join(lines)

    # Клавиатура: по одной строке на каждый элемент очереди — только ⬆️ ⬇️ ❌ и смена типа
    builder = InlineKeyboardBuilder()
    for i, item in enumerate(selected_rooms):
        ct = item.get("cleaning_type", "current")
        row = [
            InlineKeyboardButton(text="⬆️", callback_data=f"qup_{i}"),
            InlineKeyboardButton(text="⬇️", callback_data=f"qdown_{i}"),
            InlineKeyboardButton(text="🔄 " + format_cleaning_type(ct)[:8], callback_data=f"ct_{i}"),
            InlineKeyboardButton(text="❌", callback_data=f"qdel_{i}"),
        ]
        builder.row(*row)

    # Room buttons — все помещения можно добавить (лимит можно превышать)
    for r in rooms:
        if not r.is_active:
            continue
        suffix = " ✓" if r.id in selected_ids else ""
        btn_text = f"{r.name} ({r.area:.2f}){suffix}"[:64]
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"room_add_{r.id}"))

    builder.row(
        InlineKeyboardButton(text="✅ ОТПРАВИТЬ ЗАДАНИЕ", callback_data="send_task"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data="add_comment"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ ОЧИСТИТЬ ВСЁ", callback_data="clear_queue"),
        InlineKeyboardButton(text="🔙 ДРУГОЙ СОТРУДНИК", callback_data="change_employee"),
    )

    return text, builder.as_markup()


# --- Channel message format ---
def format_channel_message(
    employee_key: str,
    queue: list,
    total_area: float,
    comment: str | None,
) -> str:
    emp_name = format_employee_name(employee_key)
    limit = config.AREA_LIMIT
    remainder = limit - total_area
    now = datetime.now()
    date_str = now.strftime("%d.%m.%Y %H:%M")

    lines = [
        "🧹 НОВОЕ ЗАДАНИЕ",
        "━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"👤 Исполнитель: {emp_name}",
        "",
        "ПОРЯДОК УБОРКИ:",
    ]
    for i, r in enumerate(queue, 1):
        num_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][min(i - 1, 9)] if i <= 10 else f"{i}."
        ct = format_cleaning_type(r.get("cleaning_type", "current"))
        lines.append(f"{num_emoji} {r['name']} — {r['area']:.0f} м² — {ct}")
        bl = r.get("bed_layout")
        if bl:
            lines.append(f"   🛏️ {format_bed_layout_label(bl)}")
        if r.get("linen_kit"):
            beds = r.get("beds_to_make")
            if beds is not None:
                lines.append(f"   Заправить кроватей: {beds}")
            vid = r.get("linen_variant")
            if vid is not None:
                lines.append(f"   Вариант белья: {LINEN_VARIANT_SHORT.get(int(vid), str(vid))}")
            lines.append("   Бельё:")
            for ln in format_linen_lines(r.get("linen_kit")):
                lines.append("   " + ln.strip())

    lines.extend([
        "",
        "📊 ИТОГО:",
        f"• Помещений: {len(queue)}",
        f"• Общая площадь: {total_area:.0f} / {limit:.0f} м²",
        f"• {'Превышение лимита: ' + str(abs(int(remainder))) + ' м²' if remainder < 0 else 'Остаток лимита: ' + str(int(remainder)) + ' м²'}",
        "",
        f"🕐 Смена от: {date_str}",
    ])
    if comment:
        lines.append("")
        lines.append(f"💬 Комментарий: {comment}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ Задание действительно до конца смены")

    return "\n".join(lines)


def strip_linen_fields_for_cleaning_type(item: dict, cleaning_type: str) -> None:
    if not cleaning_needs_linen_flow(cleaning_type):
        for k in ("bed_layout", "linen_kit", "beds_to_make", "linen_variant"):
            item.pop(k, None)


async def finish_pending_room_append(cq: CallbackQuery, state: FSMContext, item: dict) -> None:
    data = await state.get_data()
    selected = list(data.get("selected_rooms", []))
    selected.append(item)
    await state.update_data(
        selected_rooms=selected,
        pending_queue_item=None,
        pending_room_key=None,
        pending_beds_max=None,
        pending_separated_auto=False,
        pending_linen_variant=None,
    )
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


async def show_linen_variant_keyboard(cq: CallbackQuery, state: FSMContext, room_name: str, cleaning_type: str) -> None:
    await state.set_state(BossStates.selecting_linen_variant)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 · Белый 1,5", callback_data="lnv_1"),
        InlineKeyboardButton(text="2 · Голубой", callback_data="lnv_2"),
    )
    builder.row(
        InlineKeyboardButton(text="3 · Серый", callback_data="lnv_3"),
        InlineKeyboardButton(text="4 · Полоска", callback_data="lnv_4"),
    )
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="linwizard_cancel"))
    ct = format_cleaning_type(cleaning_type)
    await cq.message.edit_text(
        f"🧺 Вариант комплекта белья для:\n<b>{room_name}</b>\n\n({ct})",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


async def show_beds_count_keyboard(
    cq: CallbackQuery, state: FSMContext, max_beds: int, header: str
) -> None:
    await state.set_state(BossStates.selecting_beds_count)
    builder = InlineKeyboardBuilder()
    buttons = [InlineKeyboardButton(text=str(n), callback_data=f"bedn_{n}") for n in range(1, max_beds + 1)]
    for i in range(0, len(buttons), 4):
        builder.row(*buttons[i : i + 4])
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="linwizard_cancel"))
    await cq.message.edit_text(
        f"{header}\n\nСколько кроватей заправить? (от 1 до {max_beds})",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


# ---------- Start & Main Menu ----------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.from_user and message.from_user.id != config.BOSS_ID:
        await message.answer("У вас нет доступа к этому боту.")
        return
    await state.clear()
    await message.answer(main_menu_text(), reply_markup=main_menu_kb())
    await state.set_state(BossStates.main_menu)


@router.callback_query(F.data == "cancel_to_menu", BossStates.choosing_employee)
@router.callback_query(F.data == "cancel_to_menu", BossStates.choosing_rooms)
@router.callback_query(F.data == "cancel_to_menu", BossStates.adding_comment)
@router.callback_query(F.data == "cancel_to_menu", BossStates.selecting_bed_layout)
@router.callback_query(F.data == "cancel_to_menu", BossStates.selecting_linen_variant)
@router.callback_query(F.data == "cancel_to_menu", BossStates.selecting_beds_count)
@router.callback_query(F.data == "history_back")
@router.callback_query(F.data == "cancel_to_menu", BossStates.room_management)
async def to_main_menu(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.clear()
    await cq.message.edit_text(main_menu_text(), reply_markup=main_menu_kb())
    await state.set_state(BossStates.main_menu)


# ---------- Create task: choose employee ----------
@router.callback_query(F.data == "create_task", BossStates.main_menu)
async def create_task_start(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.choosing_employee)
    await state.update_data(selected_rooms=[], comment=None)
    await cq.message.edit_text(
        "👤 Для кого это задание?\n\n[👩 ДИНА] [👩 ЛЕНА]",
        reply_markup=choose_employee_kb(),
    )


@router.callback_query(F.data.in_(["emp_dina", "emp_lena"]), BossStates.choosing_employee)
async def employee_chosen(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    emp = "dina" if cq.data == "emp_dina" else "lena"
    await state.update_data(current_employee=emp, selected_rooms=[], comment=None)
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        data = await state.get_data()
        text, kb = await build_rooms_screen(
            session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


# ---------- Choosing rooms: add room → сначала выбор вида уборки ----------
@router.callback_query(F.data.startswith("room_add_"), BossStates.choosing_rooms)
async def room_add_to_queue(cq: CallbackQuery, state: FSMContext):
    if cq.data == "room_add_":
        await safe_answer(cq)
        return
    await safe_answer(cq)
    room_id = int(cq.data.replace("room_add_", ""))
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalars().first()
    if not room:
        await safe_answer(cq, "Помещение не найдено.")
        return
    await state.update_data(pending_room_id=room.id, pending_room_name=room.name, pending_room_area=room.area)
    await state.set_state(BossStates.selecting_cleaning_type)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for key, label in CLEANING_TYPES.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"ctype_{key}"))
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="ctype_cancel"))
    await cq.message.edit_text(
        f"👤 Выберите вид уборки для:\n<b>{room.name}</b> ({room.area:.2f} м²)",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("ctype_"), BossStates.selecting_cleaning_type)
async def cleaning_type_chosen(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    if cq.data == "ctype_cancel":
        await state.set_state(BossStates.choosing_rooms)
        await state.update_data(
            pending_room_id=None,
            pending_room_name=None,
            pending_room_area=None,
            pending_queue_item=None,
            pending_room_key=None,
            pending_beds_max=None,
            pending_separated_auto=False,
            pending_linen_variant=None,
        )
        data = await state.get_data()
        sm = get_async_session_maker()
        async with sm() as session:
            text, kb = await build_rooms_screen(
                session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
            )
        await cq.message.edit_text(text, reply_markup=kb)
        return
    # ctype_current, ctype_departure, ...
    cleaning_type = cq.data.replace("ctype_", "")
    if cleaning_type not in CLEANING_TYPES:
        return
    data = await state.get_data()
    rid = data.get("pending_room_id")
    rname = data.get("pending_room_name")
    rarea = data.get("pending_room_area")
    if rid is None:
        await state.set_state(BossStates.choosing_rooms)
        return
    item = {"id": rid, "name": rname, "area": rarea, "cleaning_type": cleaning_type}
    room_key = room_key_from_name(rname or "")

    await state.update_data(
        pending_room_id=None,
        pending_room_name=None,
        pending_room_area=None,
    )

    if cleaning_needs_linen_flow(cleaning_type) and room_key:
        if room_needs_bed_layout(room_key):
            await state.update_data(pending_queue_item=item, pending_room_key=room_key)
            await state.set_state(BossStates.selecting_bed_layout)
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="Кровати разъединены", callback_data="bedl_s"),
                InlineKeyboardButton(text="Кровати соединены", callback_data="bedl_j"),
            )
            builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="linwizard_cancel"))
            ct = format_cleaning_type(cleaning_type)
            await cq.message.edit_text(
                f"🛏️ Расположение кроватей для:\n<b>{rname}</b>\n\n({ct})",
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
            return
        if room_needs_color_linen(room_key):
            await state.update_data(pending_queue_item=item, pending_room_key=room_key)
            await show_linen_variant_keyboard(cq, state, rname or "", cleaning_type)
            return

    await finish_pending_room_append(cq, state, item)


@router.callback_query(F.data == "linwizard_cancel", StateFilter(BossStates.selecting_bed_layout))
@router.callback_query(F.data == "linwizard_cancel", StateFilter(BossStates.selecting_linen_variant))
@router.callback_query(F.data == "linwizard_cancel", StateFilter(BossStates.selecting_beds_count))
async def linen_wizard_cancel(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.update_data(
        pending_queue_item=None,
        pending_room_key=None,
        pending_beds_max=None,
        pending_separated_auto=False,
        pending_linen_variant=None,
    )
    await state.set_state(BossStates.choosing_rooms)
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.in_({"bedl_s", "bedl_j"}), StateFilter(BossStates.selecting_bed_layout))
async def bed_layout_chosen(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    layout = "separated" if cq.data == "bedl_s" else "joined"
    data = await state.get_data()
    item = dict(data.get("pending_queue_item") or {})
    key = data.get("pending_room_key")
    if not item or not key:
        await state.set_state(BossStates.choosing_rooms)
        return
    item["bed_layout"] = layout
    cleaning_type = item.get("cleaning_type", "")

    if key in AUTO_LINEN_BY_LAYOUT_ROOMS:
        if layout == "joined":
            item["linen_kit"] = dict(JOINED_DOUBLE_KIT)
            item["beds_to_make"] = 1
            await finish_pending_room_append(cq, state, item)
            return
        await state.update_data(
            pending_queue_item=item,
            pending_beds_max=2,
            pending_separated_auto=True,
        )
        header = (
            f"🛏️ <b>{item.get('name', '')}</b>\n"
            f"Кровати разъединены — комплект 1,5 сп. белый\n\n({format_cleaning_type(cleaning_type)})"
        )
        await show_beds_count_keyboard(cq, state, 2, header)
        return

    await finish_pending_room_append(cq, state, item)


@router.callback_query(F.data.startswith("lnv_"), StateFilter(BossStates.selecting_linen_variant))
async def linen_variant_chosen(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    try:
        variant = int(cq.data.replace("lnv_", ""))
    except ValueError:
        return
    if variant not in (1, 2, 3, 4):
        return
    data = await state.get_data()
    key = data.get("pending_room_key")
    item = data.get("pending_queue_item")
    if not key or not item or key not in LINEN_COLOR_MAX_BEDS:
        await state.set_state(BossStates.choosing_rooms)
        return
    max_b = LINEN_COLOR_MAX_BEDS[key]
    cleaning_type = item.get("cleaning_type", "")
    await state.update_data(
        pending_linen_variant=variant,
        pending_beds_max=max_b,
        pending_separated_auto=False,
    )
    vlabel = LINEN_VARIANT_SHORT.get(variant, str(variant))
    header = (
        f"🧺 <b>{item.get('name', '')}</b>\n"
        f"Вариант белья: {vlabel}\n\n({format_cleaning_type(cleaning_type)})"
    )
    await show_beds_count_keyboard(cq, state, max_b, header)


@router.callback_query(F.data.startswith("bedn_"), StateFilter(BossStates.selecting_beds_count))
async def beds_count_chosen(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    try:
        n = int(cq.data.replace("bedn_", ""))
    except ValueError:
        return
    data = await state.get_data()
    item = dict(data.get("pending_queue_item") or {})
    key = data.get("pending_room_key")
    max_b = data.get("pending_beds_max") or 0
    if not item or not key or n < 1 or n > max_b:
        return
    separated_auto = data.get("pending_separated_auto")
    if separated_auto:
        item["bed_layout"] = "separated"
        item["linen_kit"] = scale_linen_kit(SEPARATED_15_FULL, n, 2)
        item["beds_to_make"] = n
    else:
        variant = data.get("pending_linen_variant")
        if variant not in (1, 2, 3, 4):
            return
        full = build_color_variant_full_kit(variant, max_b)
        item["linen_kit"] = scale_linen_kit(full, n, max_b)
        item["linen_variant"] = variant
        item["beds_to_make"] = n
    await finish_pending_room_append(cq, state, item)


@router.callback_query(F.data == "noop")
async def noop(cq: CallbackQuery):
    await safe_answer(cq)


# ---------- Queue: up / down / delete (короткие callback_data: qup_N, qdown_N, qdel_N) ----------
def apply_queue_action(selected: list, action: str, index: int) -> list:
    selected = list(selected)
    if action == "up":
        if index <= 0:
            return selected
        selected[index], selected[index - 1] = selected[index - 1], selected[index]
    elif action == "down":
        if index >= len(selected) - 1:
            return selected
        selected[index], selected[index + 1] = selected[index + 1], selected[index]
    elif action == "del":
        selected.pop(index)
    return selected


@router.callback_query(F.data.startswith("qup_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("qdown_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("qdel_"), BossStates.choosing_rooms)
async def queue_action(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    prefix = "qup_" if cq.data.startswith("qup_") else "qdown_" if cq.data.startswith("qdown_") else "qdel_"
    action = "up" if prefix == "qup_" else "down" if prefix == "qdown_" else "del"
    try:
        index = int(cq.data.replace(prefix, ""))
    except ValueError:
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if index < 0 or index >= len(selected):
        return
    new_selected = apply_queue_action(selected, action, index)
    await state.update_data(selected_rooms=new_selected)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], new_selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data.startswith("queue_up_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("queue_down_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("queue_del_"), BossStates.choosing_rooms)
async def queue_action_legacy(cq: CallbackQuery, state: FSMContext):
    """Поддержка старых callback_data вида queue_up_N / queue_down_N / queue_del_N."""
    await safe_answer(cq)
    if cq.data.startswith("queue_up_"):
        prefix, action = "queue_up_", "up"
    elif cq.data.startswith("queue_down_"):
        prefix, action = "queue_down_", "down"
    else:
        prefix, action = "queue_del_", "del"
    try:
        index = int(cq.data.replace(prefix, ""))
    except ValueError:
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if index < 0 or index >= len(selected):
        return
    new_selected = apply_queue_action(selected, action, index)
    await state.update_data(selected_rooms=new_selected)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], new_selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


# ---------- Смена вида уборки для элемента очереди (ct_N → выбор типа → settype_N_X) ----------
@router.callback_query(F.data.startswith("ct_"), BossStates.choosing_rooms)
async def queue_change_type_show(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    try:
        idx = int(cq.data.replace("ct_", ""))
    except ValueError:
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if idx < 0 or idx >= len(selected):
        return
    builder = InlineKeyboardBuilder()
    for key, label in CLEANING_TYPES.items():
        builder.row(InlineKeyboardButton(text=label, callback_data=f"settype_{idx}_{key}"))
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="settype_back"))
    await cq.message.edit_text(
        f"Вид уборки для: <b>{selected[idx]['name']}</b>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    await state.update_data(editing_queue_index=idx)
    await state.set_state(BossStates.selecting_cleaning_type)


@router.callback_query(F.data.startswith("settype_"), BossStates.selecting_cleaning_type)
async def queue_set_type(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    if cq.data == "settype_back":
        await state.set_state(BossStates.choosing_rooms)
        data = await state.get_data()
        sm = get_async_session_maker()
        async with sm() as session:
            text, kb = await build_rooms_screen(
                session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
            )
        await cq.message.edit_text(text, reply_markup=kb)
        return
    # settype_2_departure
    parts = cq.data.split("_")
    if len(parts) != 3:
        return
    try:
        idx = int(parts[1])
        ctype = parts[2]
    except (ValueError, IndexError):
        return
    if ctype not in CLEANING_TYPES:
        return
    data = await state.get_data()
    selected = list(data.get("selected_rooms", []))
    if idx < 0 or idx >= len(selected):
        return
    selected[idx]["cleaning_type"] = ctype
    strip_linen_fields_for_cleaning_type(selected[idx], ctype)
    await state.update_data(selected_rooms=selected)
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


# ---------- Send task ----------
@router.callback_query(F.data == "send_task", BossStates.choosing_rooms)
async def send_task(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if not selected:
        await safe_answer(cq, "⚠️ Очередь пуста. Добавьте помещения.", show_alert=True)
        return
    await safe_answer(cq)

    employee = data["current_employee"]
    comment = data.get("comment")
    total_area = sum(r["area"] for r in selected)
    channel_id = config.CHANNEL_ID
    if isinstance(channel_id, str) and channel_id.lstrip("-").isdigit():
        channel_id = int(channel_id)

    msg_text = format_channel_message(employee, selected, total_area, comment)
    try:
        sent = await cq.bot.send_message(
            chat_id=channel_id,
            text=msg_text,
        )
        message_id = sent.message_id
    except Exception as e:
        await cq.message.edit_text(f"❌ Ошибка отправки в канал: {e}")
        return

    # Save to history
    sm = get_async_session_maker()
    async with sm() as session:
        task = Task(
            employee_name=employee,
            rooms_list=json.dumps(selected, ensure_ascii=False),
            total_area=total_area,
            message_id=message_id,
            comment=comment,
        )
        session.add(task)
        await session.commit()

    # Full reset
    await state.clear()
    await state.set_state(BossStates.main_menu)
    emp_name = format_employee_name(employee)
    done_text = (
        "✅ ГОТОВО!\n\n"
        f"Задание для {emp_name} отправлено в канал.\n"
        f"Общая площадь: {total_area:.0f} м²\n\n"
    )
    await cq.message.edit_text(done_text, reply_markup=after_send_kb())


# ---------- Clear queue / Change employee ----------
@router.callback_query(F.data == "clear_queue", BossStates.choosing_rooms)
async def clear_queue(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.update_data(selected_rooms=[])
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], [], data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "change_employee", BossStates.choosing_rooms)
async def change_employee(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.choosing_employee)
    await state.update_data(selected_rooms=[], comment=None)
    await cq.message.edit_text(
        "👤 Для кого это задание?\n\n[👩 ДИНА] [👩 ЛЕНА]",
        reply_markup=choose_employee_kb(),
    )


# ---------- Add comment ----------
@router.callback_query(F.data == "add_comment", BossStates.choosing_rooms)
async def add_comment_start(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.adding_comment)
    await cq.message.edit_text(
        "💬 Введите комментарий к заданию (или отправьте «-» чтобы пропустить):",
        reply_markup=back_kb("cancel_to_menu"),
    )


@router.message(BossStates.adding_comment, F.text)
async def add_comment_done(message: Message, state: FSMContext):
    comment = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(comment=comment or None)
    await state.set_state(BossStates.choosing_rooms)
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
        )
    await message.answer(text, reply_markup=kb)
    await message.delete()


# ---------- History ----------
@router.callback_query(F.data == "history", BossStates.main_menu)
async def history_list(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.history_list)
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(
            select(Task).order_by(Task.created_at.desc()).limit(50)
        )
        tasks = list(result.scalars().all())

    by_date = defaultdict(list)
    for t in tasks:
        d = t.created_at.date() if hasattr(t.created_at, "date") else t.created_at
        by_date[d].append(t)

    lines = ["📋 ИСТОРИЯ ЗАДАНИЙ", ""]
    for d in sorted(by_date.keys(), reverse=True)[:7]:
        lines.append(format_date_group(d) + ":")
        for t in by_date[d]:
            emp = format_employee_name(t.employee_name)
            time_str = t.created_at.strftime("%H:%M") if hasattr(t.created_at, "strftime") else str(t.created_at)
            count = len(json.loads(t.rooms_list)) if t.rooms_list else 0
            lines.append(f"  {time_str} 👩 {emp} | {t.total_area:.0f} м² | {count} номера")
        lines.append("")

    text = "\n".join(lines).strip()
    builder = InlineKeyboardBuilder()
    for t in tasks[:15]:
        builder.row(
            InlineKeyboardButton(
                text=f"{t.created_at.strftime('%d.%m %H:%M')} {format_employee_name(t.employee_name)} {t.total_area:.0f} м²",
                callback_data=f"history_detail_{t.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="history_back"))

    await cq.message.edit_text(text or "Нет заданий.", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("history_detail_"), BossStates.history_list)
async def history_detail(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    task_id = int(cq.data.replace("history_detail_", ""))
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalars().first()
    if not task:
        return
    rooms = json.loads(task.rooms_list)
    lines = [
        f"📋 Задание #{task.id}",
        f"👤 {format_employee_name(task.employee_name)}",
        f"🕐 {task.created_at.strftime('%d.%m.%Y %H:%M')}",
        f"📊 {task.total_area:.0f} м², помещений: {len(rooms)}",
        "",
        "Порядок уборки:",
    ]
    for i, r in enumerate(rooms, 1):
        ct = format_cleaning_type(r.get("cleaning_type", "current"))
        lines.append(f"  {i}. {r.get('name', '')} — {r.get('area', 0):.0f} м² — {ct}")
        bl = r.get("bed_layout")
        if bl:
            lines.append(f"     🛏️ {format_bed_layout_label(bl)}")
        if r.get("linen_kit"):
            if r.get("beds_to_make") is not None:
                lines.append(f"     Заправить кроватей: {r['beds_to_make']}")
            vid = r.get("linen_variant")
            if vid is not None:
                lines.append(f"     Вариант: {LINEN_VARIANT_SHORT.get(int(vid), str(vid))}")
            for ln in format_linen_lines(r.get("linen_kit")):
                lines.append("    " + ln.strip())
    if task.comment:
        lines.append("")
        lines.append(f"💬 {task.comment}")
    await cq.message.edit_text("\n".join(lines), reply_markup=history_detail_back_kb())


# ---------- Channel link ----------
@router.callback_query(F.data == "channel_link", BossStates.main_menu)
async def channel_link(cq: CallbackQuery):
    await safe_answer(cq)
    await cq.message.answer(f"🔗 Ссылка на канал: {config.CHANNEL_LINK}")


# ---------- Room management ----------
@router.callback_query(F.data == "rooms_manage", BossStates.main_menu)
async def rooms_manage(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.room_management)
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).order_by(Room.name))
        rooms = list(result.scalars().all())
    lines = ["🏨 УПРАВЛЕНИЕ ПОМЕЩЕНИЯМИ", "", "Помещение — Площадь — Статус"]
    for r in rooms:
        status = "✅" if r.is_active else "🔴 откл."
        lines.append(f"{r.name} — {r.area:.2f} — {status}")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить помещение", callback_data="room_add"))
    for r in rooms:
        builder.row(
            InlineKeyboardButton(text=f"✏️ {r.name}", callback_data=f"room_edit_{r.id}"),
            InlineKeyboardButton(
                text="🔴 Откл" if r.is_active else "🟢 Вкл",
                callback_data=f"room_toggle_{r.id}",
            ),
        )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="cancel_to_menu"))
    await cq.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data == "rooms_manage")
async def back_to_rooms_manage(cq: CallbackQuery, state: FSMContext):
    """Return to room management from add/edit flows."""
    await safe_answer(cq)
    cur = await state.get_state()
    if cur not in (BossStates.room_add_name.state, BossStates.room_add_area.state, BossStates.room_edit_area.state):
        return
    await state.set_state(BossStates.room_management)
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).order_by(Room.name))
        rooms = list(result.scalars().all())
    lines = ["🏨 УПРАВЛЕНИЕ ПОМЕЩЕНИЯМИ", "", "Помещение — Площадь — Статус"]
    for r in rooms:
        status = "✅" if r.is_active else "🔴 откл."
        lines.append(f"{r.name} — {r.area:.2f} — {status}")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить помещение", callback_data="room_add"))
    for r in rooms:
        builder.row(
            InlineKeyboardButton(text=f"✏️ {r.name}", callback_data=f"room_edit_{r.id}"),
            InlineKeyboardButton(text="🔴 Откл" if r.is_active else "🟢 Вкл", callback_data=f"room_toggle_{r.id}"),
        )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="cancel_to_menu"))
    await cq.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data == "room_add", BossStates.room_management)
async def room_add_start(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    await state.set_state(BossStates.room_add_name)
    await cq.message.edit_text(
        "Введите название помещения:",
        reply_markup=back_kb("rooms_manage"),
    )


@router.message(BossStates.room_add_name, F.text)
async def room_add_name(message: Message, state: FSMContext):
    await state.update_data(room_name=message.text.strip())
    await state.set_state(BossStates.room_add_area)
    await message.answer("Введите площадь (число, например 25.5):", reply_markup=back_kb("rooms_manage"))
    await message.delete()


@router.message(BossStates.room_add_area, F.text)
async def room_add_area(message: Message, state: FSMContext):
    try:
        area = float(message.text.strip().replace(",", "."))
        if area <= 0:
            raise ValueError("Площадь должна быть больше 0")
    except ValueError:
        await message.answer("Введите число, например 25.5")
        return
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        room = Room(name=data["room_name"], area=area, is_active=True)
        session.add(room)
        await session.commit()
    await state.set_state(BossStates.room_management)
    await state.clear()
    await message.answer(f"✅ Добавлено: {data['room_name']} — {area} м²")
    # Return to room management
    await message.answer("Выберите действие:", reply_markup=room_management_kb())
    await message.delete()


@router.callback_query(F.data.startswith("room_edit_"), BossStates.room_management)
async def room_edit_select(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    room_id = int(cq.data.replace("room_edit_", ""))
    await state.update_data(editing_room_id=room_id)
    await state.set_state(BossStates.room_edit_area)
    await cq.message.edit_text(
        "Введите новую площадь (число):",
        reply_markup=back_kb("rooms_manage"),
    )


@router.callback_query(F.data.startswith("room_edit_area_"), BossStates.room_management)
async def room_edit_area_start(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    room_id = int(cq.data.replace("room_edit_area_", ""))
    await state.update_data(editing_room_id=room_id)
    await state.set_state(BossStates.room_edit_area)
    await cq.message.edit_text(
        "Введите новую площадь (число):",
        reply_markup=back_kb("rooms_manage"),
    )


@router.callback_query(F.data.startswith("room_toggle_"), BossStates.room_management)
async def room_toggle(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    room_id = int(cq.data.replace("room_toggle_", ""))
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalars().first()
        if room:
            room.is_active = not room.is_active
            await session.commit()
        # else: помещение не найдено — просто обновим список
    await rooms_manage(cq, state)


@router.message(BossStates.room_edit_area, F.text)
async def room_edit_area_done(message: Message, state: FSMContext):
    try:
        area = float(message.text.strip().replace(",", "."))
        if area <= 0:
            raise ValueError("Площадь должна быть больше 0")
    except ValueError:
        await message.answer("Введите число, например 25.5")
        return
    data = await state.get_data()
    room_id = data.get("editing_room_id")
    if not room_id:
        await state.clear()
        await message.answer("Ошибка. Вернитесь в меню.")
        return
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalars().first()
        if room:
            room.area = area
            await session.commit()
            await message.answer(f"✅ Площадь обновлена: {room.name} — {area} м²")
    await state.set_state(BossStates.room_management)
    await state.clear()
    await message.delete()


# ---------- Template apply (optional) ----------
@router.callback_query(F.data.startswith("template_apply_"), BossStates.choosing_rooms)
async def template_apply(cq: CallbackQuery, state: FSMContext):
    await safe_answer(cq)
    template_id = int(cq.data.replace("template_apply_", ""))
    data = await state.get_data()
    selected = list(data.get("selected_rooms", []))

    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Template).where(Template.id == template_id))
        template = result.scalars().first()
        if not template:
            return
        rooms_data = json.loads(template.rooms_list)
        for r in rooms_data:
            r = dict(r)
            r.setdefault("cleaning_type", "current")
            selected.append(r)
        await state.update_data(selected_rooms=selected)
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)


# ---------- Fallback: callback не попал ни в один обработчик — только снимаем спиннер ----------
@router.callback_query()
async def callback_fallback(cq: CallbackQuery, state: FSMContext):
    """Только отвечаем на callback (убираем спиннер), сообщение и состояние не трогаем."""
    await safe_answer(cq)