import datetime
import time
from collections import defaultdict
from typing import MutableMapping, Optional

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from db import db
from utils import _T, MyBot, embed_success


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Security extension was loaded successfully.")

    async def enable_antispam(self, i, enabled, notify):
        actions = [
            discord.AutoModRuleAction(
                custom_message=f"{self.bot.user.name} - Your message was blocked for spam"
            ),
            discord.AutoModRuleAction(duration=datetime.timedelta(hours=1)),
        ]
        if notify:
            actions.append(discord.AutoModRuleAction(channel_id=notify.id))

        mention_spam_trigger = discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.mention_spam
        )
        await i.guild.create_automod_rule(
            name=f"{self.bot.user.name} - Anti Mention Spam",
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=mention_spam_trigger,
            actions=actions,
            enabled=enabled,
        )
        spam_trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam)
        await i.guild.create_automod_rule(
            name=f"{self.bot.user.name} - Anti Spam",
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=spam_trigger,
            actions=actions,
            enabled=enabled,
        )

    @app_commands.command(description="Manage the antispam filter.")
    @app_commands.describe(
        notify="Channel to send a notification when a user is punished for spam."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def antispam(
        self, i: Interaction, enabled: bool, notify: discord.TextChannel = None
    ):
        await i.response.defer()

        await self.enable_antispam(i, enabled, notify)

        msg = _T(i, f"security.antispam.{'on' if enabled else 'off'}")
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)

    @app_commands.command(description="Enable or disable the raid mode.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def raid(self, i: Interaction):
        pass


async def setup(bot):
    await bot.add_cog(Security(bot))

"""
## Spam detector
class ExpiringCache(dict):
    def __init__(self, seconds: float):
        self.__ttl: float = seconds
        super().__init__()

    def __verify_cache_integrity(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [
            k for (k, (v, t)) in self.items() if current_time > (t + self.__ttl)
        ]
        for k in to_remove:
            del self[k]

    def __contains__(self, key: str):
        self.__verify_cache_integrity()
        return super().__contains__(key)

    def __getitem__(self, key: str):
        self.__verify_cache_integrity()
        return super().__getitem__(key)

    def __setitem__(self, key: str, value):
        super().__setitem__(key, (value, time.monotonic()))


class CooldownByContent(commands.CooldownMapping):
    def _bucket_key(self, message: discord.Message) -> tuple[int, str]:
        return (message.channel.id, message.content)


class SpamChecker:
    ""This spam checker does a few things.
    1) It checks if a user has spammed more than 10 times in 12 seconds
    2) It checks if the content has been spammed 15 times in 17 seconds.
    3) It checks if new users have spammed 30 times in 35 seconds.
    4) It checks if "fast joiners" have spammed 10 times in 12 seconds.
    The second case is meant to catch alternating spam bots while the first one
    just catches regular singular spam bots.
    ""

    def __init__(self):
        self.by_content = CooldownByContent.from_cooldown(
            15, 17.0, commands.BucketType.member
        )
        self.by_user = commands.CooldownMapping.from_cooldown(
            10, 12.0, commands.BucketType.user
        )
        self.last_join: Optional[datetime.datetime] = None
        self.new_user = commands.CooldownMapping.from_cooldown(
            30, 35.0, commands.BucketType.channel
        )

        self.fast_joiners: MutableMapping[int, bool] = ExpiringCache(seconds=1800.0)
        self.hit_and_run = commands.CooldownMapping.from_cooldown(
            10, 12, commands.BucketType.channel
        )

    def is_new(self, member: discord.Member) -> bool:
        now = discord.utils.utcnow()
        seven_days_ago = now - datetime.timedelta(days=7)
        ninety_days_ago = now - datetime.timedelta(days=90)
        return (
            member.created_at > ninety_days_ago
            and member.joined_at is not None
            and member.joined_at > seven_days_ago
        )

    def is_spamming(self, message: discord.Message) -> bool:
        if message.guild is None:
            return False

        current = message.created_at.timestamp()

        if message.author.id in self.fast_joiners:
            bucket = self.hit_and_run.get_bucket(message)
            if bucket and bucket.update_rate_limit(current):
                return True

        if self.is_new(message.author):  # type: ignore
            new_bucket = self.new_user.get_bucket(message)
            if new_bucket and new_bucket.update_rate_limit(current):
                return True

        user_bucket = self.by_user.get_bucket(message)
        if user_bucket and user_bucket.update_rate_limit(current):
            return True

        content_bucket = self.by_content.get_bucket(message)
        return bool(content_bucket and content_bucket.update_rate_limit(current))

    def is_fast_join(self, member: discord.Member) -> bool:
        joined = member.joined_at or discord.utils.utcnow()
        if self.last_join is None:
            self.last_join = joined
            return False
        is_fast = (joined - self.last_join).total_seconds() <= 2.0
        self.last_join = joined
        if is_fast:
            self.fast_joiners[member.id] = True
        return is_fast

    def __init__(self, bot: MyBot):
        self.bot = bot
        self._spam_check: defaultdict[int, SpamChecker] = defaultdict(SpamChecker)

    async def check_raid(
        self,
        guild_id: int,
        member: discord.Member,
        message: discord.Message,
    ) -> None:
        if not db.raid_enabled(guild_id):
            return

        checker = self._spam_check[guild_id]
        if not checker.is_spamming(message):
            return

        try:
            await member.ban(reason="Auto-ban for spamming")
        except discord.HTTPException:
            log.info(
                "[RoboMod] Failed to ban %s (ID: %s) from server %s.",
                member,
                member.id,
                member.guild,
            )
        else:
            await self.bot.log((guild_id, member), "Banned from server")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        author = message.author
        if author.id in (self.bot.user.id, self.bot.owner_id):
            return
        if message.guild is None or not isinstance(author, discord.Member):
            return
        if author.bot:
            return

        # we're going to ignore members with manage messages
        if author.guild_permissions.manage_messages:
            return

        guild_id = message.guild.id
        config: ModConfig = await db.get_guild_config(guild_id)
        if config is None:
            return

        await self.check_raid(config, guild_id, author, message)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        now = discord.utils.utcnow()
        is_new = member.created_at > (now - datetime.timedelta(days=7))
        checker = self._spam_check[member.guild.id]

        # Do the broadcasted message to the channel
        title = "Member Joined"
        if checker.is_fast_join(member):
            colour = 0xDD5F53  # red
            if is_new:
                title = "Member Joined (Very New Member)"
        else:
            colour = 0x53DDA4  # green

            if is_new:
                colour = 0xDDA453  # yellow
                title = "Member Joined (Very New Member)"

        e = discord.Embed(title=title, colour=colour)
        e.timestamp = now
        e.set_author(name=str(member), icon_url=member.display_avatar.url)
        e.add_field(name="ID", value=member.id)
        assert member.joined_at is not None
        e.add_field(name="Joined", value=time.format_dt(member.joined_at, "F"))
        e.add_field(
            name="Created", value=time.format_relative(member.created_at), inline=False
        )

        if config.requires_migration:
            await self.suggest_automod_migration(config, e, guild_id)
            return

        if config.broadcast_webhook:
            try:
                await config.broadcast_webhook.send(embed=e)
            except (discord.Forbidden, discord.NotFound):
                async with self._disable_lock:
                    await self.disable_automod_broadcast(guild_id)

    async def start_lockdown(
        self,
        ctx,
        channels: list[discord.TextChannel | discord.VoiceChannel],
    ) -> tuple[
        list[discord.TextChannel | discord.VoiceChannel],
        list[discord.TextChannel | discord.VoiceChannel],
    ]:
        guild_id = ctx.guild.id
        default_role = ctx.guild.default_role

        records = []
        success, failures = [], []
        reason = f"Lockdown request by {ctx.author} (ID: {ctx.author.id})"
        async with ctx.typing():
            for channel in channels:
                overwrite = channel.overwrites_for(default_role)
                allow, deny = overwrite.pair()

                overwrite.send_messages = False
                overwrite.connect = False
                overwrite.add_reactions = False
                overwrite.use_application_commands = False
                overwrite.create_private_threads = False
                overwrite.create_public_threads = False
                overwrite.send_messages_in_threads = False

                try:
                    await channel.set_permissions(
                        default_role, overwrite=overwrite, reason=reason
                    )
                except discord.HTTPException:
                    failures.append(channel)
                else:
                    success.append(channel)
                    records.append(
                        {
                            "guild_id": guild_id,
                            "channel_id": channel.id,
                            "allow": allow.value,
                            "deny": deny.value,
                        }
                    )

        query = ""
            INSERT INTO guild_lockdowns(guild_id, channel_id, allow, deny)
            SELECT d.guild_id, d.channel_id, d.allow, d.deny
            FROM jsonb_to_recordset($1::jsonb) AS d(guild_id BIGINT, channel_id BIGINT, allow BIGINT, deny BIGINT)
            ON CONFLICT (guild_id, channel_id) DO NOTHING
        ""
        await self.bot.pool.execute(query, records)
        return success, failures

    async def end_lockdown(
        self,
        guild: discord.Guild,
        *,
        channel_ids: Optional[list[int]] = None,
        reason: Optional[str] = None,
    ) -> list[discord.abc.GuildChannel]:
        get_channel = guild.get_channel
        http_fallback: Optional[dict[int, discord.abc.GuildChannel]] = None
        default_role = guild.default_role
        failures = []
        lockdowns = await self.get_lockdown_information(
            guild.id, channel_ids=channel_ids
        )
        for channel_id, permissions in lockdowns.items():
            channel = get_channel(channel_id)
            # If a channel isn't found, do an HTTP fallback instead of cache
            # This way we can ensure whether the channel is there or not without
            # making N invalid requests per deleted channel
            if channel is None:
                if http_fallback is None:
                    http_fallback = {c.id: c for c in await guild.fetch_channels()}
                    get_channel = http_fallback.get
                    channel = get_channel(channel_id)
                    if channel is None:
                        continue
                continue

            try:
                await channel.set_permissions(
                    default_role, overwrite=permissions, reason=reason
                )
            except discord.HTTPException:
                failures.append(channel)

        return failures
"""