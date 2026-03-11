"""Configuration from environment."""
import os
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str | None = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Missing required env variable: {key}")
    return value


BOT_TOKEN = get_env("BOT_TOKEN")
BOSS_ID = int(get_env("BOSS_ID"))
CHANNEL_ID = get_env("CHANNEL_ID")  # can be int or str with -100...
CHANNEL_LINK = get_env("CHANNEL_LINK", "https://t.me/your_channel")

# Constants
AREA_LIMIT = 375.0
BOSS_NAME = "Екатерина"
