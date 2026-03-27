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


def room_key_from_name(room_name: str) -> str | None:
    """«Номер 401.1» → «401.1», «Номер 403» → «403»."""
    if not isinstance(room_name, str) or not room_name.startswith("Номер "):
        return None
    return room_name.replace("Номер ", "").strip()


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


# Номера 4 этажа: сначала «кровати разъединены / соединены», белые 1,5×2 или двуспальный комплект
FLOOR4_SPLIT_BED_ROOMS: frozenset[str] = frozenset({"401.1", "402.4", "404.1", "405.4"})

# Макс. кроватей в номере для вариантов расцветки 1–4 (не включает split-номера выше)
FLOOR4_COLOR_MAX_BEDS: dict[str, int] = {}
for _k in ("401.3", "401.4", "402.1", "402.2", "404.3", "404.4", "405.1"):
    FLOOR4_COLOR_MAX_BEDS[_k] = 2
for _k in ("401.2", "402.3", "404.2", "405.3"):
    FLOOR4_COLOR_MAX_BEDS[_k] = 3
for _k in ("403", "405.2"):
    FLOOR4_COLOR_MAX_BEDS[_k] = 4

# Вариант комплекта (1–4) → ключ цвета для блока «по цвету» в канале
FLOOR4_VARIANT_TO_COLOR_KEY: dict[int, str] = {
    1: "white",
    2: "blue",
    3: "gray",
    4: "stripe",
}

# Единица белья на одну кровать (вариции расцветки по ТЗ)
FLOOR4_COLOR_UNIT: dict[int, dict[str, int]] = {
    1: {
        "Простыня 1,5 спальная белая": 1,
        "Пододеяльник 1,5 спальный белый": 1,
        "Наволочка белая": 1,
        "Полотенце банное": 1,
        "Полотенце 40х70": 1,
    },
    2: {
        "Простыня 1,5 спальная голубая": 1,
        "Пододеяльник 1,5 спальный голубой": 1,
        "Наволочка голубая": 1,
        "Полотенце банное": 1,
        "Полотенце 40х70": 1,
    },
    3: {
        "Простыня 1,5 спальная серая": 1,
        "Пододеяльник 1,5 спальный серый": 1,
        "Наволочка серая": 1,
        "Полотенце банное": 1,
        "Полотенце 40х70": 1,
    },
    4: {
        "Простыня 1,5 спальная в полоску": 1,
        "Пододеяльник 1,5 спальный в полоску": 1,
        "Наволочка в полоску": 1,
        "Полотенце банное": 1,
        "Полотенце 40х70": 1,
    },
}

# 401.1 / …: разъединённые кровати — комплект 1,5 белый на две кровати (полный номер)
FLOOR4_SPLIT_SEPARATED_FULL: dict[str, int] = {
    "Простыня 1,5 спальная белая": 2,
    "Пододеяльник 1,5 спальный белый": 2,
    "Наволочка белая": 2,
    "Полотенце банное": 2,
    "Полотенце 40х70": 2,
}

FLOOR4_SPLIT_JOINED_KIT: dict[str, int] = {
    "Простыня двуспальная белая": 1,
    "Пододеяльник двуспальный белый": 1,
    "Наволочка белая": 2,
    "Полотенце банное": 2,
    "Полотенце 40х70": 2,
}


def floor4_color_max_beds(room_key: str | None) -> int | None:
    if not room_key:
        return None
    return FLOOR4_COLOR_MAX_BEDS.get(room_key)


def floor4_color_kit_full(variant_id: int, max_beds: int) -> dict[str, int]:
    unit = FLOOR4_COLOR_UNIT[variant_id]
    return {k: v * max_beds for k, v in unit.items()}


