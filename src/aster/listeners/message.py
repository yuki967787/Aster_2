import asyncio
import io

import discord
from discord.ext import commands

from aster.ai import MAX_IMAGES, ask_gemini, describe_image, extract_memory_update
from aster.pdf import process_pdf
from aster.db import get_notes, save_notes
from aster.error_messages import (
    get_busy_message,
    get_failed_message,
    get_unknown_message,
)
from aster.handwriting import render_note
from aster.memory import ConversationHistory
from aster.note_messages import get_note_wait_message
from aster.utils.logger import logger
from aster.reply_manager import ReplyManager
from aster.voice import VoicevoxError, synthesize


# 何秒発言が無かったら「会話が一区切りついた」とみなし、
# 長期記憶の自動抽出を実行する
MEMORY_EXTRACTION_DELAY = 300  # 5分


class MessageListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # このCogが生きている間だけ保持される短期記憶
        self.history = ConversationHistory()

        # タイピング演出・分割送信を担当
        self.reply_manager = ReplyManager()

        # user_id -> 長期記憶抽出待ちタスク
        self._pending_extraction: dict[int, asyncio.Task] = {}

    async def handle_voice_text(
        self,
        guild: discord.Guild,
        member: discord.Member,
        text: str,
    ) -> None:
        """
        音声認識結果を受け取り、
        Geminiで応答を生成してテキストチャンネルへ送信する。

        普通の会話:
            🎤 → Gemini → 💬テキスト + 🔊VC読み上げ

        ノートが必要な質問:
            🎤 → Gemini → 📝ノート画像
            → VCでは「ノートを送ったよ」とだけ通知
        """

        if not text.strip():
            return

        user_id = member.id
        display_name = member.display_name

        # Botが発言できるテキストチャンネルを探す
        channel = guild.system_channel or next(
            (
                c
                for c in guild.text_channels
                if c.permissions_for(guild.me).send_messages
            ),
            None,
        )

        if channel is None:
            logger.warning(
                "送信可能なテキストチャンネルが見つかりません: guild=%s",
                guild.name,
            )
            return

        channel_id = channel.id

        # 1. 音声入力を短期記憶へ保存
        self.history.add(channel_id, display_name, text)
        history_context = self.history.get_context(channel_id)

        # 2. 長期記憶を取得
        long_term_notes = get_notes(user_id)

        # 3. Geminiへ送信
        # 【修正】ask_geminiは同期関数(内部でHTTP通信のブロッキング待ちが発生する)。
        # VC音声受信と同じイベントループ上でそのままawait無しに呼ぶと、
        # 応答が返るまでの数秒間ループ全体が止まり、VC接続のheartbeatが
        # 途切れる(voice heartbeat blocked)原因になる。
        # asyncio.to_threadで別スレッドに逃がすことでループを塞がないようにする。
        try:
            chat_intro, reply, emoji, is_note = await asyncio.to_thread(
                ask_gemini,
                text,
                history_context=history_context,
                long_term_notes=long_term_notes,
                images=None,
            )

            if len(reply) > 1900:
                reply = reply[:1900] + "..."

        except Exception as e:
            logger.exception(
                "Gemini呼び出しに失敗しました (Voice): %s",
                e,
            )

            error_text = str(e)

            if "503" in error_text or "overloaded" in error_text.lower():
                reply = get_busy_message()
            elif "429" in error_text or "quota" in error_text.lower():
                reply = get_failed_message()
            else:
                reply = get_unknown_message()

            # エラー内容をテキストチャンネルへ送信
            await channel.send(reply)

            # VCにもエラーを通知
            await self._speak(guild, reply)
            return

        # 4. Asterの返答を短期記憶へ保存
        note_for_history = (
            f"{chat_intro} {reply}".strip()
            if chat_intro
            else reply
        )

        self.history.add(
            channel_id,
            "Aster",
            note_for_history,
        )

        # --------------------------------------------------
        # 5. 音声入力に対する返答
        # --------------------------------------------------

        if is_note:
            # ==============================
            # 🎤 → 📝 ノートモード
            # ==============================

            # まず「ノートを作るよ」という前置きを送信
            await channel.send(
                chat_intro or get_note_wait_message()
            )

            try:
                # ノート画像を生成
                async with channel.typing():
                    image_bytes = render_note(reply)

                # ノート画像を送信
                sent_messages = [
                    await channel.send(
                        file=discord.File(
                            io.BytesIO(image_bytes),
                            filename="note.png",
                        )
                    )
                ]

                # VCではノートの内容を読み上げない。
                # 「ノートを送った」ことだけ知らせる。
                await self._speak(
                    guild,
                    "ノートにまとめたよ。",
                )

            except Exception as e:
                logger.exception(
                    "ノート画像の生成に失敗しました: %s",
                    e,
                )

                # ノート生成に失敗した場合だけ、
                # 通常のテキストとして送信する。
                sent_messages = await self.reply_manager.send(
                    channel,
                    reply,
                )

                # 失敗した場合は内容をVCで読み上げる
                await self._speak(guild, reply)

        else:
            # ==============================
            # 🎤 → 💬 + 🔊 通常会話モード
            # ==============================

            sent_messages = await self.reply_manager.send(
                channel,
                reply,
            )

            # VCで返答を読み上げる
            await self._speak(guild, reply)

        # 6. アイドルタイマー更新
        voice_cog = self.bot.get_cog("VoiceStateListener")

        if voice_cog is not None:
            voice_cog.notify_activity(guild)

        # 7. リアクション
        if emoji and sent_messages:
            try:
                await sent_messages[-1].add_reaction(emoji)
            except discord.HTTPException as e:
                logger.warning(
                    "リアクションの追加に失敗しました: %s",
                    e,
                )

        # 8. 長期記憶抽出をスケジュール
        self._schedule_memory_extraction(
            user_id,
            display_name,
            channel_id,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Aster自身のメッセージは無視
        if message.author == self.bot.user:
            return

        channel_id = message.channel.id
        user_id = message.author.id
        display_name = message.author.display_name

        # 添付画像を取得
        images = await self._extract_images(message)

        # PDFを処理
        pdf_context = ""
        pdf_history = ""
        pdf_warning = ""

        try:
            pdf_data = await self._extract_pdf(message)

            if pdf_data is not None:
                pdf_result = process_pdf(pdf_data)

                pdf_context = pdf_result.text
                pdf_history = (
                    f"[添付PDF: {pdf_result.page_count}ページ]"
                )

                if pdf_result.unreadable_pages:
                    pages = ", ".join(
                        map(str, pdf_result.unreadable_pages)
                    )

                    pdf_warning = (
                        f"ごめん、PDFの{pages}ページ目は"
                        "ちょっと読み取りにくかったかも…。"
                    )

        except ValueError as e:
            logger.warning(
                "PDFの処理を中止しました: %s",
                e,
            )
            pdf_warning = str(e)

        except Exception as e:
            logger.exception(
                "PDFの読み取りに失敗しました: %s",
                e,
            )
            pdf_warning = (
                "ごめん、PDFをうまく読み取れなかったかも…。"
            )

        # --------------------------------------------------
        # 短期記憶用のテキストを作成
        # --------------------------------------------------

        history_text = message.content

        if images:
            try:
                caption = describe_image(images)

                history_text = (
                    f"{history_text} "
                    f"[添付画像: {caption}]"
                ).strip()

            except Exception as e:
                logger.exception(
                    "画像の説明生成に失敗しました: %s",
                    e,
                )

                history_text = (
                    f"{history_text} "
                    f"[画像を{len(images)}枚送信]"
                ).strip()

        if pdf_history:
            history_text = (
                f"{history_text} {pdf_history}"
            ).strip()

        # ユーザー発言を短期記憶へ保存
        self.history.add(
            channel_id,
            display_name,
            history_text,
        )

        history_context = self.history.get_context(
            channel_id
        )

        # 長期記憶を取得
        long_term_notes = get_notes(user_id)

        # Geminiの応答を待っている間は入力中表示
        async with message.channel.typing():

            try:
                ai_message = message.content

                if pdf_context:
                    ai_message = (
                        f"{message.content}\n\n"
                        f"# 添付PDFの内容\n"
                        f"{pdf_context}"
                    ).strip()

                # 【修正】こちらも同様にasyncio.to_thread化。
                # テキストチャンネルのみの会話ではVC heartbeatへの影響は無いが、
                # VCに参加中のギルドで同時にテキストメッセージが来た場合に
                # 同じイベントループを塞がないよう、テキスト側も統一しておく。
                chat_intro, reply, emoji, is_note = await asyncio.to_thread(
                    ask_gemini,
                    ai_message,
                    history_context=history_context,
                    long_term_notes=long_term_notes,
                    images=images,
                )

                if len(reply) > 1900:
                    reply = reply[:1900] + "..."

            except Exception as e:
                logger.exception(
                    "Gemini呼び出しに失敗しました: %s",
                    e,
                )

                error_text = str(e)

                if (
                    "503" in error_text
                    or "overloaded" in error_text.lower()
                ):
                    reply = get_busy_message()

                elif (
                    "429" in error_text
                    or "quota" in error_text.lower()
                ):
                    reply = get_failed_message()

                else:
                    reply = get_unknown_message()

                await message.channel.send(reply)
                return

        # PDFの読み取りについて注意が必要な場合
        if pdf_warning:
            await message.channel.send(pdf_warning)

        # Asterの返答を短期記憶へ保存
        note_for_history = (
            f"{chat_intro} {reply}".strip()
            if chat_intro
            else reply
        )

        self.history.add(
            channel_id,
            "Aster",
            note_for_history,
        )

        # --------------------------------------------------
        # テキスト入力に対する返答
        # --------------------------------------------------

        if is_note:
            # ==============================
            # 💬 → 📝 ノートモード
            # ==============================

            await message.channel.send(
                chat_intro or get_note_wait_message()
            )

            try:
                async with message.channel.typing():
                    image_bytes = render_note(reply)

                sent_messages = [
                    await message.channel.send(
                        file=discord.File(
                            io.BytesIO(image_bytes),
                            filename="note.png",
                        )
                    )
                ]

            except Exception as e:
                logger.exception(
                    "ノート画像の生成に失敗しました: %s",
                    e,
                )

                # 画像生成に失敗した場合だけ通常テキスト
                sent_messages = await self.reply_manager.send(
                    message.channel,
                    reply,
                )

        else:
            # ==============================
            # 💬 → 💬 通常会話
            # ==============================

            sent_messages = await self.reply_manager.send(
                message.channel,
                reply,
            )

            # テキスト入力の場合、
            # AsterはVCで勝手に読み上げない。
            #
            # 音声入力の場合だけhandle_voice_text()から
            # _speak()を呼ぶ。
            pass

        # Guildにいる場合はアイドルタイマーを更新
        if message.guild is not None:
            voice_cog = self.bot.get_cog(
                "VoiceStateListener"
            )

            if voice_cog is not None:
                voice_cog.notify_activity(
                    message.guild
                )

        # リアクション
        if emoji and sent_messages:
            try:
                await sent_messages[-1].add_reaction(
                    emoji
                )
            except discord.HTTPException as e:
                logger.warning(
                    "リアクションの追加に失敗しました: %s",
                    e,
                )

        # 長期記憶抽出
        self._schedule_memory_extraction(
            user_id,
            display_name,
            channel_id,
        )

    async def _speak(
        self,
        guild: discord.Guild,
        text: str,
    ) -> None:
        """
        VOICEVOXで文章を音声化してVCで再生する。

        実際の音声合成は別スレッドで行い、
        Discordのイベントループを止めないようにする。
        """

        voice_client = guild.voice_client

        if voice_client is None:
            return

        try:
            wav_bytes = await asyncio.to_thread(
                synthesize,
                text,
            )

        except VoicevoxError as e:
            logger.warning(
                "音声合成に失敗しました(VC自体には影響なし): %s",
                e,
            )
            return

        try:
            # 現在の音声が終わるまで待つ
            while voice_client.is_playing():
                await asyncio.sleep(0.2)

            audio_source = discord.FFmpegPCMAudio(
                io.BytesIO(wav_bytes),
                pipe=True,
            )

            voice_client.play(audio_source)

        except discord.ClientException as e:
            logger.warning(
                "音声の再生に失敗しました: %s",
                e,
            )

    async def _extract_pdf(
        self,
        message: discord.Message,
    ) -> bytes | None:

        for attachment in message.attachments:

            content_type = (
                attachment.content_type or ""
            )

            is_pdf = (
                content_type == "application/pdf"
                or attachment.filename.lower().endswith(".pdf")
            )

            if not is_pdf:
                continue

            try:
                return await attachment.read()

            except discord.HTTPException as e:
                logger.warning(
                    "PDFの取得に失敗しました: %s",
                    e,
                )
                return None

        return None

    async def _extract_images(
        self,
        message: discord.Message,
    ) -> list[tuple[bytes, str]]:

        images: list[tuple[bytes, str]] = []

        for attachment in message.attachments:

            if len(images) >= MAX_IMAGES:
                break

            if (
                not attachment.content_type
                or not attachment.content_type.startswith("image/")
            ):
                continue

            try:
                data = await attachment.read()

                images.append(
                    (
                        data,
                        attachment.content_type,
                    )
                )

            except discord.HTTPException as e:
                logger.warning(
                    "画像の取得に失敗しました: %s",
                    e,
                )

        return images

    def _schedule_memory_extraction(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
    ) -> None:

        pending = self._pending_extraction.get(
            user_id
        )

        if pending and not pending.done():
            pending.cancel()

        task = asyncio.create_task(
            self._run_memory_extraction_after_delay(
                user_id,
                display_name,
                channel_id,
            )
        )

        self._pending_extraction[user_id] = task

    async def _run_memory_extraction_after_delay(
        self,
        user_id: int,
        display_name: str,
        channel_id: int,
    ) -> None:

        try:
            await asyncio.sleep(
                MEMORY_EXTRACTION_DELAY
            )

        except asyncio.CancelledError:
            return

        try:
            existing_notes = get_notes(user_id)

            recent_exchange = (
                self.history.get_context(channel_id)
            )

            updated_notes = extract_memory_update(
                existing_notes,
                recent_exchange,
            )

            save_notes(
                user_id,
                display_name,
                updated_notes,
            )

            logger.info(
                "長期記憶を更新しました: user_id=%s",
                user_id,
            )

        except Exception as e:
            logger.exception(
                "長期記憶の更新に失敗しました: %s",
                e,
            )


async def setup(bot):
    await bot.add_cog(
        MessageListener(bot)
    )