import discord
from discord.ext import commands

from aster.ai import ask_gemini


class MessageListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # 自分自身のメッセージだけ無視
        if message.author == self.bot.user:
            return

        # 入力中表示
        async with message.channel.typing():

            try:

                reply = ask_gemini(message.content)

                if len(reply) > 1900:
                    reply = reply[:1900] + "..."

                await message.reply(reply)

            except Exception as e:

                await message.reply(
                    f"エラーが発生しました。\n{e}"
                )


async def setup(bot):
    await bot.add_cog(MessageListener(bot))