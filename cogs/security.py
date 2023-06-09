import contextlib
import datetime
import time
from collections import defaultdict
from typing import Iterable, List, MutableMapping, Optional

from discord import (
    AutoModAction,
    AutoModRuleAction,
    AutoModRuleEventType,
    AutoModRuleTriggerType,
    AutoModTrigger,
    ChannelType,
    Embed,
    Interaction,
    Member,
    Message,
    TextChannel,
    app_commands,
)
from discord.components import MISSING, SelectOption
from discord.errors import Forbidden
from discord.ext import commands
from discord.interactions import Interaction
from discord.ui import ChannelSelect, Select, View
from discord.utils import format_dt, utcnow

from utils import (
    _T,
    MyBot,
    embed_success,
    get_guild_prefs,
    get_punishments,
    set_guild_data,
)

from .warnings import exec_warn


# AntiSpam
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
    def _bucket_key(self, message: Message) -> tuple[int, str]:
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

    def is_new(self, member: Member) -> bool:
        now = utcnow()
        seven_days_ago = now - datetime.timedelta(days=7)
        ninety_days_ago = now - datetime.timedelta(days=90)
        return (
            member.created_at > ninety_days_ago
            and member.joined_at is not None
            and member.joined_at > seven_days_ago
        )

    def is_spamming(self, message: Message) -> bool:
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

    def is_fast_join(self, member: Member) -> bool:
        joined = member.joined_at or utcnow()
        if self.last_join is None:
            self.last_join = joined
            return False
        is_fast = (joined - self.last_join).total_seconds() <= 2.0
        self.last_join = joined
        if is_fast:
            self.fast_joiners[member.id] = True
        return is_fast


