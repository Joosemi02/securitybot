import contextlib
from datetime import datetime

from discord import ButtonStyle, Embed, Interaction, Member, app_commands
from discord.errors import NotFound
from discord.ext import commands
from discord.ui import View, button
from discord.utils import format_dt

from constants import EMBED_COLOR
from db import db
from utils import _T, embed_success, log_punishment


class Paginator:
    def __init__(
        self,
        interaction: Interaction,
        warnings: dict[str, set[str, datetime]],
        **kwargs,
    ) -> None:
        self.i: Interaction = interaction
        self.warns: dict = warnings
        self.ITEMS_PER_PAGE = 10
        self.view = (
            PaginatorView(self.i, self, timeout=30)
            if len(self.warns) > self.ITEMS_PER_PAGE
            else None
        )

        self.page = kwargs.get("page", 1)
        calculation = len(self.warns) / self.ITEMS_PER_PAGE
        self.total_pages = (
            int(calculation) if calculation.is_integer() else int(calculation) + 1
        )
        if self.total_pages == 0:
            self.total_pages = 1

    def _get_cards(self) -> list[dict]:
        return self.warns[
            (self.page - 1) * self.ITEMS_PER_PAGE : self.page * self.ITEMS_PER_PAGE
        ]

    def _build_embed(self):
        embed = Embed(
            description="" if self.warns else _T(self.i, "warnings.display.no_warns"),
            color=EMBED_COLOR,
        )
        for num, dict_ in self.warns.items():
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
            name=f"{_T(self.i, 'warnings.display.title')} {self.i.user.name}",
            icon_url=self.i.user.display_avatar.url,
        )
        return embed

    @property
    def embed(self) -> Embed:
        return self._build_embed()

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
                _T(interaction, "warnings.display.not_my_warns")
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


class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Warnings extension loaded successfully.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def warn(self, i: Interaction, member: Member, reason: str):
        await i.response.defer()
        await db.warn(member.id, reason)

        punishment_msg = _T(
            i, "warnings.punished", member=member.display_name, reason=reason
        )
        await i.followup.send(embed_success(punishment_msg))
        await log_punishment(i, punishment_msg)

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def userwarnings(self, i: Interaction, member: Member):
        await i.response.defer()
        warns = db.warns.find_one({"_id": member.id})
        del warns["_id"]

        paginator = Paginator(interaction=i, warnings=warns)
        await paginator.send_message(i)

    @app_commands.command()
    @app_commands.guild_only()
    async def warnings(self, i: Interaction):
        await i.response.defer()
        warns = db.warns.find_one({"_id": i.user.id})
        del warns["_id"]

        paginator = Paginator(interaction=i, warnings=warns)
        await paginator.send_message(i)


async def setup(bot):
    await bot.add_cog(Warnings(bot))
