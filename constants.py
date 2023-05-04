import os

from dotenv import load_dotenv

load_dotenv()

MONGODB_CONNECTION_URI = os.getenv("MONGO")
APPLICATION_ID = int(os.getenv("APP"))
TOKEN = os.getenv("TOKEN")

ADMINS = [int(os.getenv("ID1")), int(os.getenv("ID2"))]

EMBED_COLOR = 0x3498DB

MAX_CLEAR_AMOUNT = 300

BUG_REPORT_CHANNEL = int(os.getenv("BUG"))

LANGUAGES = {"English": "en"}

INVITE_LINK = "https://google.com"
SUPPORT_SERVER = "https://google.com"