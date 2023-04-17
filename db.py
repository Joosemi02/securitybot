from motor import motor_tornado

from constants import DEFAULT_GUILD_SETTINGS, MONGODB_CONNECTION_STR


class Database:
    async def __init__(self, url):
        db = motor_tornado.MotorClient(url)["security"]
        self.guilds = db.guilds

        prefs = self.guilds.find({})
        self.guilds_cache = {
            d["_id"]: {k: v for k, v in d.items() if k != "_id"} async for d in prefs
        }

    def get_guild_lang(self, guild_id: int):
        return self.guilds_cache[guild_id]["lang"]

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
