import time

import psutil
from discord import (
    Guild,
    Interaction,
    Message,
    SelectOption,
    TextChannel,
    TextStyle,
    app_commands,
)
from discord.app_commands import Choice
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, View, select

from constants import BUG_REPORT_CHANNEL, INVITE_LINK, LANGUAGES, SUPPORT_SERVER
from utils import (
    _T,
    MyBot,
    embed_fail,
    embed_info,
    embed_success,
    get_guild_prefs,
    is_admin,
    set_default_prefs,
    set_guild_data,
)


class BugModal(Modal):
    def __init__(self):
        super().__init__(title="Bug report", timeout=180)

    info = TextInput(
        style=TextStyle.long,
        label="Explain the bug here",
        placeholder="Please be detailed about the steps to reproduce this.",
        min_length=20,
    )

    async def on_submit(self, i: Interaction):
        await i.response.defer()
        channel = i.client.get_channel(BUG_REPORT_CHANNEL)
        e = embed_info(i, self.info.value)
        e.set_author(name=i.user.name, icon_url=i.user.display_avatar.url)
        if channel:
            await channel.send(embed=e)
        else:
            print("BUG REPORT CHANNEL NOT FOUND")
        await i.followup.send(
            "Thanks for submitting the bug you found!", ephemeral=True
        )


class HelpView(View):
    def __init__(self, bot, main_embed, i):
        self.bot: MyBot = bot
        self.main_embed = main_embed
        self.message: Message
        super().__init__()

        self.add_item(Button(label=_T(i, "help.support"), url=SUPPORT_SERVER))
        self.add_item(Button(label=_T(i, "help.invite"), url=INVITE_LINK))

    async def on_timeout(self):
        await self.message.edit(view=None)

    @select(
        options=[
            SelectOption(label="Moderation commands", value="Moderation", emoji="🔨"),
            SelectOption(label="Security commands", value="Security", emoji="🛡️"),
            SelectOption(label="Warning commands", value="Warnings", emoji="🪧"),
            SelectOption(label="General commands", value="General", emoji="🔧"),
            SelectOption(label="Bot info", value="Main", emoji="ℹ️"),
        ],
        placeholder="Help by category",
        max_values=1,
    )
    async def helpmenu(self, i: Interaction, select: Select):
        category = select.values[0]
        embed = embed_info(i, f"{category} commands")
        if category == "Main":
            embed = self.main_embed
        else:
            for command in self.bot.get_cog(category).get_app_commands():
                name = f"/{command.name}"
                if category == "Security":
                    enabled = (
                        get_guild_prefs(i.guild_id, command.name)["enabled"]
                        if command.name != "joinwatch"
                        else get_guild_prefs(i.guild_id, command.name)
                    )
                    name += " ✅" if enabled else " ❌"
                embed.add_field(name=name, value=command.description)
        await i.response.edit_message(embed=embed)


class General(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Global extension loaded successfully.")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: Guild):
        await set_default_prefs(guild.id)

    @commands.command()
    @commands.check(is_admin)
    async def adminhelp(self, ctx: commands.Context):
        embed = embed_info(ctx, "Admin commands")
        embed.add_field(name="sync", value="Sync app commands")
        embed.add_field(
            name="leave [server_id]", value="The bot leaves the given server"
        )
        embed.add_field(name="info", value="Panel with bot info and performance")
        await ctx.send(embed=embed)

    @commands.command()
    @commands.check(is_admin)
    async def sync(self, ctx: commands.Context):
        await self.bot.tree.sync()
        await ctx.message.delete()
        await ctx.send(embed=embed_success(ctx, "Commands synced!"), delete_after=5)

    @commands.command()
    @commands.check(is_admin)
    async def leave(self, ctx: commands.Context, guild_id: int):
        if (guild := self.bot.get_guild(guild_id)) is None:
            return await ctx.send(embed=embed_fail(ctx, "Server not found for this ID"))
        await guild.leave()
        await ctx.send(embed=embed_success(ctx, "Left server successfully"))

    @commands.command()
    @commands.check(is_admin)
    async def info(self, ctx: commands.Context):
        embed = embed_info(ctx, "Bot information")
        bot = self.bot

        # General info
        uptime = time.time() - bot.start_time
        uptime_str = f"{int(uptime // 3600)} hours, {int((uptime % 3600) // 60)} minutes, and {int(uptime % 60)} seconds"
        embed.add_field(name="Uptime", value=uptime_str, inline=False)

        guild_count = len(bot.guilds)
        embed.add_field(name="Guild Count", value=guild_count)

        user_count = len(bot.users)
        embed.add_field(name="User Count", value=user_count)

        # Calculate bot response time
        start_time = time.time()
        message = await ctx.send("Pinging...")
        end_time = time.time()
        response_time = (end_time - start_time) * 1000
        embed.add_field(
            name="Response Time", value=f"{response_time:.2f} ms", inline=False
        )

        # CPU and memory usage
        cpu_usage = psutil.cpu_percent()
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%")

        memory_usage = psutil.virtual_memory().percent
        embed.add_field(name="Memory Usage", value=f"{memory_usage}%")

        await message.edit(content="", embed=embed)

    @app_commands.command(description="Use this command to report bot bugs")
    @app_commands.guild_only()
    async def report(self, i: Interaction):
        modal = BugModal()
        await i.response.send_modal(modal)

    @app_commands.command(description="General bot info")
    @app_commands.guild_only()
    async def help(self, i: Interaction):
        await i.response.defer()
        embed = embed_info(i, _T(i, "help.desc"))
        embed.add_field(name=_T(i, "help.antispam.1"), value=_T(i, "help.antispam.2"))
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

        view = HelpView(self.bot, embed, i)
        view.message = await i.followup.send(embed=embed, view=view)

    @app_commands.command(description="Edit the bot language settings for this server")
    @app_commands.choices(
        language=[Choice(name=k, value=v) for k, v in LANGUAGES.items()]
    )
    @app_commands.describe(
        language="The general language for the bot",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def language(self, i: Interaction, language: Choice[str]):
        await i.response.defer()
        await set_guild_data(i.guild_id, "lang", language.value)
        await i.followup.send(embed=embed_success(i, _T(i, "config")))

    @app_commands.command(
        description="Manage logs channel. If no channel is selected logs will be disabled."
    )
    @app_commands.describe(
        channel="Punishments and logs will be posted in this channel"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def logs(self, i: Interaction, channel: TextChannel = None):
        await i.response.defer()
        await set_guild_data(i.guild_id, "logs", channel.id if channel else 0)
        await i.followup.send(embed=embed_success(i, _T(i, "config")))


async def setup(bot):
    await bot.add_cog(General(bot))
