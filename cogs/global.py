import discord
from discord import app_commands
from discord.ext import commands

from constants import BUG_REPORT_CHANNEL
from utils import MyBot, embed_info, is_admin, set_default_prefs


class BugModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Bug report", timeout=180)

    info = discord.ui.TextInput(
        label="Explain the bug here",
        placeholder="Please be detailed about the steps to reproduce this.",
        min_length=20,
    )

    async def on_submit(self, i: discord.Interaction):
        channel = i.client.get_channel(BUG_REPORT_CHANNEL)
        e = embed_info(self.info.value)
        e.set_author(name=i.user.name, icon_url=i.user.display_avatar.url)
        await channel.send(embed=e)
        await i.response.send_message(
            "Thanks for submitting the bug you found!", ephemeral=True
        )


class Global(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Global extension loaded successfully.")

    @commands.Cog.listener
    async def on_guild_join(self, guild: discord.Guild):
        await set_default_prefs(guild.id)

    @commands.command()
    @commands.check(is_admin)
    async def sync(self, ctx: commands.Context):
        await self.bot.tree.sync()
        await ctx.message.delete()
    

    @app_commands.command(description="Use this command to report bot bugs")
    @app_commands.guild_only()
    async def report(self, i: discord.Interaction):
        modal = BugModal()
        await i.response.send_modal(modal)


async def setup(bot):
    await bot.add_cog(Global(bot))
