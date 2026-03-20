"""Inline keyboards for boss bot."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 СОЗДАТЬ НОВОЕ ЗАДАНИЕ", callback_data="create_task"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 ИСТОРИЯ ЗАДАНИЙ", callback_data="history"),
    )
    builder.row(
        InlineKeyboardButton(text="🏨 УПРАВЛЕНИЕ ПОМЕЩЕНИЯМИ", callback_data="rooms_manage"),
    )
    builder.row(
        InlineKeyboardButton(text="🔗 ССЫЛКА НА КАНАЛ", callback_data="channel_link"),
    )
    return builder.as_markup()


def choose_employee_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👩 ДИНА", callback_data="emp_dina"),
        InlineKeyboardButton(text="👩 ЛЕНА", callback_data="emp_lena"),
    )
    builder.row(
        InlineKeyboardButton(text="👩 ОЛЯ", callback_data="emp_olya"),
    )
    builder.row(
        InlineKeyboardButton(text="🔙 ОТМЕНА", callback_data="cancel_to_menu"),
    )
    return builder.as_markup()


def back_kb(callback_data: str = "cancel_to_menu") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data=callback_data))
    return builder.as_markup()


def history_back_kb() -> InlineKeyboardMarkup:
    return back_kb("history_back")


def send_clear_back_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ ОТПРАВИТЬ ЗАДАНИЕ", callback_data="send_task"),
        InlineKeyboardButton(text="💬 Комментарий", callback_data="add_comment"),
    )
    builder.row(
        InlineKeyboardButton(text="❌ ОЧИСТИТЬ ВСЁ", callback_data="clear_queue"),
        InlineKeyboardButton(text="🔙 ДРУГОЙ СОТРУДНИК", callback_data="change_employee"),
    )
    return builder.as_markup()


def room_management_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить помещение", callback_data="room_add"),
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="cancel_to_menu"))
    return builder.as_markup()


def room_edit_actions_kb(room_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Площадь", callback_data=f"room_edit_area_{room_id}"),
        InlineKeyboardButton(text="🔴 Отключить", callback_data=f"room_toggle_{room_id}"),
    )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="rooms_manage"))
    return builder.as_markup()


def rooms_list_kb(rooms: list, selected_ids: set, limit: float, current_total: float) -> InlineKeyboardMarkup:
    """Rooms as buttons: room_<id>. If room in selected_ids, show differently or skip (we show in queue)."""
    builder = InlineKeyboardBuilder()
    for r in rooms:
        if not r.is_active:
            continue
        can_add = (current_total + r.area) <= limit
        suffix = " ✓" if r.id in selected_ids else ""
        text = f"{r.name} ({r.area:.2f} м²){suffix}"
        if can_add:
            builder.row(
                InlineKeyboardButton(text=text, callback_data=f"room_add_{r.id}"),
            )
        else:
            builder.row(
                InlineKeyboardButton(text=f"{text} (лимит)", callback_data="limit_exceeded"),
            )
    return builder.as_markup()


def queue_kb(queue: list) -> InlineKeyboardMarkup:
    """Queue: each item has up, down, remove."""
    builder = InlineKeyboardBuilder()
    for i, item in enumerate(queue):
        name, area = item.get("name", ""), item.get("area", 0)
        row = [
            InlineKeyboardButton(text="⬆️", callback_data=f"queue_up_{i}"),
            InlineKeyboardButton(text=f"{name} — {area:.0f} м²", callback_data="noop"),
            InlineKeyboardButton(text="⬇️", callback_data=f"queue_down_{i}"),
            InlineKeyboardButton(text="❌", callback_data=f"queue_del_{i}"),
        ]
        builder.row(*row)
    return builder.as_markup()


def templates_kb(templates: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for t in templates:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {t.name} — {t.total_area:.0f} м²",
                callback_data=f"template_apply_{t.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 НАЗАД", callback_data="change_employee"))
    return builder.as_markup()


def after_send_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📝 СОЗДАТЬ НОВОЕ ЗАДАНИЕ", callback_data="create_task"),
        InlineKeyboardButton(text="📋 ИСТОРИЯ", callback_data="history"),
    )
    return builder.as_markup()


def history_item_kb(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Подробнее", callback_data=f"history_detail_{task_id}"),
    )
    return builder.as_markup()


def history_detail_back_kb() -> InlineKeyboardMarkup:
    return back_kb("history_back")
