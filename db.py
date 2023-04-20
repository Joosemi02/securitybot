import json
import os

from motor import motor_tornado

from constants import DEFAULT_GUILD_SETTINGS, MONGODB_CONNECTION_STR


def load_languages():
    translations = {}
    for filename in os.listdir("langs"):
        if filename.endswith(".json"):
            lang = filename[:-5]
            with open(f"translations/{filename}", "r") as f:
                translations[lang] = json.load(f)
    return translations


class Database:
    async def __init__(self, url):
        # Collections
        db = motor_tornado.MotorClient(url)["security"]
        self.guilds = db.guilds

        # Cache
        prefs = self.guilds.find({})
        self.guilds_cache = {
            d["_id"]: {k: v for k, v in d.items() if k != "_id"} async for d in prefs
        }

        self.translations = load_languages()

    async def set_default_prefs(self, guild_id: int):
        settings = DEFAULT_GUILD_SETTINGS.copy()
        settings["_id"] = guild_id
        await self.guilds.insert_one(settings)
        self.guilds_cache[guild_id] = settings
        return settings

    async def set_guild_data(self, guild_id, field, value):
        await self.guilds.update_one({"_id": guild_id}, {"$set": {field: value}})
        self.guilds_cache[guild_id][field] = value


db = Database(MONGODB_CONNECTION_STR)
