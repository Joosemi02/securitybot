from datetime import timedelta

from discord import Embed, Interaction, Member, Status, TextChannel, app_commands
from discord.app_commands import Choice
from discord.errors import Forbidden, NotFound
from discord.ext import commands

from constants import EMBED_COLOR, MAX_CLEAR_AMOUNT
from utils import _T, MyBot, Paginator, embed_fail, embed_info, embed_success


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Moderation extension loaded successfully.")

    @app_commands.command(description="Kick this user from the server.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def kick(self, i: Interaction, member: Member, reason: str = None):
        await i.response.defer()
        try:
            await member.kick(reason=reason)
        except Forbidden:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "command_fail.forbidden"))
            )

        punishment_msg = _T(
            i,
            "moderation.kick",
            member=member.display_name,
            reason=f"for {reason}" if reason else "✅",
        )

        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    @app_commands.command(description="Ban this user from the server.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def ban(self, i: Interaction, member: Member, reason: str = None):
        await i.response.defer()
        try:
            await member.ban(reason=reason)
        except Forbidden:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "command_fail.forbidden"))
            )

        punishment_msg = _T(
            i,
            "moderation.ban",
            member=member.display_name,
            reason=f"for {reason}" if reason else "✅",
        )

        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    @app_commands.command(description="Mute this user temporarily.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    @app_commands.choices(
        time=[
            Choice(name="60 secs", value=60),
            Choice(name="5 mins", value=300),
            Choice(name="10 mins", value=600),
            Choice(name="1 hour", value=3600),
            Choice(name="1 day", value=86400),
            Choice(name="1 week", value=604800),
            Choice(name="Unmute", value=0),
        ]
    )
    async def mute(
        self,
        i: Interaction,
        member: Member,
        time: Choice[int],
        reason: str = None,
    ):
        await i.response.defer()
        try:
            await member.timeout(timedelta(seconds=time.value), reason=reason)
        except Forbidden:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "command_fail.forbidden"))
            )

        punishment_msg = _T(
            i,
            "moderation.mute",
            member=member.display_name,
            mutetime=time.name,
            reason=f"for {reason}" if reason else "✅",
        )

        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    @app_commands.command(description="Bulk delete messages in this channel.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def clear(
        self, i: Interaction, amount: app_commands.Range[int, 1, MAX_CLEAR_AMOUNT]
    ):
        await i.response.defer(ephemeral=True)
        try:
            await i.channel.purge(limit=amount, bulk=True)
        except Forbidden:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "command_fail.forbidden"))
            )

        punishment_msg = _T(
            i,
            "moderation.clear",
            amount=amount,
            channel=i.channel.mention,
        )

        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    @app_commands.command(description="Get info of this user.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def userinfo(self, i: Interaction, member: Member):
        await i.response.defer()
        embed = embed_info(i, "")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_author(name=member)

        embed.add_field(name=_T(i, "moderation.userinfo.user_id"), value=member.id)
        embed.add_field(
            name=_T(i, "moderation.userinfo.nick"), value=member.display_name
        )
        embed.add_field(name=_T(i, "moderation.userinfo.status"), value=member.status)

        embed.add_field(name=_T(i, "moderation.userinfo.voice"), value=member.voice)
        embed.add_field(
            name=_T(i, "moderation.userinfo.toprole"), value=member.top_role
        )

        embed.add_field(
            name=_T(i, "moderation.userinfo.created_at"),
            value=member.created_at.__format__("%A, %d. %B %Y @ %H:%M:%S"),
        )
        embed.add_field(
            name=_T(i, "moderation.userinfo.joined_at"),
            value=member.joined_at.__format__("%A, %d. %B %Y @ %H:%M:%S"),
        )

        await i.followup.send(embed=embed)

    @app_commands.command(description="Get info of the server.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def serverinfo(self, i: Interaction):
        await i.response.defer()
        server = i.guild
        embed = Embed(title=_T(i, "moderation.serverinfo.title"), color=EMBED_COLOR)
        embed.set_thumbnail(url=server.icon.url if server.icon else "")
        embed.set_footer(
            text=f"{_T(i, 'moderation.serverinfo.server_id')}: {server.id}"
        )

        embed.add_field(name=_T(i, "moderation.serverinfo.name"), value=server.name)
        embed.add_field(name=_T(i, "moderation.serverinfo.owner"), value=server.owner)
        embed.add_field(
            name=_T(i, "moderation.serverinfo.members"), value=server.member_count
        )

        online = len([m for m in server.members if m.status != Status.offline])
        embed.add_field(name=_T(i, "moderation.serverinfo.online"), value=str(online))
        channels = len(server.text_channels)
        embed.add_field(
            name=_T(i, "moderation.serverinfo.channels"), value=str(channels)
        )
        embed.add_field(
            name=_T(i, "moderation.serverinfo.region"),
            value=server.preferred_locale.name,
        )

        roles = len(server.roles)
        emojis = len(server.emojis)
        embed.add_field(
            name=_T(i, "moderation.serverinfo.toprole"), value=server.roles[-1]
        )
        embed.add_field(name=_T(i, "moderation.serverinfo.roles"), value=str(roles))
        embed.add_field(name=_T(i, "moderation.serverinfo.emojis"), value=str(emojis))

        embed.add_field(
            name=_T(i, "moderation.serverinfo.created_at"),
            value=server.created_at.__format__("%A, %d. %B %Y @ %H:%M:%S"),
        )

        await i.followup.send(embed=embed)

    @app_commands.command(description="Enable slowmode in this channel.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    @app_commands.describe(time="Slowmode time in seconds")
    async def slowmode(self, i: Interaction, channel: TextChannel, time: int):
        await i.response.defer()
        try:
            await channel.edit(slowmode_delay=time)
        except Forbidden:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "command_fail.forbidden"))
            )

        punishment_msg = _T(
            i, "moderation.slowmode", channel=i.channel.mention, time=time
        )

        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    @app_commands.command(description="Get a list of banned members")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def bans(self, i: Interaction):
        await i.response.defer()
        bans = [entry async for entry in i.guild.bans()]
        paginator = Paginator(interaction=i, objects=bans)
        await paginator.send_message(i)

    @app_commands.command(description="Unban a user from this server")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def unban(self, i: Interaction, user_id: str):
        await i.response.defer()
        fail_msg = _T(i, "command_fail.user_not_found")
        if not user_id.isnumeric():
            return await i.followup.send(fail_msg)
        try:
            user = await self.bot.fetch_user(int(user_id))
        except NotFound:
            return await i.followup.send(fail_msg)

        await i.guild.unban(user)
        msg = _T(i, "moderation.unban", member=user.name)
        await i.followup.send(embed=embed_success(i, msg))
        await self.bot.log(i, msg)

    @app_commands.command(
        description="Enable or disable server invites. They are turned off automatically when a raid is detected"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def invites(self, i: Interaction, enabled: bool):
        await i.response.defer()
        if "COMMUNITY" in i.guild.features:
            await i.guild.edit(invites_disabled=not enabled)
            msg = _T(i, "moderation.invites", state="on" if enabled else "off")
            await i.followup.send(embed=embed_success(i, msg))
            await self.bot.log(i, msg)
        else:
            msg = _T(i, "command_fail.no_community")
            await i.followup.send(embed=embed_fail(i, msg))


async def setup(bot):
    await bot.add_cog(Moderation(bot))
