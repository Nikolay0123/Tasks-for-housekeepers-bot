"""Entry point: run the hotel cleaning bot."""
import asyncio
import logging

import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import ExceptionTypeFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent, Message, CallbackQuery
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

# Дефолтный клиент aiogram часто ~60 с — при медленном канале edit_message падает по таймауту.
# Важно: число секунд, не aiohttp.ClientTimeout — иначе start_polling падает:
# int(bot.session.timeout + polling_timeout) не работает с ClientTimeout.
TELEGRAM_HTTP_TIMEOUT_SECONDS = 180.0


def boss_only(event: Message | CallbackQuery) -> bool:
    user = event.from_user
    return user is not None and user.id == config.BOSS_ID


async def main():
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Only boss can use the bot
    dp.include_router(boss_router)

    @dp.error(ExceptionTypeFilter(TelegramNetworkError))
    async def on_telegram_network_error(event: ErrorEvent) -> bool:
        """Не оставляем callback без ответа при таймауте к Telegram API."""
        logger.warning(
            "TelegramNetworkError while handling update: %s",
            event.exception,
            exc_info=event.exception,
        )
        cq = event.update.callback_query
        if cq:
            try:
                await cq.answer(
                    "Таймаут сети к Telegram. Повторите нажатие кнопки.",
                    show_alert=True,
                )
            except Exception as ans_err:
                logger.debug("Could not answer callback after network error: %r", ans_err)
        return True

    await init_db()
    await seed_rooms()

    logger.info("Bot starting...")

    backoff_config = BackoffConfig(min_delay=1.0, max_delay=120.0, factor=1.5, jitter=0.2)

    # If long polling ends due to network issues, we recreate the bot and continue polling
    # instead of exiting the process.
    attempt = 0
    while True:
        attempt += 1
        session = AiohttpSession(timeout=TELEGRAM_HTTP_TIMEOUT_SECONDS)
        bot = Bot(token=config.BOT_TOKEN, session=session)
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