"""Database engine and session."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from .models import Base

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
SYNC_URL = f"sqlite:///{DB_PATH}"

_async_engine = None
_async_session_factory = None


def get_engine():
    return create_engine(SYNC_URL, echo=False)


def get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(DATABASE_URL, echo=False)
    return _async_engine


def get_session_maker():
    return sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)


def get_async_session_maker():
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def init_db():
    engine = get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # ensure session maker is created
    get_async_session_maker()
