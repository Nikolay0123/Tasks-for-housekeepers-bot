"""Entry point: run the hotel cleaning bot."""
import asyncio
import logging

import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery
from aiogram.utils.backoff import BackoffConfig

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
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Only boss can use the bot
    dp.include_router(boss_router)

    await init_db()
    await seed_rooms()

    logger.info("Bot starting...")

    backoff_config = BackoffConfig(min_delay=1.0, max_delay=120.0, factor=1.5, jitter=0.2)

    # If long polling ends due to network issues, we recreate the bot and continue polling
    # instead of exiting the process.
    attempt = 0
    while True:
        attempt += 1
        bot = Bot(token=config.BOT_TOKEN)
        try:
            logger.info("Starting polling (attempt %s)...", attempt)
            await dp.start_polling(
                bot,
                polling_timeout=30,
                backoff_config=backoff_config,
                handle_signals=False,
                close_bot_session=False,
            )
            logger.warning("Polling stopped unexpectedly; reconnecting...")
        except asyncio.CancelledError:
            raise
        except (TelegramNetworkError, aiohttp.ClientError, asyncio.TimeoutError, OSError, ConnectionError) as e:
            logger.warning("Polling ended due to network error: %r", e)
        finally:
            await bot.session.close()

        # aiogram already applies internal backoff; keep this delay small.
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())