import json
import os
from datetime import datetime

import discord
from discord import Interaction
from discord.ext import commands
from discord.utils import format_dt
from motor import motor_tornado

from constants import (
    ADMINS,
    DEFAULT_GUILD_SETTINGS,
    EMBED_COLOR,
    LANGUAGES,
    MONGODB_CONNECTION_URI,
)


# CLASSES
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        self.translations = load_languages()
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        prefs = db.guilds.find({})
        global guilds_cache
        guilds_cache = {
            d["_id"]: {k: v for k, v in d.items() if k != "_id"} async for d in prefs
        }

    async def log(self, object_: Interaction | tuple[int, discord.User], msg: str):
        if isinstance(object_, Interaction):
            guild_id = object_.guild_id
            user = object_.user
        else:
            guild_id, user = object_

        if channel := self.get_channel(guilds_cache[guild_id]["logs"]):
            log_embed = embed_info(msg)
            log_embed.add_field(
                name=_T(guild_id, ""),
                value=f"{user.name}#{user.discriminator}\nID: ``{user.id}``",
            )
            log_embed.set_footer(text=format_dt(datetime.now()))
            await channel.send(log_embed)


# DATABASE
db = motor_tornado.MotorClient(MONGODB_CONNECTION_URI)["security"]
guilds_cache = {}


async def set_guild_data(guild_id, field, value):
    await db.guilds.update_one({"_id": guild_id}, {"$set": {field: value}})
    guilds_cache[guild_id][field] = value


async def set_default_prefs(guild_id: int):
    if (data := await db.guilds.find_one({"_id": guild_id})) is None:
        settings = DEFAULT_GUILD_SETTINGS.copy()
        settings["_id"] = guild_id
        await db.guilds.insert_one(settings)
        guilds_cache[guild_id] = settings
    else:
        del data["_id"]
        guilds_cache[guild_id] = data


def get_punishments(guild_id: int, category: str):
    return guilds_cache[guild_id][category]["punishments"]


def get_guild_prefs(guild_id: int, key):
    return guilds_cache[guild_id][key]


async def configure_punihsments(guild_id, category: str, punishment: str):
    if punishment == "disabled":
        await db.guilds.update_one(
            {"_id": guild_id}, {"$set": {f"{category}.enabled": False}}
        )
        guilds_cache[guild_id][category]["enabled"] = False
    else:
        await db.guilds.update_one(
            {"_id": guild_id},
            {
                "$set": {
                    f"{category}.enabled": True,
                    f"{category}.punishments": [punishment],
                }
            },
        )
        guilds_cache[guild_id][category]["enabled"] = True
        guilds_cache[guild_id][category]["punishments"] = [punishment]


# TRANSLATIONS
def load_languages():
    translations = {}
    for lang in LANGUAGES.values():
        with open(f"langs/{lang}.json", "r", encoding="utf-8") as f:
            translations[lang] = json.load(f)
    return translations


translations = load_languages()


def _T(
    object_: discord.Interaction | commands.Context | discord.Guild | int,
    key: str,
    **kwargs,
) -> str:
    guild_id = get_guild_id(object_)
    lang = guilds_cache[guild_id]["lang"]

    keys = key.split(".")
    value = translations[lang]
    for k in keys:
        value: dict | str = value[k]
    return value.format(**kwargs)


def get_guild_id(object_):
    if isinstance(object_, (discord.Interaction, commands.Context)):
        return object_.guild.id
    elif isinstance(object_, discord.Guild):
        return object_.id
    else:
        return object_


# FORMAT
def embed_info(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=EMBED_COLOR)


def embed_fail(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.red())


def embed_success(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.green())


# CHECKS
def is_admin(object_: Interaction | commands.Context):
    if isinstance(object_, Interaction):
        i = object_
        return i.user.id in ADMINS
    elif isinstance(object_, commands.Context):
        ctx = object_
        return ctx.author.id in ADMINS
