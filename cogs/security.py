import discord
from discord import Interaction, app_commands
from discord.ext import commands


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot: commands.Bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: The Security extension was loaded successfully.")

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def antispam(self, i: Interaction, enabled: bool):
        pass


async def setup(bot):
    await bot.add_cog(Security(bot))
