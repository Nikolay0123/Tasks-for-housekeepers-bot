"""Entry point: run the hotel cleaning bot."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
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
    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Only boss can use the bot
    dp.include_router(boss_router, boss_only)

    await init_db()
    await seed_rooms()

    logger.info("Bot starting...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())