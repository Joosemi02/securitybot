import asyncio
import os
import sys
import time
import traceback

from discord import Intents
from discord.ext import commands

from constants import APPLICATION_ID, TOKEN
from utils import _T, MyBot, embed_fail

bot: commands.Bot | MyBot = MyBot(
    command_prefix=commands.when_mentioned,
    intents=Intents.all(),
    application_id=APPLICATION_ID,
)
bot.start_time = time.time()


@bot.event
async def on_ready():
    print(f"{bot.user.name}: Bot started successfully.")


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        embed = embed_fail(ctx, _T(ctx, "command_fail.no_admin"))
        await ctx.reply(
            embed=embed,
            delete_after=5,
        )
        await ctx.message.delete(delay=5)
    else:
        print(
            f"Ignoring exception in command {ctx.command}:",
            file=sys.stderr,
        )
        traceback.print_exception(
            type(error), error, error.__traceback__, file=sys.stderr
        )


async def load_extensions():
    for extension in os.listdir("cogs"):
        if extension.endswith(".py"):
            await bot.load_extension(f"cogs.{extension.removesuffix('.py')}")


asyncio.run(load_extensions())
bot.run(TOKEN)
