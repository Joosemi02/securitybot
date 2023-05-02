import subprocess
import time

import discord
from discord import app_commands
from discord.ext import commands

from constants import BUG_REPORT_CHANNEL
from utils import (
    _T,
    MyBot,
    embed_fail,
    embed_info,
    embed_success,
    is_admin,
    set_default_prefs,
)


class BugModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Bug report", timeout=180)

    info = discord.ui.TextInput(
        style=discord.TextStyle.long,
        label="Explain the bug here",
        placeholder="Please be detailed about the steps to reproduce this.",
        min_length=20,
    )

    async def on_submit(self, i: discord.Interaction):
        await i.response.defer()
        channel = i.client.get_channel(BUG_REPORT_CHANNEL)
        e = embed_info(self.info.value)
        e.set_author(name=i.user.name, icon_url=i.user.display_avatar.url)
        await channel.send(embed=e)
        await i.followup.send(
            "Thanks for submitting the bug you found!", ephemeral=True
        )


class Global(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Global extension loaded successfully.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await set_default_prefs(guild.id)

    @commands.command()
    @commands.check(is_admin)
    async def sync(self, ctx: commands.Context):
        await self.bot.tree.sync()
        await ctx.message.delete()

    @commands.command()
    @commands.check(is_admin)
    async def leave(self, ctx: commands.Context, guild_id: int):
        if guild := self.bot.get_guild(guild_id) is None:
            return await ctx.send(embed=embed_fail("Server not found for this ID"))
        await guild.leave()
        await ctx.send(embed=embed_success("Left server successfully"))

    @commands.command()
    @commands.check(is_admin)
    async def info(self, ctx: commands.Context):
        embed = embed_info("")
        bot = self.bot
        uptime = time.time() - bot.start_time
        uptime_str = f"{int(uptime // 3600)} hours, {int((uptime % 3600) // 60)} minutes, and {int(uptime % 60)} seconds"

        # Get general bot information
        guild_count = len(bot.guilds)
        user_count = len(bot.users)

        # Create an embed to display the bot information
        embed = discord.Embed(title="Bot Information", color=discord.Color.blue())
        embed.add_field(name="Uptime", value=uptime_str, inline=False)
        embed.add_field(name="Guild Count", value=guild_count)
        embed.add_field(name="User Count", value=user_count)

        # Calculate bot response time
        start_time = time.time()
        message = await ctx.send("Pinging...")
        end_time = time.time()
        response_time = (end_time - start_time) * 1000
        embed.add_field(
            name="Response Time", value=f"{response_time:.2f} ms", inline=False
        )

        # Calculate bot CPU usage
        cpu_output = subprocess.check_output(
            "WMIC CPU GET LoadPercentage /Value", shell=True
        )
        cpu_usage = int(cpu_output.decode().strip().split("=")[1])
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%")

        # Get memory usage
        memory_output = subprocess.check_output(
            "WMIC OS GET FreePhysicalMemory,TotalVisibleMemorySize /Value", shell=True
        )
        memory_free, memory_total = map(
            int,
            [
                s.split("=")[1].strip()
                for s in memory_output.decode().split("\n")
                if "FreePhysicalMemory" in s or "TotalVisibleMemorySize" in s
            ],
        )
        memory_used = memory_total - memory_free
        memory_percent = memory_used / memory_total * 100
        memory_used_mb = memory_used / 1024
        memory_total_mb = memory_total / 1024
        embed.add_field(
            name="Memory Usage",
            value=f"{memory_used_mb:.2f}/{memory_total_mb:.2f} MB ({memory_percent:.2f}%)",
        )

        await message.edit(content="", embed=embed)

    @app_commands.command(description="Use this command to report bot bugs")
    @app_commands.guild_only()
    async def report(self, i: discord.Interaction):
        modal = BugModal()
        await i.response.send_modal(modal)

    @app_commands.command()
    @app_commands.guild_only()
    async def help(self, i: discord.Interaction):
        embed = embed_info(_T(i, "help.desc"))
        embed.add_field(name=_T(i, "help.antispam.1"), value=_T(i, "help.antispam.2"))
        embed.add_field(name=_T(i, "help.antiraid.1"), value=_T(i, "help.antiraid.2"))
        embed.add_field(
            name=_T(i, "help.linkfilter.1"), value=_T(i, "help.linkfilter.2")
        )
        embed.add_field(name=_T(i, "help.joinwatch.1"), value=_T(i, "help.joinwatch.2"))
        embed.add_field(
            name=_T(i, "help.punishments.1"), value=_T(i, "help.punishments.2")
        )
        embed.add_field(
            name=_T(i, "help.moderation.1"), value=_T(i, "help.moderation.2")
        )
        embed.add_field(name=_T(i, "help.warnings.1"), value=_T(i, "help.warnings.2"))
        await i.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Global(bot))
