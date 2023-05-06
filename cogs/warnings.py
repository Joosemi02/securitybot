from datetime import datetime

from discord import Interaction, Member, app_commands
from discord.ext import commands
from discord.utils import format_dt

from utils import _T, MyBot, Paginator, db, embed_fail, embed_success


async def exec_warn(guild_id: int, user_id: int, reason: str):
    if (warns := await db.warns.find_one({"_id": user_id, "guild": guild_id})) is None:
        warns = {
            "_id": user_id,
            "guild": guild_id,
            "0": [reason, datetime.now()],
        }
        await db.warns.insert_one(warns)
    else:
        del warns["_id"]
        del warns["guild"]
        num = int(list(warns.keys())[-1]) if warns else -1
        await db.warns.update_one(
            {"_id": user_id, "guild": guild_id},
            {"$set": {str(num + 1): [reason, datetime.now()]}},
        )


class Warnings(commands.Cog):
    def __init__(self, bot):
        self.bot: MyBot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"{self.bot.user.name}: Warnings extension loaded successfully.")

    @app_commands.command(description="Warn a user.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def warn(self, i: Interaction, member: Member, reason: str):
        await i.response.defer()
        await exec_warn(i.guild_id, member.id, reason)

        punishment_msg = _T(
            i, "warnings.punish", member=member.display_name, reason=reason
        )
        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)

    async def send_warnings(self, i: Interaction, member: Member = None):
        await i.response.defer()
        if not member:
            member = i.user
        warns = await db.warns.find_one({"_id": member.id, "guild": i.guild_id})
        if warns:
            del warns["_id"]
            del warns["guild"]
        else:
            warns = {}

        paginator = Paginator(interaction=i, objects=warns, username=member.name)
        await paginator.send_message(i)

    @app_commands.command(description="Use this command to check a user's warnings")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def userwarnings(self, i: Interaction, member: Member):
        await self.send_warnings(i, member)

    @app_commands.command(description="Use this command to check your warnings.")
    @app_commands.guild_only()
    async def warnings(self, i: Interaction):
        await self.send_warnings(i)

    @app_commands.command(description="Remove a warning from a member.")
    @app_commands.guild_only()
    @app_commands.default_permissions()
    async def unwarn(self, i: Interaction, member: Member, warn_id: int):
        await i.response.defer()
        warn_id = str(warn_id)
        filter_ = {
            "_id": member.id,
            "guild": i.guild_id,
            warn_id: {"$exists": True},
        }
        if (warn := await db.warns.find_one(filter_)) is None:
            return await i.followup.send(
                embed=embed_fail(i, _T(i, "warning.not_found"))
            )

        await db.warns.update_one(filter_, {"$unset": {warn_id: ""}})

        warning = f"ID: ``{warn_id}`` {warn[warn_id][0]}\n{format_dt(warn[warn_id][1])}"
        punishment_msg = _T(
            i, "warnings.unwarn", member=member.display_name, warning=warning
        )
        await i.followup.send(embed=embed_success(i, punishment_msg))
        await self.bot.log(i, punishment_msg)


async def setup(bot):
    await bot.add_cog(Warnings(bot))
