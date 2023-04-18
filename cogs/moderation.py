import discord
from discord import Interaction, app_commands
from discord.errors import Forbidden
from discord.ext import commands

from utils import _T, embed_fail, embed_success, is_mod


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Moderation extension loaded successfully.")

    @app_commands.command()
    @app_commands.check()
    async def kick(self, i: Interaction, member: discord.Member, reason: str = None):
        await i.response.defer()
        try:
            await member.kick(reason=reason)
        except Forbidden:
            await i.followup.send(embed_fail(_T(i, "command_fail.forbidden")))
        await i.followup.send(
            embed_success(_T(i, "moderation.kick", member=member.display_name))
        )


async def setup(bot):
    await bot.add_cog(Moderation(bot))
