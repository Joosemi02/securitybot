import os

from dotenv import load_dotenv

load_dotenv()

MONGODB_CONNECTION_URI = os.getenv("MONGO")
APPLICATION_ID = int(os.getenv("APP"))
TOKEN = os.getenv("TOKEN")

ADMINS = [int(os.getenv("ID"))]

EMBED_COLOR = 0x000
DEFAULT_GUILD_SETTINGS = {"lang": "en", "logs": 0, "raid": False}

MAX_CLEAR_AMOUNT = 300
