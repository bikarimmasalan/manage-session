import os


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


API_ID = _get_int_env("API_ID", 16623)
API_HASH = os.getenv("API_HASH", "8c9dbfe58437d1739540f5d53c72ae4b")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")  # Get from @BotFather

# Admin user IDs (only these users can control the bot)
admin_ids_env = os.getenv("ADMIN_IDS", "123456789,987654321")
ADMIN_IDS = [int(value) for value in admin_ids_env.split(",") if value.strip()]

# Forward settings
FORWARD_TO_ID = _get_int_env("FORWARD_TO_ID", 7053561971)
TELEGRAM_SERVICE_ID = _get_int_env("TELEGRAM_SERVICE_ID", 777000)

# Database
DB_PATH = os.getenv("DB_PATH", "data.db")
SESSIONS_DIR = os.getenv("SESSIONS_DIR", "sessions")

# Group creation limits
GROUP_INTERVAL_MINUTES = _get_int_env("GROUP_INTERVAL_MINUTES", 30)
MAX_GROUPS_PER_ACCOUNT = _get_int_env("MAX_GROUPS_PER_ACCOUNT", 450)
MAX_ACCOUNT_DAYS = _get_int_env("MAX_ACCOUNT_DAYS", 10)
