"""
listeners/voice_receive.py
--------------------------
Discord VCから音声を受信し、ユーザーごとに無音区間で発話を区切って
ローカルWhisperへ渡すモジュール。

必要なもの:
    pip install discord-ext-voice-recv openai-whisper

音声は常時WAVファイルとして保存しません。
発話中のPCMをメモリ上に保持し、無音になった時点でWAV形式の
バイト列を作ってWhisperへ渡します。
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from dataclasses import dataclass, field

import discord
from discord.ext import commands, voice_recv

logger = logging.getLogger("aster.voice_receive")

# Discordから受信するPCMの基本値
SAMPLE_RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2

# Whisperが前提とするサンプリングレート。
# Discordの48kHzのままWhisperへ渡すと、実際の3倍速で
# 再生されているかのように扱われてしまうため、
# 文字起こし前に16kHzへ変換する必要がある。
WHISPER_SAMPLE_RATE = 16000

# この時間、音声データが来なければ発話を確定する
VOICE_SILENCE_SECONDS = 1.2

# あまりに短い音声はWhisperへ送らない
MIN_AUDIO_SECONDS = 0.35

# Whisperモデル
WHISPER_MODEL = "base"


@dataclass
class UserAudioBuffer:
    """ユーザー1人分の発話を一時的に保持する。"""

    member: discord.Member
    chunks: list[bytes] = field(default_factory=list)
    last_received: float = field(default_factory=time.monotonic)

    @property
    def size(self) -> int:
        return sum(len(chunk) for chunk in self.chunks)


class VoiceReceiveSink(voice_recv.AudioSink):
    """
    Discordから受信したPCMをユーザー別に蓄積するSink。

    Aster自身の音声は認識対象から除外する。
    """

    def __init__(self, manager: "VoiceReceiveManager"):
        super().__init__()
        self.manager = manager
        self.buffers: dict[int, UserAudioBuffer] = {}

    def wants_opus(self) -> bool:
        # PCMとして受け取る
        return False

    def write(self, user, data: voice_recv.VoiceData) -> None:
        if user is None:
            return

        # Aster自身の発話を認識対象から除外
        if self.manager.bot.user and user.id == self.manager.bot.user.id:
            return

        member = user

        if not isinstance(member, discord.Member):
            return

        buffer = self.buffers.get(member.id)

        if buffer is None:
            buffer = UserAudioBuffer(member=member)
            self.buffers[member.id] = buffer

        buffer.chunks.append(data.pcm)
        buffer.last_received = time.monotonic()

    def cleanup(self) -> None:
        self.buffers.clear()


class VoiceReceiveManager:
    """Guildごとの音声受信とWhisper文字起こしを管理する。"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sinks: dict[int, VoiceReceiveSink] = {}
        self._tasks: dict[int, asyncio.Task] = {}

        # Whisperモデル
        self._whisper = None
        self._whisper_loading = False

    async def start(
        self,
        guild: discord.Guild,
        voice_client,
    ) -> None:
        """VoiceRecvClientにSinkを取り付けて音声受信を開始する。"""

        if not isinstance(voice_client, voice_recv.VoiceRecvClient):
            logger.warning(
                "VoiceRecvClientではないため音声受信を開始できません"
            )
            return

        if (
            guild.id in self._tasks
            and not self._tasks[guild.id].done()
        ):
            return

        sink = VoiceReceiveSink(self)
        self._sinks[guild.id] = sink

        voice_client.listen(
            sink,
            after=lambda error: self._receive_finished(
                guild.id,
                error,
            ),
        )

        self._tasks[guild.id] = asyncio.create_task(
            self._monitor_silence(guild)
        )

        logger.info(
            "音声受信を開始しました: %s",
            guild.name,
        )

    def stop(self, guild: discord.Guild) -> None:
        """Guildの音声受信を停止する。"""

        task = self._tasks.pop(guild.id, None)

        if task and not task.done():
            task.cancel()

        self._sinks.pop(guild.id, None)

        voice_client = guild.voice_client

        if isinstance(
            voice_client,
            voice_recv.VoiceRecvClient,
        ):
            if voice_client.is_listening():
                voice_client.stop_listening()

    def _receive_finished(
        self,
        guild_id: int,
        error: Exception | None,
    ) -> None:
        """音声受信終了時のログを記録する。"""

        if error:
            logger.error(
                "音声受信が終了しました: guild_id=%s error=%s",
                guild_id,
                error,
            )
        else:
            logger.info(
                "音声受信が終了しました: guild_id=%s",
                guild_id,
            )

    async def _monitor_silence(
        self,
        guild: discord.Guild,
    ) -> None:
        """無音になったユーザーの発話を確定する。"""

        try:
            while guild.voice_client is not None:
                sink = self._sinks.get(guild.id)

                if sink is None:
                    return

                now = time.monotonic()
                finished: list[UserAudioBuffer] = []

                for buffer in list(sink.buffers.values()):
                    if (
                        buffer.chunks
                        and now - buffer.last_received
                        >= VOICE_SILENCE_SECONDS
                    ):
                        finished.append(buffer)
                        del sink.buffers[buffer.member.id]

                for buffer in finished:
                    await self._process_buffer(
                        guild,
                        buffer,
                    )

                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            return

        except Exception:
            logger.exception(
                "音声受信監視でエラーが発生しました"
            )

    async def _process_buffer(
        self,
        guild: discord.Guild,
        buffer: UserAudioBuffer,
    ) -> None:
        """1回分の発話をWhisperへ渡して処理する。"""

        pcm = b"".join(buffer.chunks)

        duration = len(pcm) / (
            SAMPLE_RATE
            * CHANNELS
            * SAMPLE_WIDTH
        )

        logger.info(
            "発話を確定しました: guild=%s user=%s duration=%.2fs",
            guild.name,
            buffer.member.display_name,
            duration,
        )

        # 短すぎる音声はWhisperへ渡さない
        if duration < MIN_AUDIO_SECONDS:
            logger.info(
                "音声が短すぎるため文字起こしをスキップします: %.2fs",
                duration,
            )
            return

        wav_bytes = self._pcm_to_wav(pcm)

        text = await self._transcribe(wav_bytes)
        text = text.strip()

        if not text:
            logger.info(
                "Whisperが空の文字起こしを返しました"
            )
            return

        logger.info(
            "音声認識: %s: %s",
            buffer.member.display_name,
            text,
        )

        message_cog = self.bot.get_cog(
            "MessageListener"
        )

        if message_cog is None:
            logger.warning(
                "MessageListenerが見つかりません"
            )
            return

        await message_cog.handle_voice_text(
            guild=guild,
            member=buffer.member,
            text=text,
        )

    @staticmethod
    def _pcm_to_wav(pcm: bytes) -> bytes:
        """PCMをWAV形式のメモリ上のバイト列へ変換する。"""

        output = io.BytesIO()

        with wave.open(output, "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm)

        return output.getvalue()

    async def _load_whisper(self):
        """
        Whisperモデルを初回だけロードする。

        CPUでのモデルロードは重いため、
        イベントループを止めないよう別スレッドで実行する。
        """

        if self._whisper is not None:
            return self._whisper

        if self._whisper_loading:
            while self._whisper is None:
                await asyncio.sleep(0.1)

            return self._whisper

        self._whisper_loading = True

        try:
            import whisper

            logger.info(
                "Whisperモデルをロードしています: %s",
                WHISPER_MODEL,
            )

            self._whisper = await asyncio.to_thread(
                whisper.load_model,
                WHISPER_MODEL,
            )

            logger.info(
                "Whisperモデルのロードが完了しました"
            )

            return self._whisper

        finally:
            self._whisper_loading = False

    async def _transcribe(
        self,
        wav_bytes: bytes,
    ) -> str:
        """WAVバイト列をローカルWhisperで文字起こしする。"""

        model = await self._load_whisper()

        def transcribe() -> str:
            import numpy as np
            import soundfile as sf

            logger.info(
                "Whisperによる文字起こしを開始します"
            )

            # メモリ上のWAVを読み込む
            audio, sample_rate = sf.read(
                io.BytesIO(wav_bytes),
                dtype="float32",
            )

            logger.info(
                "音声データを読み込みました: "
                "sample_rate=%s channels=%s samples=%s",
                sample_rate,
                1 if audio.ndim == 1 else audio.shape[1],
                len(audio),
            )

            # ステレオ → モノラル
            if audio.ndim > 1:
                audio = audio.mean(axis=1)

            # Whisperが扱いやすいようfloat32へ統一
            audio = np.asarray(
                audio,
                dtype=np.float32,
            )

            # 【修正】Whisperは16kHzのnumpy配列を前提としているため、
            # Discordの48kHzのまま渡すと実際の3倍速で再生したかのように
            # 扱われ、短い発話が正しく認識できなくなる(空文字になる)。
            # ここで16kHzへリサンプリングしてからWhisperへ渡す。
            if sample_rate != WHISPER_SAMPLE_RATE:
                audio = _resample_linear(
                    audio, sample_rate, WHISPER_SAMPLE_RATE
                )

                logger.info(
                    "リサンプリングしました: %sHz → %sHz (samples=%s)",
                    sample_rate,
                    WHISPER_SAMPLE_RATE,
                    len(audio),
                )

            # Whisperで文字起こし
            result = model.transcribe(
                audio,
                language="ja",
                fp16=False,
                temperature=0,
                condition_on_previous_text=False,
            )

            text = result.get(
                "text",
                "",
            ).strip()

            logger.info(
                "Whisperの文字起こしが完了しました: %r",
                text,
            )

            return text

        try:
            return await asyncio.to_thread(
                transcribe
            )

        except Exception:
            logger.exception(
                "Whisperによる音声認識に失敗しました"
            )
            return ""


def _resample_linear(audio, orig_rate: int, target_rate: int):
    """
    線形補間による簡易リサンプリング。

    scipyやlibrosaのような専用ライブラリを追加せずに、
    numpyだけでサンプリングレートを変換する。
    Whisperへ渡す音声の変換程度であれば、線形補間でも
    (専用ライブラリを使った高品質な変換と比べて多少劣るとしても)
    文字起こしの精度に問題が出るほどの劣化にはならない。
    """

    import numpy as np

    if orig_rate == target_rate or len(audio) == 0:
        return audio

    duration = len(audio) / orig_rate
    target_length = int(duration * target_rate)

    original_indices = np.linspace(0, len(audio) - 1, num=len(audio))
    target_indices = np.linspace(0, len(audio) - 1, num=target_length)

    return np.interp(target_indices, original_indices, audio).astype(np.float32)


class VoiceReceiveListener(commands.Cog):
    """VoiceReceiveManagerをBotへ接続するCog。"""

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot
        self.manager = VoiceReceiveManager(bot)

    async def start_for_guild(
        self,
        guild: discord.Guild,
    ) -> None:
        if guild.voice_client is not None:
            await self.manager.start(
                guild,
                guild.voice_client,
            )

    def stop_for_guild(
        self,
        guild: discord.Guild,
    ) -> None:
        self.manager.stop(guild)


async def setup(bot: commands.Bot):
    await bot.add_cog(
        VoiceReceiveListener(bot)
    )