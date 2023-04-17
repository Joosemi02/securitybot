from motor import motor_tornado

from constants import DEFAULT_GUILD_SETTINGS, MONGODB_CONNECTION_STR


class Database:
    def __init__(self, url):
        db = motor_tornado.MotorClient(url)["security"]
        self.guilds = db.guilds

        self.guilds_cache = {}

    async def get_guild_lang(self, guild_id: int):
        if guild_id not in self.guilds_cache:
            prefs = await self.guilds.find_one({"_id": guild_id})
            if prefs is not None:
                self.guilds_cache[guild_id] = prefs
            else:
                self.guilds_cache[guild_id] = await self.set_default_prefs(guild_id)
        return self.guilds_cache[guild_id]["lang"]

    async def set_default_prefs(self, guild_id: int):
        settings = DEFAULT_GUILD_SETTINGS.copy()
        settings["_id"] = guild_id
        await self.guilds.insert_one(settings)
        return settings

    async def set_guild_data(self, guild_id, field, value):
        await self.guilds.update_one({"_id": guild_id}, {"$set": {field: value}})
        self.guilds_cache[guild_id][field] = value


db = Database(MONGODB_CONNECTION_STR)
