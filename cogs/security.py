import contextlib
import datetime
from collections import defaultdict
from datetime import time
from typing import Iterable, List, MutableMapping, Optional

import discord
from discord import Interaction, app_commands
from discord.app_commands import Choice
from discord.components import SelectOption
from discord.errors import Forbidden
from discord.ext import commands
from discord.interactions import Interaction

from utils import (
    _T,
    MyBot,
    configure_punihsments,
    embed_info,
    embed_success,
    get_guild_prefs,
    get_punishments,
    set_guild_data,
)

from .warnings import exec_warn


# AntiRaid
class ExpiringCache(dict):
    def __init__(self, seconds: float):
        self.__ttl: float = seconds
        super().__init__()

    def __verify_cache_integrity(self):
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


class RaidChecker:
    """
    1) Checks if a user has spammed more than 10 times in 12 seconds
    2) Checks if the content has been spammed 15 times in 17 seconds.
    3) Checks if new users have spammed 30 times in 35 seconds.
    4) Checks if "fast joiners" have spammed 10 times in 12 seconds.
    """

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

        if self.is_new(message.author):
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
        self._spam_check: defaultdict[int, RaidChecker] = defaultdict(RaidChecker)


# Views
class NotifySelect(discord.ui.ChannelSelect):
    def __init__(self, placeholder: str, bot: MyBot):
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=1,
            channel_types=discord.ChannelType.text,
        )
        self.bot = bot

    async def callback(self, i: Interaction):
        if self.values:
            channel_id = self.values[0].id
            channel_name = self.values[0].name
            rules = await i.guild.fetch_automod_rules()
            for rule in rules:
                if rule.trigger.type.value in [3, 5]:
                    actions = rule.actions
                    actions.append(discord.AutoModRuleAction(channel_id=channel_id))
                    await rule.edit(actions=actions)
        else:
            channel_id = 0
            channel_name = "---"
        await set_guild_data(i.guild_id, "antispam.notify", channel_id)
        msg = _T(i, "antispam.notify", channel=channel_name)
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)


class ActionSelect(discord.ui.Select):
    def __init__(
        self,
        *,
        placeholder: str,
        options: List[SelectOption],
        actions: Iterable,
        bot: MyBot,
    ):
        super().__init__(
            placeholder=placeholder, min_values=0, max_values=2, options=options
        )
        self.actions = actions
        self.bot = bot

    async def callback(self, i: Interaction):
        await set_guild_data(i.guild_id, "antispam.punishments", self.values)
        msg = _T(i, "antispam.config")
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)


