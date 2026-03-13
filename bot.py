"""Entry point: run the hotel cleaning bot."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery

import config
from database import init_db
from database.seed_rooms import seed_rooms
from handlers import boss_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def boss_only(event: Message | CallbackQuery) -> bool:
    user = event.from_user
    return user is not None and user.id == config.BOSS_ID


async def main():
    # Увеличенный timeout для long polling (getUpdates ждёт до ~60 сек) и нестабильной сети
    session = AiohttpSession(timeout=90.0)
    bot = Bot(token=config.BOT_TOKEN, session=session)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Only boss can use the bot
    dp.include_router(boss_router)

    await init_db()
    await seed_rooms()

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())