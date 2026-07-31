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
    ) -> list[discord.Message]:
        """
        返信を送信する。

        Parameters
        ----------
        channel
            Discordの送信先
        text
            Geminiが生成した文章

        Returns
        -------
        list[discord.Message]
            実際に送信したメッセージのリスト(分割送信された場合は複数)。
            呼び出し側でリアクションを付けたい時などに使う。
        """

        messages = self._split_message(text)
        sent: list[discord.Message] = []

        for message in messages:

            async with channel.typing():
                await asyncio.sleep(random.uniform(0.4, 1.0))

            sent_message = await channel.send(message)
            sent.append(sent_message)

            if message != messages[-1]:
                await asyncio.sleep(
                    random.uniform(
                        self.MIN_DELAY,
                        self.MAX_DELAY,
                    )
                )

        return sent

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