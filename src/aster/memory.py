"""
memory.py
---------
Asterの「短期記憶」を管理するモジュール。

ここでの短期記憶は、Bot起動中だけ有効なチャンネルごとの会話履歴を指す。
再起動すると消える(揮発性)。永続化する「長期記憶」は今後別途design予定。

なぜチャンネル単位か:
    直近20件を「同じチャンネルの会話をみんな分まとめて」覚える方針にしたため、
    ユーザーごとに分けたい場合は _channels のキーを (channel_id, user_id) にすればよい。
"""

from __future__ import annotations

from collections import deque


class ConversationHistory:
    """チャンネルごとに直近のやり取りを保持するクラス。"""

    # 1チャンネルあたり何件まで覚えておくか
    MAX_HISTORY = 20

    def __init__(self) -> None:
        # channel_id -> 発言のdeque
        # dequeにmaxlenを指定しておくと、上限を超えた古い発言は
        # 自前でpopしなくても自動的に消えてくれる
        self._channels: dict[int, deque[tuple[str, str]]] = {}

    def add(self, channel_id: int, author_name: str, content: str) -> None:
        """このチャンネルの履歴に1件追加する。"""

        if channel_id not in self._channels:
            self._channels[channel_id] = deque(maxlen=self.MAX_HISTORY)

        self._channels[channel_id].append((author_name, content))

    def get_context(self, channel_id: int) -> str:
        """
        Geminiに渡すための「これまでの会話」を文字列に整形して返す。

        履歴が無いチャンネルの場合は空文字を返す。
        """

        history = self._channels.get(channel_id)

        if not history:
            return ""

        lines = [f"{name}: {text}" for name, text in history]

        return "\n".join(lines)