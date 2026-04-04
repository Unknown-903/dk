import os
import logging
from logging.handlers import RotatingFileHandler

# ── Core credentials ───────────────────────────────────────────────────────────
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
APP_ID       = int(os.environ.get("APP_ID", "0"))
API_HASH     = os.environ.get("API_HASH", "")

# ── DB channel where files are stored ─────────────────────────────────────────
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1002864509771"))

# ── Owner ──────────────────────────────────────────────────────────────────────
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

# ── MongoDB ────────────────────────────────────────────────────────────────────
DB_URI  = os.environ.get("DATABASE_URL", "")
DB_NAME = os.environ.get("DATABASE_NAME", "filestorebot")

# ── Web server ─────────────────────────────────────────────────────────────────
PORT = int(os.environ.get("PORT", "8080"))

# ── Workers ────────────────────────────────────────────────────────────────────
TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))

# ── Start / force-sub images ───────────────────────────────────────────────────
START_PIC = os.environ.get("START_PIC", "")
FORCE_PIC = os.environ.get("FORCE_PIC", "")

# ── Messages ───────────────────────────────────────────────────────────────────
START_MSG  = os.environ.get("START_MESSAGE", "<b>Hello {first}!\n\nI am a File Store Bot. Send me a file and I'll give you a shareable link.</b>")
FORCE_MSG  = os.environ.get("FORCE_SUB_MESSAGE", "<b>Hello {first}!\n\nPlease join our channels first, then click Reload.</b>")
HELP_TXT   = os.environ.get("HELP_TEXT", "<b>📌 Commands:\n/start – Start the bot\n/status – Bot status\n/rank – Upload leaderboard</b>")
ABOUT_TXT  = os.environ.get("ABOUT_TEXT", "<b>File Store Bot\nOwner: {first}</b>")

# ── Protect content ────────────────────────────────────────────────────────────
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False") == "True"

# ── ADMINS list (loaded from DB at runtime; this is only a seed) ───────────────
ADMINS: list[int] = [OWNER_ID]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE = "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=50_000_000, backupCount=5),
        logging.StreamHandler(),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
