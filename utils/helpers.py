"""Helper functions."""
import re
from datetime import datetime, date, timedelta


def format_area(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def format_employee_name(employee_key: str) -> str:
    names = {"dina": "ДИНА", "lena": "ЛЕНА", "olya": "ОЛЯ", "admin": "АДМИНИСТРАТОР"}
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


def room_linen_profile(room_name: str) -> str | None:
    """
    None — без выбора комплекта белья в сценарии бота.
    classic — номера 101–109 (кровати / люкс).
    floor4 — номера 401.x, 402.x, 403, 404.x, 405.x.
    """
    if not isinstance(room_name, str) or not room_name.startswith("Номер "):
        return None
    rest = room_name.replace("Номер ", "").strip()
    if rest.isdigit():
        n = int(rest)
        if 101 <= n <= 109:
            return "classic"
        if n == 403:
            return "floor4"
        return None
    m = re.match(r"^(\d+)(?:\.(\d+))?$", rest)
    if not m:
        return None
    major_s, minor_s = m.group(1), m.group(2)
    major = int(major_s)
    if major == 403 and minor_s is None:
        return "floor4"
    if major in (401, 402, 404, 405) and minor_s is not None:
        minor = int(minor_s)
        if 1 <= minor <= 4:
            return "floor4"
    return None


# Цвет белья (4 этаж); «белое» — и для 4 этажа, и считается для комплектов 101–109 в итоге
LINEN_COLORS: dict[str, str] = {
    "blue": "голубое",
    "gray": "серое",
    "stripe": "в полоску",
    "white": "белое",
}

# Порядок строк в сводке «по цвету» в сообщении в канал
LINEN_COLOR_ORDER: tuple[str, ...] = ("blue", "gray", "stripe", "white")


def format_linen_color(key: str | None) -> str:
    if not key:
        return ""
    return LINEN_COLORS.get(key, key)


def resolve_linen_profile(queue_item: dict) -> str | None:
    """Профиль комплекта для строки очереди (с учётом старых записей без linen_profile)."""
    p = queue_item.get("linen_profile")
    if p in ("classic", "floor4"):
        return p
    return room_linen_profile(queue_item.get("name") or "")


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

# Комплекты белья для номеров 401–405 (4 этаж): варианты 1/2/3 — множитель 2/3/4 на каждую позицию
LINEN_PACKAGES_FLOOR4: dict[int, dict[str, int]] = {
    1: {
        "Простыня 1,5 спальная": 2,
        "Пододеяльник 1,5 спальный": 2,
        "Полотенце банное": 2,
        "Полотенце 40х70": 2,
    },
    2: {
        "Простыня 1,5 спальная": 3,
        "Пододеяльник 1,5 спальный": 3,
        "Полотенце банное": 3,
        "Полотенце 40х70": 3,
    },
    3: {
        "Простыня 1,5 спальная": 4,
        "Пододеяльник 1,5 спальный": 4,
        "Полотенце банное": 4,
        "Полотенце 40х70": 4,
    },
}
