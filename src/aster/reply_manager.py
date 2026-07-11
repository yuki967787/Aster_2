"""
Asterの返信演出を管理するモジュール。

このモジュールは、
・Typing表示
・送信間隔
・分割送信
を担当します。

将来的には
・VOICEVOX
・スタンプ
・リアクション
などもここに追加します。
"""

from __future__ import annotations

import asyncio
import random

import discord


class ReplyManager:
    """Discordへの返信を管理するクラス。"""

    # 分割送信する確率
    SPLIT_CHANCE = 0.25

    # 送信間隔
    MIN_DELAY = 0.7
    MAX_DELAY = 1.4

    async def send(
        self,
        channel: discord.abc.Messageable,
        text: str,
    ) -> None:
        """
        返信を送信する。

        Parameters
        ----------
        channel
            Discordの送信先
        text
            Geminiが生成した文章
        """

        messages = self._split_message(text)

        for message in messages:

            async with channel.typing():
                await asyncio.sleep(random.uniform(0.4, 1.0))

            await channel.send(message)

            if message != messages[-1]:
                await asyncio.sleep(
                    random.uniform(
                        self.MIN_DELAY,
                        self.MAX_DELAY,
                    )
                )

    def _split_message(self, text: str) -> list[str]:
        """
        必要なら文章を2つに分割する。
        """

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        if len(lines) <= 1:
            return [text]

        if random.random() > self.SPLIT_CHANCE:
            return [text]

        middle = len(lines) // 2

        first = "\n".join(lines[:middle])
        second = "\n".join(lines[middle:])

        return [first, second]