"""Правила белья и раскладки кроватей по номерам."""
from __future__ import annotations

from typing import Any

# Виды уборки, при которых спрашиваем бельё / кровати
CLEANING_TYPES_NEED_LINEN_FLOW = frozenset({"current_linen", "departure", "departure_arrival"})

# Номера с выбором «разъединены / соединены» (как 101–109)
SPLIT_BED_ROOM_KEYS = {str(n) for n in range(101, 110)} | {"401.1", "402.4", "404.1", "405.4"}

# Подгруппа: бельё зависит от раскладки (две 1,5 или одна двуспальная)
AUTO_LINEN_BY_LAYOUT_ROOMS = {"401.1", "402.4", "404.1", "405.4"}

# Четыре варианта расцветки 1,5 спальных комплектов; значения — на одну кровать (× max кроватей = полный номер)
LINEN_COLOR_VARIANTS: dict[int, dict[str, int]] = {
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

# Полный номер = вариант × max кроватей (на одну кровать — доля от полного)
LINEN_COLOR_MAX_BEDS: dict[str, int] = {}
for k in ("401.3", "401.4", "402.1", "402.2", "404.3", "404.4", "405.1"):
    LINEN_COLOR_MAX_BEDS[k] = 2
for k in ("401.2", "402.3", "404.2", "405.3"):
    LINEN_COLOR_MAX_BEDS[k] = 3
for k in ("403", "405.2"):
    LINEN_COLOR_MAX_BEDS[k] = 4

LINEN_VARIANT_SHORT = {
    1: "бел. 1,5",
    2: "голуб.",
    3: "сер.",
    4: "полоска",
}

SEPARATED_15_FULL: dict[str, int] = {
    "Простыня 1,5 спальная белая": 2,
    "Пододеяльник 1,5 спальный белый": 2,
    "Наволочка белая": 2,
    "Полотенце банное": 2,
    "Полотенце 40х70": 2,
}

JOINED_DOUBLE_KIT: dict[str, int] = {
    "Простыня двуспальная белая": 1,
    "Пододеяльник двуспальный белый": 1,
    "Наволочка белая": 2,
    "Полотенце банное": 2,
    "Полотенце 40х70": 2,
}


def room_key_from_name(name: str) -> str | None:
    if not name.startswith("Номер "):
        return None
    return name[6:].strip()


def cleaning_needs_linen_flow(cleaning_type: str) -> bool:
    return cleaning_type in CLEANING_TYPES_NEED_LINEN_FLOW


def room_needs_bed_layout(room_key: str | None) -> bool:
    return bool(room_key) and room_key in SPLIT_BED_ROOM_KEYS


def room_needs_color_linen(room_key: str | None) -> bool:
    return bool(room_key) and room_key in LINEN_COLOR_MAX_BEDS


def scale_linen_kit(kit: dict[str, int], beds_to_make: int, max_beds: int) -> dict[str, int]:
    if max_beds <= 0:
        return dict(kit)
    out: dict[str, int] = {}
    for item, qty in kit.items():
        out[item] = max(0, (qty * beds_to_make) // max_beds)
    return out


def build_color_variant_full_kit(variant_id: int, max_beds: int) -> dict[str, int]:
    base = LINEN_COLOR_VARIANTS[variant_id]
    return {k: v * max_beds for k, v in base.items()}


def format_linen_lines(linen: dict[str, int] | None) -> list[str]:
    if not linen:
        return []
    return [f"  • {name}: {qty}" for name, qty in sorted(linen.items())]


def format_bed_layout_label(layout: str | None) -> str:
    if layout == "separated":
        return "кровати разъединены"
    if layout == "joined":
        return "кровати соединены"
    return ""


def queue_item_linen_summary(item: dict[str, Any]) -> str:
    parts: list[str] = []
    bl = item.get("bed_layout")
    if bl == "separated":
        parts.append("разъед.")
    elif bl == "joined":
        parts.append("соед.")
    lk = item.get("linen_kit")
    if lk and isinstance(lk, dict):
        beds = item.get("beds_to_make")
        if beds is not None:
            parts.append(f"{beds} кр.")
        vid = item.get("linen_variant")
        if vid:
            parts.append(LINEN_VARIANT_SHORT.get(int(vid), str(vid)))
    return ", ".join(parts)


def describe_queue_item_extra(item: dict[str, Any]) -> str:
    """Короткая строка для строки очереди."""
    s = queue_item_linen_summary(item)
    return f" | {s}" if s else ""
