"""
listeners/voice_state.py
------------------------
Discordのボイスチャンネル(VC)入退室を検知して、Asterを追従させるCog。

設計:
- ユーザーがVCに入ったら、3〜7秒のランダムな間を置いてAsterも入室する
  (即座に入ると「待ち構えてた」感じが出て機械的なので、少し遅れて自然に見せる)
- ユーザーがVCから抜けたら、2分の猶予を置く(誤って抜けた・デバイス切り替え等を考慮)。
  猶予の間に別のユーザーが同じVCに居れば退出しない。
- テキストチャンネルでの会話が一定時間(3〜5分のランダム)止まったらAsterも退出する
  (listeners/message.py 側からのメッセージ受信で、このタイマーがリセットされる)

読み上げ(音声合成→再生)自体は listeners/message.py 側から呼ばれる
(Asterが実際にテキストで返信したタイミングで読み上げるため)。
このファイルはVCへの接続・切断の管理に専念する。
"""

from __future__ import annotations

import asyncio
import random

import discord
from discord.ext import commands

from aster.config import (
    VOICE_IDLE_TIMEOUT_MAX,
    VOICE_IDLE_TIMEOUT_MIN,
    VOICE_JOIN_DELAY_MAX,
    VOICE_JOIN_DELAY_MIN,
    VOICE_USER_LEFT_GRACE_SECONDS,
)
from aster.utils.logger import logger


class VoiceStateListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # guild_id -> 「ユーザーが抜けたので退出を検討する」猶予タスク
        self._leave_grace_tasks: dict[int, asyncio.Task] = {}
        # guild_id -> 「会話が止まったので退出する」アイドルタイマー
        self._idle_tasks: dict[int, asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        # Aster自身の状態変化には反応しない
        if member.id == self.bot.user.id:
            return

        # ユーザーがVCに新しく入室した場合
        if before.channel is None and after.channel is not None:
            await self._on_user_joined(after.channel)

        # ユーザーがVCから退出した場合
        elif before.channel is not None and after.channel is None:
            await self._on_user_left(before.channel)

    async def _on_user_joined(self, channel: discord.VoiceChannel):
        guild = channel.guild

        # 既にAsterがそのギルドのどこかのVCに居るなら、何もしない
        if guild.voice_client is not None:
            return

        delay = random.uniform(VOICE_JOIN_DELAY_MIN, VOICE_JOIN_DELAY_MAX)
        await asyncio.sleep(delay)

        # 待っている間にユーザーが抜けてしまっていたら参加しない
        if not channel.members or all(m.bot for m in channel.members):
            return

        try:
            await channel.connect()
            logger.info(f"VCに参加しました: {channel.name}")
            self._reset_idle_timer(guild)
        except discord.ClientException as e:
            logger.warning(f"VCへの参加に失敗しました: {e}")

    async def _on_user_left(self, channel: discord.VoiceChannel):
        guild = channel.guild
        voice_client = guild.voice_client

        if voice_client is None:
            return

        # Aster以外の人間がまだ同じVCに残っていれば、何もしない
        remaining_humans = [m for m in voice_client.channel.members if not m.bot]
        if remaining_humans:
            return

        # 前回の猶予タスクが残っていればキャンセルしてから、新しく猶予を置く
        pending = self._leave_grace_tasks.get(guild.id)
        if pending and not pending.done():
            pending.cancel()

        self._leave_grace_tasks[guild.id] = asyncio.create_task(
            self._leave_after_grace_period(guild)
        )

    async def _leave_after_grace_period(self, guild: discord.Guild):
        try:
            await asyncio.sleep(VOICE_USER_LEFT_GRACE_SECONDS)
        except asyncio.CancelledError:
            # 猶予中に誰か戻ってきた等で取り消されただけ
            return

        voice_client = guild.voice_client
        if voice_client is None:
            return

        remaining_humans = [m for m in voice_client.channel.members if not m.bot]
        if remaining_humans:
            # 猶予の間に別の人が入ってきていた場合は退出しない
            return

        await voice_client.disconnect()
        logger.info(f"VCから退出しました(誰もいなくなったため): {guild.name}")

    def _reset_idle_timer(self, guild: discord.Guild):
        """
        「会話が止まったら退出する」タイマーをリセットする。
        listeners/message.py からAsterが返信するたびに呼ばれる想定。
        """

        pending = self._idle_tasks.get(guild.id)
        if pending and not pending.done():
            pending.cancel()

        self._idle_tasks[guild.id] = asyncio.create_task(
            self._leave_after_idle_timeout(guild)
        )

    async def _leave_after_idle_timeout(self, guild: discord.Guild):
        timeout = random.uniform(VOICE_IDLE_TIMEOUT_MIN, VOICE_IDLE_TIMEOUT_MAX)

        try:
            await asyncio.sleep(timeout)
        except asyncio.CancelledError:
            return

        voice_client = guild.voice_client
        if voice_client is None:
            return

        await voice_client.disconnect()
        logger.info(f"VCから退出しました(会話が止まったため): {guild.name}")

    def notify_activity(self, guild: discord.Guild) -> None:
        """
        Asterが実際に会話した時に呼ばれる、外部向けの合図。
        VCに参加している場合のみアイドルタイマーをリセットする。
        """

        if guild.voice_client is not None:
            self._reset_idle_timer(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceStateListener(bot))