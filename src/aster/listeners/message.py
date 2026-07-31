import asyncio
import io

import discord
from discord.ext import commands

from aster.ai import MAX_IMAGES, ask_gemini, describe_image, extract_memory_update
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

# 何秒発言が無かったら「会話が一区切りついた」とみなし、
# 長期記憶の自動抽出を実行するか
MEMORY_EXTRACTION_DELAY = 300  # 5分


class MessageListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # このCogが生きている間(=Bot起動中)だけ保持される短期記憶
        self.history = ConversationHistory()
        # タイピング演出・分割送信を担当
        self.reply_manager = ReplyManager()
        # channel_id -> 「一区切りついたら抽出する」ための保留タスク
        self._pending_extraction: dict[int, asyncio.Task] = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        # 自分自身のメッセージだけ無視
        if message.author == self.bot.user:
            return

        channel_id = message.channel.id
        user_id = message.author.id
        display_name = message.author.display_name

        # 添付画像を取り出す(最大MAX_IMAGES枚。それ以外の添付は今回は無視)
        images = await self._extract_images(message)

        # 短期記憶用のテキストを組み立てる
        # 画像がある場合は、Geminiに内容を説明させたテキストを残す
        # (画像そのものは記憶に残さないので、これが無いと後の会話で内容を思い出せなくなる)
        history_text = message.content

        if images:
            try:
                caption = describe_image(images)
                history_text = f"{history_text} [添付画像: {caption}]".strip()
            except Exception as e:
                # 説明の生成に失敗しても会話自体は止めず、簡易な目印だけ残す
                logger.exception(f"画像の説明生成に失敗しました: {e}")
                history_text = f"{history_text} [画像を{len(images)}枚送信]".strip()

        # 今回のユーザー発言を短期記憶に記録
        self.history.add(channel_id, display_name, history_text)
        history_context = self.history.get_context(channel_id)

        # 長期記憶(このユーザーについて覚えていること)を読み込む
        long_term_notes = get_notes(user_id)

        # 入力中表示(Geminiの応答を待っている間)
        async with message.channel.typing():

            try:
                reply, emoji, is_note = ask_gemini(
                    message.content,
                    history_context=history_context,
                    long_term_notes=long_term_notes,
                    images=images,
                )

                if len(reply) > 1900:
                    reply = reply[:1900] + "..."

            except Exception as e:
                # 詳細はログにのみ残し、Discordにはキャラクターに合った一言だけ返す
                logger.exception(f"Gemini呼び出しに失敗しました: {e}")

                error_text = str(e)
                if "503" in error_text or "overloaded" in error_text.lower():
                    reply = get_busy_message()
                elif "429" in error_text or "quota" in error_text.lower():
                    reply = get_failed_message()
                else:
                    reply = get_unknown_message()

                await message.channel.send(reply)
                return

        # Aster自身の発言も短期記憶に残す(自分の発言と矛盾しないため)
        self.history.add(channel_id, "Aster", reply)

        if is_note:
            # 詳しい解説・数式は手書きノート画像にして送る
            # (画像生成には少し時間がかかるので、先に一言挟んでから送る)
            await message.channel.send(get_note_wait_message())

            try:
                async with message.channel.typing():
                    image_bytes = render_note(reply)

                await message.channel.send(
                    file=discord.File(io.BytesIO(image_bytes), filename="note.png")
                )
                sent_messages = []
            except Exception as e:
                # 画像化に失敗しても、テキストとしては伝わるようにフォールバックする
                logger.exception(f"ノート画像の生成に失敗しました: {e}")
                sent_messages = await self.reply_manager.send(message.channel, reply)
        else:
            # 通常の会話はReplyManagerに送信を任せる
            # (typing演出・分割送信・送信間隔はReplyManager自身が担当するため、
            #  ここで重ねてtypingを出す必要は無い)
            sent_messages = await self.reply_manager.send(message.channel, reply)

        # 絵文字が指定されていれば、最後に送ったメッセージにリアクションを付ける
        # (普段は淡々としているキャラなので、Geminiが「よほど心が動いた時」だけ
        #  絵文字を返す想定 → ほとんどの場合はNoneで何も付かない)
        if emoji and sent_messages:
            try:
                await sent_messages[-1].add_reaction(emoji)
            except discord.HTTPException as e:
                # 絵文字が無効(Discordが認識できない文字列)等で失敗しても
                # 会話自体は成立しているので、ログだけ残して続行する
                logger.warning(f"リアクションの追加に失敗しました: {e}")

        # 会話が一区切りついたら長期記憶を更新するようスケジュールする
        self._schedule_memory_extraction(user_id, display_name, channel_id)

    async def _extract_images(
        self, message: discord.Message
    ) -> list[tuple[bytes, str]]:
        """
        メッセージの添付ファイルから画像だけを取り出し、
        [(バイト列, mime_type), ...] のリストにして返す。
        最大 aster.ai.MAX_IMAGES 枚まで(超えた分は無視する)。
        """

        images: list[tuple[bytes, str]] = []

        for attachment in message.attachments:
            if len(images) >= MAX_IMAGES:
                break

            if not attachment.content_type or not attachment.content_type.startswith(
                "image/"
            ):
                continue

            try:
                data = await attachment.read()
                images.append((data, attachment.content_type))
            except discord.HTTPException as e:
                logger.warning(f"画像の取得に失敗しました: {e}")

        return images

    def _schedule_memory_extraction(
        self, user_id: int, display_name: str, channel_id: int
    ) -> None:
        """
        「発言が MEMORY_EXTRACTION_DELAY 秒止まったら長期記憶を更新する」
        タイマーをセットする(デバウンス)。

        会話が続いている間は、発言のたびに前回のタイマーをキャンセルして
        セットし直すので、実際に抽出が走るのは「会話が止まった時」の1回だけになる。
        """

        # 前回セットした分がまだ残っていればキャンセル
        pending = self._pending_extraction.get(user_id)
        if pending and not pending.done():
            pending.cancel()

        task = asyncio.create_task(
            self._run_memory_extraction_after_delay(
                user_id, display_name, channel_id
            )
        )
        self._pending_extraction[user_id] = task

    async def _run_memory_extraction_after_delay(
        self, user_id: int, display_name: str, channel_id: int
    ) -> None:
        try:
            await asyncio.sleep(MEMORY_EXTRACTION_DELAY)
        except asyncio.CancelledError:
            # 会話が続いて新しいタイマーに置き換わっただけなので、何もしない
            return

        try:
            existing_notes = get_notes(user_id)
            recent_exchange = self.history.get_context(channel_id)

            updated_notes = extract_memory_update(existing_notes, recent_exchange)

            save_notes(user_id, display_name, updated_notes)
            logger.info(f"長期記憶を更新しました: user_id={user_id}")

        except Exception as e:
            # 長期記憶の更新に失敗しても、会話自体には影響させない
            logger.exception(f"長期記憶の更新に失敗しました: {e}")


async def setup(bot):
    await bot.add_cog(MessageListener(bot))