class ConfigurationView(discord.ui.View):
    def __init__(self, i: Interaction, bot):
        super().__init__()
        self.i = i
        actions = {
            "warn": "🪧",
            "min_mute": "⌛",
            "hour_mute": "🕛",
            "day_mute": "📆",
            "kick": "🦶",
            "ban": "🔨",
        }
        placeholder = _T(i, "antispam.choose")
        options = [
            SelectOption(
                label=_T(i, f"pusnihments.{action}"),
                value=emoji,
                emoji=action,
                default=action in get_punishments(i.guild_id, "antispam"),
            )
            for action, emoji in actions.items()
        ]
        self.add_item(
            ActionSelect(
                placeholder=placeholder,
                options=options,
                actions=actions.keys(),
                bot=bot,
            )
        )
        self.add_item(NotifySelect(_T(i, "antispam.choose_channel"), bot))

    async def interaction_check(self, i: Interaction):
        if self.i.user.id == i.user.id:
            await i.response.defer()
            return True
        else:
            await i.response.send_message(
                _T(i, "command_fail.not_own_settings"), ephemeral=True
            )
            return False

    async def on_timeout(self):
        await self.message.edit(view=None)


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot
        self._spam_check: defaultdict[int, RaidChecker] = defaultdict(RaidChecker)
        with open("link_filter.txt", "r", encoding="utf-8") as f:
            self.links: list = f.read().splitlines()

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Security extension was loaded successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if channel := get_guild_prefs(member.guild.id, "suspicious_joins") == 0:
            return
        now = discord.utils.utcnow()
        is_new = member.created_at > (now - datetime.timedelta(days=7))
        checker = self._spam_check[member.guild.id]

        title = "Member Joined"
        if checker.is_fast_join(member):
            colour = 0xDD5F53
            if is_new:
                title = "Member Joined (Very New Member)"
        else:
            colour = 0x53DDA4

            if is_new:
                colour = 0xDDA453
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
        await channel.send(embed=e)

    async def execute_punishments(self, member: discord.Member, guild_id, punishments):
        punishment_msg = None
        if "warn" in punishments:
            exec_warn(guild_id, member.id, "Anti Spam")
            punishment_msg = _T(
                guild_id,
                "warnings.punished",
                member=member.display_name,
                reason="Anti Spam",
            )
        if "day_mute" in punishments:
            await member.timeout(datetime.timedelta(days=1))
            punishment_msg = _T(
                guild_id,
                "punishments_log.day_mute",
                member=member.display_name,
                reason="Anti Spam",
            )
        elif "hour_mute" in punishments:
            await member.timeout(datetime.timedelta(hours=1))
            punishment_msg = _T(
                guild_id,
                "punishments_log.hour_mute",
                member=member.display_name,
                reason="Anti Spam",
            )
        elif "min_mute" in punishments:
            await member.timeout(datetime.timedelta(minutes=5))
            punishment_msg = _T(
                guild_id,
                "punishments_log.min_mute",
                member=member.display_name,
                reason="Anti Spam",
            )
        if "ban" in punishments:
            await member.ban(reason="Anti Spam")
            punishment_msg = _T(
                guild_id,
                "punishments_log.ban",
                member=member.display_name,
                reason="Anti Spam",
            )
        elif "kick" in punishments:
            await member.kick(reason="Anti Spam")
            punishment_msg = _T(
                guild_id,
                "punishments_log.kick",
                member=member.display_name,
                reason="Anti Spam",
            )

        await self.bot.log((guild_id, self.bot.user), punishment_msg)

    async def check_raid(
        self,
        guild_id: int,
        member: discord.Member,
        message: discord.Message,
    ) -> None:
        enabled, punishments = get_guild_prefs(guild_id, "antiraid").values()
        if not enabled:
            return

        checker = self._spam_check[guild_id]
        if not checker.is_spamming(message):
            return

        with contextlib.suppress(Forbidden):
            await self.execute_punishments(member, guild_id, punishments)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        author = message.author
        if author.id in (self.bot.user.id, self.bot.owner_id):
            return
        if message.guild is None or not isinstance(author, discord.Member):
            return
        if author.bot:
            return
        if author.guild_permissions.manage_messages:
            return
        guild_id = message.guild.id

        await self.check_raid(guild_id, author, message)
        if any(link in message.content for link in self.links):
            with contextlib.suppress(Forbidden):
                await self.execute_punishments()

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction):
        guild_id = execution.guild_id
        if execution.rule_trigger_type not in [3, 5]:
            return
        if punishments := get_punishments(guild_id, "antispam") == []:
            return
        member = await self.execute_punishments(member, guild_id, punishments)

    async def enable_antispam(self, i: Interaction, enabled):
        actions = [
            discord.AutoModRuleAction(
                custom_message=_T(i, "antispam.blocked", bot=self.bot.user.name)
            ),
        ]
        rules = await i.guild.fetch_automod_rules()
        for rule in rules:
            if rule.trigger.type.value in [3, 5]:
                await rule.delete()

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
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def antispam(self, i: Interaction, enabled: bool):
        await i.response.defer()
        if not enabled:
            msg = _T(i, "antispam.off")
            await i.followup.send(embed_success(msg))
            await self.bot.log(i, msg)
        else:
            await self.enable_antispam(i)
            view = ConfigurationView(i, self.bot)
            view.message = await i.followup.send(
                view=view, embed=embed_info(_T(i, "antispam.on"))
            )

    @app_commands.command()
    @app_commands.describe(
        suspicious_join_channel="Channel to broadcast new member joins and their potential risk."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def joinwatch(
        self,
        i: Interaction,
        suspicious_join_channel: discord.TextChannel,
        enabled: bool,
    ):
        await set_guild_data(
            i.guild_id, "suspicious_joins", suspicious_join_channel.id if enabled else 0
        )
        msg = _T(
            i, "joinwatch", channel=suspicious_join_channel.name if enabled else "---"
        )
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)

    @app_commands.command()
    @app_commands.describe(
        punishment="Choose a punishment for spammers when a raid is detected."
    )
    @app_commands.choices(
        punishment=[
            Choice(name="Disable", value="disable"),
            Choice(name="Warn", value="warn"),
            Choice(name="5 min mute", value="min_mute"),
            Choice(name="1 hour mute", value="hour_mute"),
            Choice(name="1 day mute", value="day_mute"),
            Choice(name="Kick", value="kick"),
            Choice(name="Ban", value="ban"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def antiraid(self, i, punishment: Choice[str]):
        await i.response.defer()

        await configure_punihsments(i.guild_id, "antiraid", punishment)
        msg = _T(i, "antiraid")
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)

    @app_commands.command()
    @app_commands.describe(
        punishment="Choose a punishment for when a malicious link is detected."
    )
    @app_commands.choices(
        punishment=[
            Choice(name="Disable", value="disable"),
            Choice(name="Warn", value="warn"),
            Choice(name="5 min mute", value="min_mute"),
            Choice(name="1 hour mute", value="hour_mute"),
            Choice(name="1 day mute", value="day_mute"),
            Choice(name="Kick", value="kick"),
            Choice(name="Ban", value="ban"),
        ]
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def linkfilter(self, i, punishment: Choice[str]):
        await i.response.defer()

        await configure_punihsments(i.guild_id, "link_filter", punishment)
        msg = _T(i, "linkfilter")
        await i.followup.send(embed_success(msg))
        await self.bot.log(i, msg)


async def setup(bot):
    await bot.add_cog(Security(bot))
