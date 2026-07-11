from discord.ext import commands
from discord import app_commands
import discord


class Ping(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Botの応答速度を確認します"
    )
    async def ping(self, interaction: discord.Interaction):

        latency = round(self.bot.latency * 1000)

        await interaction.response.send_message(
            f"🏓 Pong!\n{latency} ms"
        )


async def setup(bot):
    await bot.add_cog(Ping(bot))