# Views
class NotifySelect(ChannelSelect):
    def __init__(self, placeholder: str, bot: MyBot):
        super().__init__(
            placeholder=placeholder,
            min_values=0,
            max_values=1,
            channel_types=[ChannelType.text],
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
                    actions.append(AutoModRuleAction(channel_id=channel_id))
                    await rule.edit(actions=actions)
        else:
            channel_id = 0
            channel_name = "---"
        msg = _T(i, "security.notify", module=self.view.category, channel=channel_name)
        await i.followup.send(embed=embed_success(i, msg))
        await self.bot.log(i, msg)


class ActionSelect(Select):
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
        category = self.view.category
        if category == "linkfilter":
            await self.create_automod_linkfilter(i)
        await set_guild_data(i.guild_id, f"{category}.punishments", self.values)
        msg = _T(i, "security.config", module=category)
        await i.followup.send(embed=embed_success(i, msg))
        await self.bot.log(i, msg)

    async def create_automod_linkfilter(self, i):
        rules = await i.guild.fetch_automod_rules()
        for rule in rules:
            if rule.trigger.type.value == 3:
                await rule.delete()

        await i.guild.create_automod_rule(
            name=f"{self.bot.user.name} - Anti Spam",
            event_type=AutoModRuleEventType.message_send,
            trigger=AutoModTrigger(type=AutoModRuleTriggerType.spam),
            actions=[
                AutoModRuleAction(
                    custom_message=_T(
                        i,
                        "security.blocked",
                        module="antispam",
                        bot=self.bot.user.name,
                    )
                ),
            ],
            enabled=True,
        )


class ConfigurationView(View):
    def __init__(self, i: Interaction, bot, category: str):
        super().__init__()
        self.i = i
        self.category = category
        actions = {
            "warn": "🪧",
            "min_mute": "⌛",
            "hour_mute": "🕛",
            "day_mute": "📆",
            "kick": "🦶",
            "ban": "🔨",
        }
        placeholder = _T(i, "punishments.choose")
        options = [
            SelectOption(
                label=_T(i, f"punishments.{action}"),
                value=action,
                emoji=emoji,
                default=action in get_punishments(i.guild_id, category),
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
        self.add_item(NotifySelect(_T(i, "punishments.choose_channel"), bot))

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
    async def on_member_join(self, member: Member):
        if (channel := get_guild_prefs(member.guild.id, "joinwatch")) == 0:
            return
        now = utcnow()
        is_new = member.created_at > (now - datetime.timedelta(days=7))
        checker = self._spam_check[member.guild.id]

        title = "Member Joined"
        if checker.is_fast_join(member):
            colour = 0xDD5F53
            if is_new:
                title = "Member Joined (Very New Member)"
            if "COMMUNITY" in member.guild.features:
                await member.guild.edit(invites_disabled=True)
        else:
            colour = 0x53DDA4

            if is_new:
                colour = 0xDDA453
                title = "Member Joined (Very New Member)"

        e = Embed(title=title, colour=colour, timestamp=now)
        e.set_author(name=str(member), icon_url=member.display_avatar.url)
        e.set_footer(
            icon_url=self.bot.user.display_avatar.url,
            text=self.bot.user.name,
        )
        e.add_field(name="ID", value=member.id)
        assert member.joined_at is not None
        e.add_field(name="Joined", value=format_dt(member.joined_at, "F"))
        e.add_field(
            name="Created", value=format_dt(member.created_at, "R"), inline=False
        )
        await self.bot.get_channel(channel).send(embed=e)

    async def execute_punishments(
        self, member: Member, guild_id, punishments, reason: str
    ):
        punishment_msg = None
        if "warn" in punishments:
            await exec_warn(guild_id, member.id, reason)
            punishment_msg = _T(
                guild_id,
                "warnings.punish",
                member=member.display_name,
                reason=reason,
            )
        if "day_mute" in punishments:
            await member.timeout(datetime.timedelta(days=1))
            punishment_msg = _T(
                guild_id,
                "punishments_log.day_mute",
                member=member.display_name,
                reason=reason,
            )
        elif "hour_mute" in punishments:
            await member.timeout(datetime.timedelta(hours=1))
            punishment_msg = _T(
                guild_id,
                "punishments_log.hour_mute",
                member=member.display_name,
                reason=reason,
            )
        elif "min_mute" in punishments:
            await member.timeout(datetime.timedelta(minutes=5))
            punishment_msg = _T(
                guild_id,
                "punishments_log.min_mute",
                member=member.display_name,
                reason=reason,
            )
        if "ban" in punishments:
            await member.ban(reason=reason)
            punishment_msg = _T(
                guild_id,
                "punishments_log.ban",
                member=member.display_name,
                reason=reason,
            )
        elif "kick" in punishments:
            await member.kick(reason=reason)
            punishment_msg = _T(
                guild_id,
                "punishments_log.kick",
                member=member.display_name,
                reason=reason,
            )

        await self.bot.log((guild_id, self.bot.user), punishment_msg)

    async def check_raid(
        self,
        guild_id: int,
        member: Member,
        message: Message,
    ) -> None:
        enabled, punishments = get_guild_prefs(guild_id, "antispam").values()
        if not enabled:
            return

        checker = self._spam_check[guild_id]
        if not checker.is_spamming(message):
            return

        with contextlib.suppress(Forbidden):
            await self.execute_punishments(member, guild_id, punishments, "Anti Raid")

    @commands.Cog.listener()
    async def on_message(self, message: Message):
        author = message.author
        if author.id in (self.bot.user.id, self.bot.owner_id):
            return
        if message.guild is None or not isinstance(author, Member):
            return
        if author.bot:
            return
        if author.guild_permissions.manage_messages:
            return
        guild_id = message.guild.id

        await self.check_raid(guild_id, author, message)
        if not get_guild_prefs(guild_id, "linkfilter")["enabled"]:
            return
        if any(word in self.links for word in message.content.split(" ")):
            with contextlib.suppress(Forbidden):
                await message.delete()
                await self.execute_punishments(
                    author, guild_id, get_punishments(guild_id, "linkfilter")
                )

    @commands.Cog.listener()
    async def on_automod_action(self, execution: AutoModAction):
        guild_id = execution.guild_id
        if execution.rule_trigger_type == 3:
            category = "linkfilter"
        elif execution.rule_trigger_type == 5:
            category = "antispam"
        else:
            return
        if (punishments := get_punishments(guild_id, category)) == []:
            return
        await self.execute_punishments(
            execution.member, guild_id, punishments, "Anti Spam"
        )

    async def enable_anti_mentionspam(self, i: Interaction, enabled):
        actions = [
            AutoModRuleAction(
                custom_message=_T(
                    i, "security.blocked", module="antispam", bot=self.bot.user.name
                )
            ),
        ]
        rules = await i.guild.fetch_automod_rules()
        for rule in rules:
            if rule.trigger.type.value == 5:
                await rule.delete()

        mention_spam_trigger = AutoModTrigger(
            type=AutoModRuleTriggerType.mention_spam, mention_limit=10
        )
        await i.guild.create_automod_rule(
            name=f"{self.bot.user.name} - Anti Mention Spam",
            event_type=AutoModRuleEventType.message_send,
            trigger=mention_spam_trigger,
            actions=actions,
            enabled=enabled,
        )

    @app_commands.command(
        description="Prevent spam and raids in your server with several spam detection methods."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def antispam(self, i: Interaction, enabled: bool):
        await i.response.defer()
        await self.enable_anti_mentionspam(i, enabled)
        await set_guild_data(i.guild_id, "antispam.enabled", enabled)

        msg = _T(i, f"security.{'on' if enabled else 'off'}", module="Anti Spam")
        view = ConfigurationView(i, self.bot, "antispam")
        view.message = await i.followup.send(
            embed=embed_success(i, msg),
            view=view if enabled else MISSING,
        )
        await self.bot.log(i, msg)

    @app_commands.command(description="Filter phishing and spam links in your server")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def linkfilter(self, i: Interaction, enabled: bool):
        await i.response.defer()

        if not enabled:
            rules = await i.guild.fetch_automod_rules()
            for rule in rules:
                if rule.trigger.type.value == 3:
                    await rule.delete()
        await set_guild_data(i.guild_id, "linkfilter.enabled", enabled)

        msg = _T(
            i, f"security.{'on' if enabled else 'off'}", module="Malicious link filter"
        )
        view = ConfigurationView(i, self.bot, "linkfilter")
        view.message = await i.followup.send(
            embed=embed_success(i, msg),
            view=view if enabled else MISSING,
        )
        await self.bot.log(i, msg)

    @app_commands.command(description="Broadcast new member join in the chosen channel")
    @app_commands.describe(
        suspicious_join_channel="Channel to broadcast new member joins and their potential risk."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def joinwatch(
        self,
        i: Interaction,
        suspicious_join_channel: TextChannel,
        enabled: bool,
    ):
        await i.response.defer()
        await set_guild_data(
            i.guild_id, "joinwatch", suspicious_join_channel.id if enabled else 0
        )
        msg = _T(
            i, "joinwatch", channel=suspicious_join_channel.name if enabled else "---"
        )
        await i.followup.send(embed=embed_success(i, msg))
        await self.bot.log(i, msg)


async def setup(bot):
    await bot.add_cog(Security(bot))
