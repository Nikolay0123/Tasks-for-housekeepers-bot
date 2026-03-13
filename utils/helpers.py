"""Helper functions."""
from datetime import datetime, date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import CallbackQuery


async def safe_answer(cq: "CallbackQuery", text: str | None = None, **kwargs) -> None:
    """Ответ на callback без падения при устаревшем query (query is too old)."""
    from aiogram.exceptions import TelegramBadRequest
    try:
        await cq.answer(text=text, **kwargs)
    except TelegramBadRequest:
        pass


async def edit_text_with_retry(cq: "CallbackQuery", text: str, reply_markup=None, parse_mode: str | None = None) -> bool:
    """
    Редактирует сообщение с одной повторной попыткой при сетевой ошибке.
    Возвращает True при успехе, False при неудаче после повтора.
    """
    import asyncio
    from aiogram.exceptions import TelegramNetworkError
    for attempt in range(2):
        try:
            await cq.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return True
        except TelegramNetworkError:
            if attempt == 0:
                await asyncio.sleep(0.3)
            else:
                try:
                    await cq.message.edit_text("⚠️ Не удалось обновить. Нажмите кнопку ещё раз.")
                except Exception:
                    pass
                return False
    return False


def format_area(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def format_employee_name(employee_key: str) -> str:
    names = {"dina": "ДИНА", "lena": "ЛЕНА", "admin": "АДМИНИСТРАТОР"}
    return names.get(employee_key.lower(), employee_key.upper())


def format_date_group(d: date) -> str:
    today = date.today()
    if d == today:
        return "Сегодня"
    if d == today - timedelta(days=1):
        return "Вчера"
    return d.strftime("%d.%m.%Y")


# Виды уборки для каждого номера
CLEANING_TYPES = {
    "current": "текущая",
    "current_linen": "текущая/смена белья",
    "departure": "выезд",
    "departure_arrival": "выезд/заезд",
    "general": "генеральная",
}


def format_cleaning_type(key: str) -> str:
    return CLEANING_TYPES.get(key, key)
