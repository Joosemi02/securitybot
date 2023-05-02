import os

from dotenv import load_dotenv

load_dotenv()

MONGODB_CONNECTION_URI = os.getenv("MONGO")
APPLICATION_ID = int(os.getenv("APP"))
TOKEN = os.getenv("TOKEN")

ADMINS = [int(os.getenv("ID"))]

EMBED_COLOR = 0x000
DEFAULT_GUILD_SETTINGS = {
    "lang": "en",
    "logs": 0,
    "antispam": {"enabled": False, "punishments": [], "notify": 0},
    "suspicious_joins": 0,
    "antiraid": {"enabled": False, "punishments": []},
    "link_filter": {"enabled": False, "punishments": []},
}

MAX_CLEAR_AMOUNT = 300
