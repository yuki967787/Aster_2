from discord.ext import commands
from discord import app_commands
import discord


class Help(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="help",
        description="Asterのヘルプを表示します"
    )
    async def help_command(self, interaction: discord.Interaction):

        embed = discord.Embed(
            title="🌟 Aster Help",
            description="現在利用できるコマンド",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="/ping",
            value="Botの応答速度",
            inline=False
        )

        embed.set_footer(text="Aster v0.1.0")

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))