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
        print(f"{self.bot.user.name}: The Security extension was loaded successfully.")

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

