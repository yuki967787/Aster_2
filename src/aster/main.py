import discord
from discord.ext import commands

from aster.ai import ask_gemini
from aster.config import DISCORD_TOKEN

# =========================
# Botの設定
# =========================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# =========================
# Bot起動時
# =========================

@bot.event
async def on_ready():
    print("=" * 40)
    print(f"{bot.user} が起動しました！")
    print("=" * 40)


# =========================
# メッセージ受信
# =========================

@bot.event
async def on_message(message: discord.Message):

    # Aster自身のメッセージは無視
    if message.author == bot.user:
        return

    # 「入力中...」を表示
    async with message.channel.typing():

        try:
            # Geminiへ送信
            reply = ask_gemini(message.content)

            # Discordは2000文字制限
            if len(reply) > 1900:
                reply = reply[:1900] + "..."

            # 返信
            await message.reply(reply)

        except Exception as e:
            await message.reply(
                f"⚠️ エラーが発生しました。\n```{e}```"
            )

    # コマンドも使えるようにする
    await bot.process_commands(message)


# =========================
# Bot起動
# =========================

bot.run(DISCORD_TOKEN)