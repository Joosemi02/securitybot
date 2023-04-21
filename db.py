import json
import os
from datetime import datetime

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
        self.warns = db.warns

        # Cache
        prefs = self.guilds.find({})
        self.guilds_cache = {
            d["_id"]: {k: v for k, v in d.items() if k != "_id"} async for d in prefs
        }

        self.translations = load_languages()

    async def warn(self, guild_id: int, user_id: int, reason: str):
        if (
            warns := await self.warns.find_one({"_id": user_id, "guild": guild_id})
        ) is None:
            warns = {
                "_id": user_id,
                "guild": guild_id,
                "0": {reason: datetime.now()},
            }
            await self.warns.insert_one(warns)
        else:
            num = list(warns.keys())[-1]
            await self.warns.update_one(
                {"_id": user_id, "guild": guild_id},
                {"$set": {str(num + 1): {reason: datetime.now()}}},
            )

    # REVIEW Unused
    async def set_default_prefs(self, guild_id: int):
        settings = DEFAULT_GUILD_SETTINGS.copy()
        settings["_id"] = guild_id
        await self.guilds.insert_one(settings)
        self.guilds_cache[guild_id] = settings
        return settings

    # REVIEW Unused
    async def set_guild_data(self, guild_id, field, value):
        await self.guilds.update_one({"_id": guild_id}, {"$set": {field: value}})
        self.guilds_cache[guild_id][field] = value


db = Database(MONGODB_CONNECTION_STR)
