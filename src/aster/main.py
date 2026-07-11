import discord
from discord.ext import commands

from dotenv import load_dotenv

import os

from aster.ai import ask_gemini

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"{bot.user} が起動しました")


@bot.event
async def on_message(message):

    if message.author.bot:
        return

    async with message.channel.typing():

        try:

            reply = ask_gemini(message.content)

            if len(reply) > 1900:
                reply = reply[:1900] + "..."

            await message.reply(reply)

        except Exception as e:

            await message.reply(f"エラー:\n{e}")

    await bot.process_commands(message)


bot.run(TOKEN)