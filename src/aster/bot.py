import discord
from discord.ext import commands

from aster.config import COGS
from aster.db import init_db
from aster.utils.logger import logger


class Aster(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

    async def setup_hook(self):

        # 長期記憶用のテーブルが無ければ作成する(既にあれば何もしない)
        init_db()

        for cog in COGS:
            await self.load_extension(cog)

        synced = await self.tree.sync()

        logger.info(f"{len(synced)} 個のスラッシュコマンドを同期しました。")

    async def on_ready(self):

        logger.info(f"ログイン: {self.user}")