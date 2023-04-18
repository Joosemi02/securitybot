from datetime import datetime, timedelta

import discord
from discord import Interaction, app_commands
from discord.app_commands import Choice
from discord.errors import Forbidden
from discord.ext import commands

from utils import _T, embed_fail, embed_success, is_mod, log


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Moderation extension loaded successfully.")

    @app_commands.command()
    @app_commands.check(is_mod)
    async def kick(self, i: Interaction, member: discord.Member, reason: str = None):
        await i.response.defer()
        try:
            await member.kick(reason=reason)
        except Forbidden:
            await i.followup.send(embed_fail(_T(i, "command_fail.forbidden")))

        punishment_msg = _T(
            i,
            "moderation.kick",
            member=member.display_name,
            reason=f"for {reason}" or "✅",
        )

        await i.followup.send(embed_success(punishment_msg))
        await log(i, punishment_msg)

    @app_commands.command()
    @app_commands.check(is_mod)
    async def ban(self, i: Interaction, member: discord.Member, reason: str = None):
        await i.response.defer()
        try:
            await member.kick(reason=reason)
        except Forbidden:
            await i.followup.send(embed_fail(_T(i, "command_fail.forbidden")))

        punishment_msg = _T(
            i,
            "moderation.ban",
            member=member.display_name,
            reason=f"for {reason}" or "✅",
        )

        await i.followup.send(embed_success(punishment_msg))
        await log(i, punishment_msg)

    @app_commands.command()
    @app_commands.check(is_mod)
    @app_commands.choices(
        time=[
            Choice(name="60 secs", value=60),
            Choice(name="5 mins", value=300),
            Choice(name="10 mins", value=600),
            Choice(name="1 hour", value=3600),
            Choice(name="1 day", value=86400),
            Choice(name="1 week", value=604800),
        ]
    )
    async def mute(
        self,
        i: Interaction,
        member: discord.Member,
        time: Choice[int],
        reason: str = None,
    ):
        await i.response.defer()
        try:
            await member.timeout(
                until=datetime.now() + timedelta(seconds=time.value), reason=reason
            )
        except Forbidden:
            await i.followup.send(embed_fail(_T(i, "command_fail.forbidden")))

        punishment_msg = _T(
            i,
            "moderation.mute",
            member=member.display_name,
            mutetime=time.name,
            reason=f"for {reason}" or "✅",
        )

        await i.followup.send(embed_success(punishment_msg))
        await log(i, punishment_msg)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
