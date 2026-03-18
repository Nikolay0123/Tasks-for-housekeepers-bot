"""Helper functions."""
from datetime import datetime, date, timedelta


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


# Комплекты белья для номеров 101–109
# Ключ — номер варианта, значение — словарь "Наименование" → количество
LINEN_PACKAGES: dict[int, dict[str, int]] = {
    1: {
        "Простыня двуспальная": 1,
        "Пододеяльник двуспальный": 1,
        "Наволочка": 2,
        "Полотенце банное с вышивкой": 2,
        "Полотенце для лица": 2,
        "Полотенце для ног": 1,
    },
    2: {
        "Простыня 1,5 спальная": 2,
        "Пододеяльник 1,5 спальный": 2,
        "Полотенце банное с вышивкой": 2,
        "Полотенце для лица": 2,
        "Полотенце для ног": 1,
    },
    3: {
        "Простыня люкс": 1,
        "Пододеяльник люкс": 1,
        "Наволочка с люкс (с вышивкой)": 2,
        "Наволочка": 2,
        "Полотенце банное с вышивкой": 2,
        "Полотенце для лица": 2,
        "Полотенце для ног": 1,
    },
}
