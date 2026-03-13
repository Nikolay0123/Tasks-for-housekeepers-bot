"""Entry point: run the hotel cleaning bot."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
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


class RetryAiohttpSession(AiohttpSession):
    """Сессия с повторными попытками при ServerDisconnectedError и других сетевых сбоях."""

    def __init__(self, max_retries: int = 2, retry_delays: tuple[float, ...] = (0.2, 0.5), **kwargs) -> None:
        super().__init__(**kwargs)
        self._max_retries = max(1, max_retries)
        self._retry_delays = retry_delays

    async def make_request(self, bot: Bot, method, timeout: int | None = None):
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return await super().make_request(bot, method, timeout)
            except TelegramNetworkError as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    delay = self._retry_delays[attempt] if attempt < len(self._retry_delays) else 0.5
                    logger.warning(
                        "Telegram request failed (%s), retry in %.2fs (%d/%d)",
                        e.message, delay, attempt + 1, self._max_retries,
                    )
                    await asyncio.sleep(delay)
        raise last_error


async def main():
    # Увеличенный timeout для long polling (getUpdates ждёт до ~60 сек) и нестабильной сети
    session = RetryAiohttpSession(timeout=90.0, max_retries=2, retry_delays=(0.2, 0.5))
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