def scale_linen_by_beds(kit: dict[str, int], beds_to_make: int, max_beds: int) -> dict[str, int]:
    if max_beds <= 0:
        return dict(kit)
    return {k: max(0, (q * beds_to_make) // max_beds) for k, q in kit.items()}


def _legacy_floor4_pkg(item: dict) -> dict[str, int] | None:
    """Старый формат: linen_variant ∈ {1,2,3} — множитель + linen_color."""
    v = item.get("linen_variant")
    if not isinstance(v, int) or v not in LINEN_PACKAGES_FLOOR4:
        return None
    if not item.get("linen_color"):
        return None
    return dict(LINEN_PACKAGES_FLOOR4[v])


def item_linen_totals(item: dict) -> dict[str, int] | None:
    """Словарь позиций белья для строки очереди (новый linen_kit, classic, старый floor4)."""
    lk = item.get("linen_kit")
    if isinstance(lk, dict) and lk:
        return {str(k): int(v) for k, v in lk.items() if int(v) > 0}

    prof = resolve_linen_profile(item)
    if prof == "classic":
        return classic_linen_quantities(item)

    if prof == "floor4":
        leg = _legacy_floor4_pkg(item)
        if leg:
            return leg
    return None


def item_linen_color_key(item: dict) -> str | None:
    """
    Ключ LINEN_COLORS для вклада в сводку «по цвету» (white / blue / …).
    """
    if item.get("linen_kit") and resolve_linen_profile(item) == "floor4":
        rk = room_key_from_name(item.get("name") or "")
        if rk and rk in FLOOR4_SPLIT_BED_ROOMS:
            return "white"
        v = item.get("linen_variant")
        if isinstance(v, int) and v in FLOOR4_VARIANT_TO_COLOR_KEY:
            return FLOOR4_VARIANT_TO_COLOR_KEY[v]
        return None
    ck = item.get("linen_color")
    if ck in LINEN_COLORS:
        return ck
    if resolve_linen_profile(item) == "classic" and item_linen_totals(item):
        return "white"
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


LINEN_FOOT_TOWEL = "Полотенце для ног"


def classic_linen_quantities(queue_item: dict) -> dict[str, int] | None:
    """
    Фактические количества белья для classic (101–109) с учётом варианта.
    Вариант 2: при linen_beds == 1 количества в 2 раза меньше (целочисленно);
    для «Полотенце для ног» — не меньше 1 шт., если в комплекте оно есть (qty > 0).
    """
    v = queue_item.get("linen_variant")
    if not isinstance(v, int) or v not in LINEN_PACKAGES:
        return None
    base = LINEN_PACKAGES[v]
    if v == 2:
        beds = queue_item.get("linen_beds", 2)
        if beds not in (1, 2):
            beds = 2
        if beds == 1:
            scaled: dict[str, int] = {}
            for k, q in base.items():
                if k == LINEN_FOOT_TOWEL and q > 0:
                    scaled[k] = max(1, q // 2)
                else:
                    scaled[k] = max(0, q // 2)
            return scaled
    return dict(base)


def classic_variant2_beds_label(beds: int | None) -> int:
    """1 или 2 кровати для отображения; по умолчанию 2 (старые записи)."""
    if beds == 1:
        return 1
    return 2


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
        "Наволочка": 2,
        "Полотенце банное с вышивкой": 2,
        "Полотенце для лица": 2,
        "Полотенце для ног": 1,
    },
    3: {
        "Простыня люкс": 1,
        "Пододеяльник люкс": 1,
        "Наволочка с люкс (с вышивкой)": 4,
        "Полотенце банное с вышивкой": 2,
        "Полотенце для лица": 2,
        "Полотенце для ног": 1,
    },
    4: {
        "Простыня люкс": 1,
        "Пододеяльник двуспальный": 1,
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
        "Наволочка": 2,
        "Полотенце банное": 2,
        "Полотенце 40х70": 2,
    },
    2: {
        "Простыня 1,5 спальная": 3,
        "Пододеяльник 1,5 спальный": 3,
        "Наволочка": 3,
        "Полотенце банное": 3,
        "Полотенце 40х70": 3,
    },
    3: {
        "Простыня 1,5 спальная": 4,
        "Пододеяльник 1,5 спальный": 4,
        "Наволочка": 4,
        "Полотенце банное": 4,
        "Полотенце 40х70": 4,
    },
}
