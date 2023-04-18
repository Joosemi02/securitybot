from datetime import datetime

import discord
from discord import Interaction
from discord.ext import commands
from discord.utils import format_dt

from constants import ADMINS, EMBED_COLOR
from db import db


# CLASSES
class MyTree(discord.app_commands.CommandTree):
    async def interaction_check(self, i: Interaction) -> bool:
        if bool(i.guild):
            return True
        await i.response.send_message("You can only use commands in servers.")
        return False


class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, tree_cls=MyTree)


# TRANSLATIONS
async def _T(
    object_: discord.Interaction | commands.Context | discord.Guild | int,
    key: str,
    **kwargs,
) -> str:
    guild_id = get_guild_id(object_)
    lang = await db.get_guild_lang(guild_id)

    keys = key.split(".")
    value = db.translations[lang]
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


# LOG
async def log(i: Interaction, msg: str):
    if channel := db.guilds_cache[i.guild_id]["logs"]:
        log_embed = discord.Embed(description=msg)
        log_embed.add_field(
            name="Author",
            value=f"{i.user.name}#{i.user.discriminator}\nID: ``{i.user.id}``",
        )
        log_embed.set_footer(text=format_dt(datetime.now()))
        await channel.send(log_embed)


# FORMAT
def embed_fail(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=discord.Color.red())


def embed_success(message: str) -> discord.Embed:
    return discord.Embed(description=message, color=EMBED_COLOR)


# CHECKS
def is_admin(object_: Interaction | commands.Context):
    if isinstance(object_, Interaction):
        i = object_
        return i.user.id in ADMINS
    elif isinstance(object_, commands.Context):
        ctx = object_
        return ctx.author.id in ADMINS


def is_mod(i: discord.Interaction):
    return (
        any(role.id in db.guilds_cache[i.guild_id]["roles"] for role in i.user.roles)
        or i.user.guild_permissions.administrator
    )
