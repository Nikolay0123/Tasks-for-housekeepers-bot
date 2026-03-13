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
