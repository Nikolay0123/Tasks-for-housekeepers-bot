"""Boss-only handlers: task creation, history, room management."""
import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import CommandStart
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
from utils.helpers import (
    format_area,
    format_employee_name,
    format_date_group,
    CLEANING_TYPES,
    format_cleaning_type,
    LINEN_PACKAGES,
    LINEN_PACKAGES_FLOOR4,
    LINEN_COLORS,
    LINEN_COLOR_ORDER,
    format_linen_color,
    room_linen_profile,
    resolve_linen_profile,
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


def build_linen_variant_markup_and_header(room_name: str, linen_profile: str) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и клавиатура выбора варианта комплекта (classic = 101–109, floor4 = 4 этаж)."""
    builder = InlineKeyboardBuilder()
    if linen_profile == "floor4":
        builder.row(InlineKeyboardButton(text="Вариант 1 (по 2 шт.)", callback_data="lset_1"))
        builder.row(InlineKeyboardButton(text="Вариант 2 (по 3 шт.)", callback_data="lset_2"))
        builder.row(InlineKeyboardButton(text="Вариант 3 (по 4 шт.)", callback_data="lset_3"))
        header = (
            f"Выберите вариант комплектации белья для номера:\n<b>{room_name}</b>\n\n"
            "Каждый вариант: простыня 1,5, пододеяльник 1,5, полотенце банное, полотенце 40×70."
        )
    else:
        builder.row(InlineKeyboardButton(text="Вариант 1", callback_data="lset_1"))
        builder.row(InlineKeyboardButton(text="Вариант 2", callback_data="lset_2"))
        builder.row(InlineKeyboardButton(text="Вариант 3", callback_data="lset_3"))
        header = f"Выберите вариант комплектации белья для номера:\n<b>{room_name}</b>"
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="lset_cancel"))
    return header, builder.as_markup()


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
            suffix = ""
            if resolve_linen_profile(r) == "floor4" and r.get("linen_variant") is not None:
                lc = format_linen_color(r.get("linen_color"))
                v = r.get("linen_variant")
                if lc:
                    suffix = f" (комплект {v}, {lc})"
            lines.append(f"{i}. {r['name']} — {format_area(r['area'])} м² ({ct}){suffix}")

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
    # Итог по белью (накапливаем по всем номерам)
    linen_totals: dict[str, int] = defaultdict(int)
    # Суммарное число единиц (позиций) по цвету: голубое / серое / в полоску / белое
    linen_color_totals: dict[str, int] = {LINEN_COLORS[k]: 0 for k in LINEN_COLOR_ORDER}

    for i, r in enumerate(queue, 1):
        num_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][min(i - 1, 9)] if i <= 10 else f"{i}."
        ct = format_cleaning_type(r.get("cleaning_type", "current"))
        linen_variant = r.get("linen_variant")
        profile = resolve_linen_profile(r)

        bed_config = ""
        if isinstance(linen_variant, int):
            if profile == "classic" and linen_variant in LINEN_PACKAGES:
                if linen_variant == 1:
                    bed_config = " — кровати соединены"
                elif linen_variant == 2:
                    bed_config = " — кровати разъединены"
            elif profile == "floor4":
                col = format_linen_color(r.get("linen_color"))
                if col:
                    bed_config = f" — бельё: {col}"

        lines.append(f"{num_emoji} {r['name']} — {r['area']:.0f} м² — {ct}{bed_config}")

        if isinstance(linen_variant, int):
            if profile == "floor4" and linen_variant in LINEN_PACKAGES_FLOOR4:
                pkg = LINEN_PACKAGES_FLOOR4[linen_variant]
                for item_name, qty in pkg.items():
                    linen_totals[item_name] += qty
                ck = r.get("linen_color")
                if ck in LINEN_COLORS:
                    linen_color_totals[LINEN_COLORS[ck]] += sum(pkg.values())
            elif profile == "classic" and linen_variant in LINEN_PACKAGES:
                pkg = LINEN_PACKAGES[linen_variant]
                for item_name, qty in pkg.items():
                    linen_totals[item_name] += qty
                linen_color_totals["белое"] += sum(pkg.values())

    lines.extend([
        "",
        "📊 ИТОГО:",
        f"• Помещений: {len(queue)}",
        f"• Общая площадь: {total_area:.0f} / {limit:.0f} м²",
        f"• {'Превышение лимита: ' + str(abs(int(remainder))) + ' м²' if remainder < 0 else 'Остаток лимита: ' + str(int(remainder)) + ' м²'}",
        "",
        f"🕐 Смена от: {date_str}",
    ])

    # Блок с итогами по белью
    if linen_totals:
        lines.append("")
        lines.append("🧺 БЕЛЬЁ (ИТОГО ПО ЗАДАНИЮ):")
        lines.append("По цвету (всего единиц):")
        for key in LINEN_COLOR_ORDER:
            label = LINEN_COLORS[key]
            lines.append(f"• {label}: {linen_color_totals[label]} шт.")
        lines.append("")
        lines.append("По наименованию:")
        for item_name, qty in linen_totals.items():
            lines.append(f"• {item_name}: {qty} шт.")
    if comment:
        lines.append("")
        lines.append(f"💬 Комментарий: {comment}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("✅ Задание действительно до конца смены")

    return "\n".join(lines)


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
@router.callback_query(F.data == "history_back")
@router.callback_query(F.data == "cancel_to_menu", BossStates.room_management)
async def to_main_menu(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.edit_text(main_menu_text(), reply_markup=main_menu_kb())
    await state.set_state(BossStates.main_menu)
    await cq.answer()


# ---------- Create task: choose employee ----------
@router.callback_query(F.data == "create_task", BossStates.main_menu)
async def create_task_start(cq: CallbackQuery, state: FSMContext):
    await state.set_state(BossStates.choosing_employee)
    await state.update_data(selected_rooms=[], comment=None)
    await cq.message.edit_text(
        "👤 Для кого это задание?\n\nДина, Лена или Оля — кнопки ниже.",
        reply_markup=choose_employee_kb(),
    )
    await cq.answer()


@router.callback_query(F.data.in_(["emp_dina", "emp_lena", "emp_olya"]), BossStates.choosing_employee)
async def employee_chosen(cq: CallbackQuery, state: FSMContext):
    if cq.data == "emp_dina":
        emp = "dina"
    elif cq.data == "emp_lena":
        emp = "lena"
    else:
        emp = "olya"
    await state.update_data(current_employee=emp, selected_rooms=[], comment=None)
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        data = await state.get_data()
        text, kb = await build_rooms_screen(
            session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


# ---------- Choosing rooms: add room → сначала выбор вида уборки ----------
@router.callback_query(F.data.startswith("room_add_"), BossStates.choosing_rooms)
async def room_add_to_queue(cq: CallbackQuery, state: FSMContext):
    if cq.data == "room_add_":
        await cq.answer()
        return
    room_id = int(cq.data.replace("room_add_", ""))
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalars().first()
    if not room:
        await cq.answer("Помещение не найдено.")
        return
    linen_profile = room_linen_profile(room.name)

    await state.update_data(
        pending_room_id=room.id,
        pending_room_name=room.name,
        pending_room_area=room.area,
        pending_linen_profile=linen_profile,
        pending_cleaning_type=None,
    )
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
    await cq.answer()


@router.callback_query(F.data.startswith("ctype_"), BossStates.selecting_cleaning_type)
async def cleaning_type_chosen(cq: CallbackQuery, state: FSMContext):
    if cq.data == "ctype_cancel":
        await state.set_state(BossStates.choosing_rooms)
        await state.update_data(
            pending_room_id=None,
            pending_room_name=None,
            pending_room_area=None,
            pending_linen_profile=None,
        )
        data = await state.get_data()
        sm = get_async_session_maker()
        async with sm() as session:
            text, kb = await build_rooms_screen(
                session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
            )
        await cq.message.edit_text(text, reply_markup=kb)
        await cq.answer()
        return
    # ctype_current, ctype_departure, ...
    cleaning_type = cq.data.replace("ctype_", "")
    if cleaning_type not in CLEANING_TYPES:
        await cq.answer()
        return
    data = await state.get_data()
    rid = data.get("pending_room_id")
    rname = data.get("pending_room_name")
    rarea = data.get("pending_room_area")
    linen_profile = data.get("pending_linen_profile")
    if rid is None:
        await cq.answer("Ошибка. Выберите помещение снова.")
        await state.set_state(BossStates.choosing_rooms)
        return
    # Номера с комплектом белья (101–109 или 4 этаж) — кроме вида «текущая»
    if linen_profile and cleaning_type != "current":
        await state.update_data(pending_cleaning_type=cleaning_type)
        await state.set_state(BossStates.selecting_linen_variant)
        header, markup = build_linen_variant_markup_and_header(rname, linen_profile)
        await cq.message.edit_text(header, reply_markup=markup, parse_mode="HTML")
        await cq.answer()
        return

    # Обычный номер — сразу добавляем в очередь
    selected = list(data.get("selected_rooms", []))
    selected.append(
        {
            "id": rid,
            "name": rname,
            "area": rarea,
            "cleaning_type": cleaning_type,
        }
    )
    await state.update_data(
        selected_rooms=selected,
        pending_room_id=None,
        pending_room_name=None,
        pending_room_area=None,
        pending_linen_profile=None,
        pending_cleaning_type=None,
    )
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("lset_"), BossStates.selecting_linen_variant)
async def linen_variant_chosen(cq: CallbackQuery, state: FSMContext):
    """Выбор варианта комплектации белья (101–109 или 4 этаж)."""
    if cq.data == "lset_cancel":
        await state.set_state(BossStates.choosing_rooms)
        await state.update_data(
            pending_room_id=None,
            pending_room_name=None,
            pending_room_area=None,
            pending_linen_profile=None,
            pending_cleaning_type=None,
            pending_linen_variant=None,
        )
        data = await state.get_data()
        sm = get_async_session_maker()
        async with sm() as session:
            text, kb = await build_rooms_screen(
                session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
            )
        await cq.message.edit_text(text, reply_markup=kb)
        await cq.answer()
        return

    try:
        variant = int(cq.data.replace("lset_", ""))
    except ValueError:
        await cq.answer()
        return

    data = await state.get_data()
    rid = data.get("pending_room_id")
    rname = data.get("pending_room_name")
    rarea = data.get("pending_room_area")
    cleaning_type = data.get("pending_cleaning_type")
    linen_profile = data.get("pending_linen_profile")

    if rid is None or cleaning_type is None:
        await cq.answer("Ошибка. Попробуйте выбрать номер снова.", show_alert=True)
        await state.set_state(BossStates.choosing_rooms)
        return

    if linen_profile == "floor4":
        await state.update_data(pending_linen_variant=variant)
        await state.set_state(BossStates.selecting_linen_color)
        cb = InlineKeyboardBuilder()
        for key, label in LINEN_COLORS.items():
            cb.row(InlineKeyboardButton(text=label, callback_data=f"lcol_{key}"))
        cb.row(InlineKeyboardButton(text="🔙 Назад к вариантам", callback_data="lcol_cancel"))
        await cq.message.edit_text(
            f"Цвет белья для <b>{rname}</b> (комплект вариант {variant}):",
            reply_markup=cb.as_markup(),
            parse_mode="HTML",
        )
        await cq.answer()
        return

    selected = list(data.get("selected_rooms", []))
    selected.append(
        {
            "id": rid,
            "name": rname,
            "area": rarea,
            "cleaning_type": cleaning_type,
            "linen_variant": variant,
        }
    )

    await state.update_data(
        selected_rooms=selected,
        pending_room_id=None,
        pending_room_name=None,
        pending_room_area=None,
        pending_linen_profile=None,
        pending_cleaning_type=None,
        pending_linen_variant=None,
    )
    await state.set_state(BossStates.choosing_rooms)

    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("lcol_"), BossStates.selecting_linen_color)
async def linen_color_chosen(cq: CallbackQuery, state: FSMContext):
    if cq.data == "lcol_cancel":
        data = await state.get_data()
        rname = data.get("pending_room_name")
        linen_profile = data.get("pending_linen_profile")
        if not rname or not linen_profile:
            await state.set_state(BossStates.choosing_rooms)
            sm = get_async_session_maker()
            async with sm() as session:
                text, kb = await build_rooms_screen(
                    session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
                )
            await cq.message.edit_text(text, reply_markup=kb)
            await cq.answer("Сессия сброшена.", show_alert=True)
            return
        await state.set_state(BossStates.selecting_linen_variant)
        header, markup = build_linen_variant_markup_and_header(rname, linen_profile)
        await cq.message.edit_text(header, reply_markup=markup, parse_mode="HTML")
        await cq.answer()
        return

    color_key = cq.data.replace("lcol_", "")
    if color_key not in LINEN_COLORS:
        await cq.answer()
        return

    data = await state.get_data()
    rid = data.get("pending_room_id")
    rname = data.get("pending_room_name")
    rarea = data.get("pending_room_area")
    cleaning_type = data.get("pending_cleaning_type")
    variant = data.get("pending_linen_variant")

    if rid is None or cleaning_type is None or variant is None:
        await cq.answer("Ошибка. Попробуйте выбрать номер снова.", show_alert=True)
        await state.set_state(BossStates.choosing_rooms)
        return

    selected = list(data.get("selected_rooms", []))
    selected.append(
        {
            "id": rid,
            "name": rname,
            "area": rarea,
            "cleaning_type": cleaning_type,
            "linen_variant": variant,
            "linen_profile": "floor4",
            "linen_color": color_key,
        }
    )
    await state.update_data(
        selected_rooms=selected,
        pending_room_id=None,
        pending_room_name=None,
        pending_room_area=None,
        pending_linen_profile=None,
        pending_cleaning_type=None,
        pending_linen_variant=None,
    )
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data == "noop")
async def noop(cq: CallbackQuery):
    await cq.answer()


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
    prefix = "qup_" if cq.data.startswith("qup_") else "qdown_" if cq.data.startswith("qdown_") else "qdel_"
    action = "up" if prefix == "qup_" else "down" if prefix == "qdown_" else "del"
    try:
        index = int(cq.data.replace(prefix, ""))
    except ValueError:
        await cq.answer()
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if index < 0 or index >= len(selected):
        await cq.answer()
        return
    new_selected = apply_queue_action(selected, action, index)
    await state.update_data(selected_rooms=new_selected)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], new_selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data.startswith("queue_up_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("queue_down_"), BossStates.choosing_rooms)
@router.callback_query(F.data.startswith("queue_del_"), BossStates.choosing_rooms)
async def queue_action_legacy(cq: CallbackQuery, state: FSMContext):
    """Поддержка старых callback_data вида queue_up_N / queue_down_N / queue_del_N."""
    if cq.data.startswith("queue_up_"):
        prefix, action = "queue_up_", "up"
    elif cq.data.startswith("queue_down_"):
        prefix, action = "queue_down_", "down"
    else:
        prefix, action = "queue_del_", "del"
    try:
        index = int(cq.data.replace(prefix, ""))
    except ValueError:
        await cq.answer()
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if index < 0 or index >= len(selected):
        await cq.answer()
        return
    new_selected = apply_queue_action(selected, action, index)
    await state.update_data(selected_rooms=new_selected)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], new_selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


# ---------- Смена вида уборки для элемента очереди (ct_N → выбор типа → settype_N_X) ----------
@router.callback_query(F.data.startswith("ct_"), BossStates.choosing_rooms)
async def queue_change_type_show(cq: CallbackQuery, state: FSMContext):
    try:
        idx = int(cq.data.replace("ct_", ""))
    except ValueError:
        await cq.answer()
        return
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if idx < 0 or idx >= len(selected):
        await cq.answer()
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
    await cq.answer()


@router.callback_query(F.data.startswith("settype_"), BossStates.selecting_cleaning_type)
async def queue_set_type(cq: CallbackQuery, state: FSMContext):
    if cq.data == "settype_back":
        await state.set_state(BossStates.choosing_rooms)
        data = await state.get_data()
        sm = get_async_session_maker()
        async with sm() as session:
            text, kb = await build_rooms_screen(
                session, data["current_employee"], data.get("selected_rooms", []), data.get("comment")
            )
        await cq.message.edit_text(text, reply_markup=kb)
        await cq.answer()
        return
    # settype_2_departure
    parts = cq.data.split("_")
    if len(parts) != 3:
        await cq.answer()
        return
    try:
        idx = int(parts[1])
        ctype = parts[2]
    except (ValueError, IndexError):
        await cq.answer()
        return
    if ctype not in CLEANING_TYPES:
        await cq.answer()
        return
    data = await state.get_data()
    selected = list(data.get("selected_rooms", []))
    if idx < 0 or idx >= len(selected):
        await cq.answer()
        return
    selected[idx]["cleaning_type"] = ctype
    await state.update_data(selected_rooms=selected)
    await state.set_state(BossStates.choosing_rooms)
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], selected, data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


# ---------- Send task ----------
@router.callback_query(F.data == "send_task", BossStates.choosing_rooms)
async def send_task(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_rooms", [])
    if not selected:
        await cq.answer("⚠️ Очередь пуста. Добавьте помещения.", show_alert=True)
        return

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
        await cq.answer(f"Ошибка отправки в канал: {e}", show_alert=True)
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
    await cq.answer()


# ---------- Clear queue / Change employee ----------
@router.callback_query(F.data == "clear_queue", BossStates.choosing_rooms)
async def clear_queue(cq: CallbackQuery, state: FSMContext):
    await state.update_data(selected_rooms=[])
    data = await state.get_data()
    sm = get_async_session_maker()
    async with sm() as session:
        text, kb = await build_rooms_screen(
            session, data["current_employee"], [], data.get("comment")
        )
    await cq.message.edit_text(text, reply_markup=kb)
    await cq.answer()


@router.callback_query(F.data == "change_employee", BossStates.choosing_rooms)
async def change_employee(cq: CallbackQuery, state: FSMContext):
    await state.set_state(BossStates.choosing_employee)
    await state.update_data(selected_rooms=[], comment=None)
    await cq.message.edit_text(
        "👤 Для кого это задание?\n\nДина, Лена или Оля — кнопки ниже.",
        reply_markup=choose_employee_kb(),
    )
    await cq.answer()


# ---------- Add comment ----------
@router.callback_query(F.data == "add_comment", BossStates.choosing_rooms)
async def add_comment_start(cq: CallbackQuery, state: FSMContext):
    await state.set_state(BossStates.adding_comment)
    await cq.message.edit_text(
        "💬 Введите комментарий к заданию (или отправьте «-» чтобы пропустить):",
        reply_markup=back_kb("cancel_to_menu"),
    )
    await cq.answer()


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
    await cq.answer()


@router.callback_query(F.data.startswith("history_detail_"), BossStates.history_list)
async def history_detail(cq: CallbackQuery, state: FSMContext):
    task_id = int(cq.data.replace("history_detail_", ""))
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Task).where(Task.id == task_id))
        task = result.scalars().first()
    if not task:
        await cq.answer("Задание не найдено.")
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
        extra = ""
        if resolve_linen_profile(r) == "floor4" and r.get("linen_variant") is not None:
            lc = format_linen_color(r.get("linen_color"))
            if lc:
                extra = f", комплект {r.get('linen_variant')} ({lc})"
        lines.append(f"  {i}. {r.get('name', '')} — {r.get('area', 0):.0f} м² — {ct}{extra}")
    if task.comment:
        lines.append("")
        lines.append(f"💬 {task.comment}")
    await cq.message.edit_text("\n".join(lines), reply_markup=history_detail_back_kb())
    await cq.answer()


# ---------- Channel link ----------
@router.callback_query(F.data == "channel_link", BossStates.main_menu)
async def channel_link(cq: CallbackQuery):
    await cq.answer()
    await cq.message.answer(f"🔗 Ссылка на канал: {config.CHANNEL_LINK}")


# ---------- Room management ----------
@router.callback_query(F.data == "rooms_manage", BossStates.main_menu)
async def rooms_manage(cq: CallbackQuery, state: FSMContext):
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
    await cq.answer()


@router.callback_query(F.data == "rooms_manage")
async def back_to_rooms_manage(cq: CallbackQuery, state: FSMContext):
    """Return to room management from add/edit flows."""
    cur = await state.get_state()
    if cur not in (BossStates.room_add_name.state, BossStates.room_add_area.state, BossStates.room_edit_area.state):
        await cq.answer()
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
        builder.row(InlineKeyboardButton(text=f"✏️ {r.name}", callback_data=f"room_edit_{r.id}"), InlineKeyboardButton(text="🔴 Откл" if r.is_active else "🟢 Вкл", callback_data=f"room_toggle_{r.id}"))
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="cancel_to_menu"))
    await cq.message.edit_text("\n".join(lines), reply_markup=builder.as_markup())
    await cq.answer()


@router.callback_query(F.data == "room_add", BossStates.room_management)
async def room_add_start(cq: CallbackQuery, state: FSMContext):
    await state.set_state(BossStates.room_add_name)
    await cq.message.edit_text(
        "Введите название помещения:",
        reply_markup=back_kb("rooms_manage"),
    )
    await cq.answer()


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
    room_id = int(cq.data.replace("room_edit_", ""))
    await state.update_data(editing_room_id=room_id)
    await state.set_state(BossStates.room_edit_area)
    await cq.message.edit_text(
        "Введите новую площадь (число):",
        reply_markup=back_kb("rooms_manage"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("room_edit_area_"), BossStates.room_management)
async def room_edit_area_start(cq: CallbackQuery, state: FSMContext):
    room_id = int(cq.data.replace("room_edit_area_", ""))
    await state.update_data(editing_room_id=room_id)
    await state.set_state(BossStates.room_edit_area)
    await cq.message.edit_text(
        "Введите новую площадь (число):",
        reply_markup=back_kb("rooms_manage"),
    )
    await cq.answer()


@router.callback_query(F.data.startswith("room_toggle_"), BossStates.room_management)
async def room_toggle(cq: CallbackQuery, state: FSMContext):
    room_id = int(cq.data.replace("room_toggle_", ""))
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).where(Room.id == room_id))
        room = result.scalars().first()
        if room:
            room.is_active = not room.is_active
            await session.commit()
            status = "включено" if room.is_active else "отключено"
            await cq.answer(f"Помещение {room.name} {status}")
        else:
            await cq.answer("Помещение не найдено.")
    # Refresh list
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
    template_id = int(cq.data.replace("template_apply_", ""))
    data = await state.get_data()
    selected = list(data.get("selected_rooms", []))

    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Template).where(Template.id == template_id))
        template = result.scalars().first()
        if not template:
            await cq.answer("Шаблон не найден.")
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
    await cq.answer()