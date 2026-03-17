"""Seed initial rooms. Run once or from bot startup if table empty."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from database.db import get_async_engine, get_async_session_maker, init_db
from database.models import Room


# Помещения и площади (актуальный список)
INITIAL_ROOMS = [
    ("Кабинет директора", 12.54),
    ("Кабинет администрации", 12.54),
    ("1 этаж", 109.84),
    ("Комната администраторов", 23.97),
    ("Лестница до 5 этажа", 76.62),
    ("2 этаж", 96.3),
    ("3 этаж", 96.0),
    ("Номер 101", 17.03),
    ("Номер 102", 22.04),
    ("Номер 103", 25.54),
    ("Номер 104", 23.18),
    ("Номер 105", 26.1),
    ("Номер 106", 22.04),
    ("Номер 107", 17.91),
    ("Номер 108", 44.44),
    ("Номер 109", 22.44),
    ("Номер 404.1", 13.0),
    ("Номер 404.2", 11.7),
    ("Номер 404.3", 10.9),
    ("Номер 404.4", 12.0),
    ("Номер 405.1", 11.7),
    ("Номер 405.2", 12.7),
    ("Номер 405.3", 12.2),
    ("Номер 405.4", 12.3),
    ("Номер 403", 22.8),
    ("Номер 401.1", 12.9),
    ("Номер 401.2", 11.8),
    ("Номер 401.3", 11.7),
    ("Номер 401.4", 11.8),
    ("Номер 402.1", 12.0),
    ("Номер 402.2", 11.9),
    ("Номер 402.3", 12.0),
    ("Номер 402.4", 13.1),
    ("Холл 4 этаж", 31.8),
    ("Блок 401, 402", 109.6),
    ("Блок 404,405", 109.2),
    ("Кухня", 51.01),
]


async def seed_rooms():
    await init_db()
    sm = get_async_session_maker()
    async with sm() as session:
        result = await session.execute(select(Room).limit(1))
        if result.scalars().first() is not None:
            print("Rooms already exist, skip seed.")
            return
        for name, area in INITIAL_ROOMS:
            room = Room(name=name, area=area, is_active=True)
            session.add(room)
        await session.commit()
        print(f"Seeded {len(INITIAL_ROOMS)} rooms.")


if __name__ == "__main__":
    asyncio.run(seed_rooms())
