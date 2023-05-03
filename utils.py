import contextlib
import json
from datetime import datetime

from discord import BanEntry, ButtonStyle, Color, Embed, Guild, Interaction, User
from discord.errors import NotFound
from discord.ext import commands
from discord.ui import View, button
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

    async def log(self, object_: Interaction | tuple[int, User], msg: str):
        if isinstance(object_, Interaction):
            guild_id = object_.guild_id
            user = object_.user
        else:
            guild_id, user = object_

        if channel := self.get_channel(guilds_cache[guild_id]["logs"]):
            log_embed = embed_info(msg)
            log_embed.add_field(
                name=_T(guild_id, "punishments_log.author"),
                value=f"{user.name}#{user.discriminator}\nID: ``{user.id}``",
            )
            log_embed.add_field(name="Time", value=format_dt(datetime.now()))
            log_embed.set_author(name=user.name, icon_url=user.display_avatar.url)
            await channel.send(embed=log_embed)


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


async def configure_punishments(guild_id, category: str, punishment: str):
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
    object_: Interaction | commands.Context | Guild | int,
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
    if isinstance(object_, (Interaction, commands.Context)):
        return object_.guild.id
    elif isinstance(object_, Guild):
        return object_.id
    else:
        return object_


# FORMAT
def embed_info(message: str) -> Embed:
    return Embed(description=message, color=EMBED_COLOR)


def embed_fail(message: str) -> Embed:
    return Embed(description=message, color=Color.red())


def embed_success(message: str) -> Embed:
    return Embed(description=message, color=Color.green())


# CHECKS
def is_admin(object_: Interaction | commands.Context):
    if isinstance(object_, Interaction):
        i = object_
        return i.user.id in ADMINS
    elif isinstance(object_, commands.Context):
        ctx = object_
        return ctx.author.id in ADMINS


# PAGINATOR
class Paginator:
    def __init__(
        self,
        interaction: Interaction,
        objects: dict[str, set[str, datetime]] | list[BanEntry],
        username=None,
        **kwargs,
    ) -> None:
        self.username = username
        self.i: Interaction = interaction
        self.ITEMS_PER_PAGE = 10
        self.type_ = "warnings" if isinstance(objects, dict) else "bans"
        self.objects: dict = objects
        self.view = (
            PaginatorView(self.i, self, timeout=30)
            if len(self.objects) > self.ITEMS_PER_PAGE
            else None
        )

        self.page = kwargs.get("page", 1)
        calculation = len(self.objects) / self.ITEMS_PER_PAGE
        self.total_pages = (
            int(calculation) if calculation.is_integer() else int(calculation) + 1
        )
        if self.total_pages == 0:
            self.total_pages = 1

    def _get_cards(self) -> list[dict]:
        return self.objects[
            (self.page - 1) * self.ITEMS_PER_PAGE : self.page * self.ITEMS_PER_PAGE
        ]

    def _build_warnings_embed(self):
        embed = Embed(
            description="" if self.objects else _T(self.i, "warnings.display.no_warns"),
            color=EMBED_COLOR,
        )
        for num, dict_ in self.objects.items():
            reason = f"{_T(self.i, 'warnings.display.reason')}: {dict_[0]}"
            date = f"{_T(self.i, 'warnings.display.date')}: {format_dt(dict_[1])}"
            embed.add_field(
                name=f"ID: {num}",
                value=f"{reason}\n{date}",
                inline=False,
            )
            embed.set_footer(
                text=f"{_T(self.i, 'warnings.display.page')} {self.page}/{self.total_pages}"
            )
            embed.set_author(
                name=f"{_T(self.i, 'warnings.display.title')} {self.username}",
                icon_url=self.i.user.display_avatar.url,
            )
        return embed

    def _build_bans_embed(self):
        self.objects: list[BanEntry]
        embed = Embed(
            description="" if self.objects else _T(self.i, "moderation.bans.no_bans"),
            color=EMBED_COLOR,
        )
        for ban in self.objects:
            embed.add_field(
                name=f"ID: {ban.user.id}",
                value=f"{_T(self.i, 'moderation.bans.reason')}: {ban.reason or '---'}",
                inline=False,
            )

            embed.set_footer(
                text=f"{_T(self.i, 'moderation.bans.page')} {self.page}/{self.total_pages}"
            )
            embed.set_author(
                name=_T(self.i, "moderation.bans.title"),
                icon_url=self.i.user.display_avatar.url,
            )
        return embed

    @property
    def embed(self) -> Embed:
        if self.type_ == "warnings":
            return self._build_warnings_embed()
        else:
            return self._build_bans_embed()

    async def send_message(self, i: Interaction):
        if not i.command:
            self.view.update_buttons()
            await i.followup.edit_message(
                message_id=i.message.id, embed=self.embed, view=self.view
            )
        elif self.view:
            await i.followup.send(embed=self.embed, view=self.view)
        else:
            await i.followup.send(embed=self.embed)


class PaginatorView(View):
    def __init__(self, i, paginator, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.i: Interaction = i
        self.paginator: Paginator = paginator

    async def on_timeout(self):
        if self.paginator.i:
            with contextlib.suppress(NotFound):
                m = await self.paginator.i.original_response()
                await m.edit(view=None)

    async def interaction_check(self, interaction: Interaction) -> bool:
        if interaction.user != self.i.user:
            await interaction.response.send_message(
                _T(interaction, "command_fail.not_own_paginator")
            )
            return False
        return True

    def update_buttons(self):
        last_disable = self.paginator.page <= 1
        next_disable = self.paginator.page >= self.paginator.total_pages
        self.children[0].disabled = last_disable
        self.children[1].disabled = last_disable
        self.children[-2].disabled = next_disable
        self.children[-1].disabled = next_disable

    @button(
        emoji="⏪",
        custom_id="fastlast",
        style=ButtonStyle.secondary,
        disabled=True,
    )
    async def fastlast_callback(self, interaction: Interaction, _):
        self.paginator.page = 1
        await self.paginator.send_message(interaction)

    @button(emoji="◀", custom_id="last", style=ButtonStyle.secondary, disabled=True)
    async def last_callback(self, interaction: Interaction, _):
        self.paginator.page -= 1
        await self.paginator.send_message(interaction)

    @button(emoji="❌", custom_id="stop", style=ButtonStyle.secondary)
    async def stop_callback(self, interaction: Interaction, _):
        await interaction.message.delete()
        self.stop()

    @button(
        emoji="▶️",
        custom_id="next",
        style=ButtonStyle.secondary,
        disabled=False,
    )
    async def next_callback(self, interaction: Interaction, _):
        self.paginator.page += 1
        await self.paginator.send_message(interaction)

    @button(
        emoji="⏩",
        custom_id="fastnext",
        style=ButtonStyle.secondary,
        disabled=False,
    )
    async def fastnext_callback(self, interaction: Interaction, _):
        self.paginator.page = self.paginator.total_pages
        await self.paginator.send_message(interaction)
