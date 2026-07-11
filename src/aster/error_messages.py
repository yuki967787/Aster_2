"""
Asterがエラー時に返すメッセージを管理するモジュール。

ここにあるメッセージはランダムで選ばれるため、
毎回同じ返答になりにくくなります。
"""

from random import choice


# Gemini APIが混雑しているとき（503）
BUSY_MESSAGES = [
    "ごめ、ちょっとまってて",
    "あっ、ごめん！ちょっと待ってて！",
    "んん…今ちょっと返せないかも",
    "ごめん、ちょっとバタバタしてる…！",
    "あわわ…ちょっと今混み合ってるみたい💦",
    "ごめんね！もう一回おねがい",
]


# リトライしても失敗したとき
FAILED_MESSAGES = [
    "ちょっと調子わるいかも",
    "ごめんね…うまく返せなかった",
    "ちょっとダメだったかも",
    "ごめん、ちょっと休むね、またあとで",
]


# 想定外のエラー
UNKNOWN_MESSAGES = [
    "あれ…？なんかバグった気がする",
    "んー、今変な感じだった",
    "えっ、なんか変なことになってるかも",
]


def get_busy_message() -> str:
    """503エラー時のメッセージを返す。"""
    return choice(BUSY_MESSAGES)


def get_failed_message() -> str:
    """リトライ後も失敗したときのメッセージを返す。"""
    return choice(FAILED_MESSAGES)


def get_unknown_message() -> str:
    """その他のエラー時のメッセージを返す。"""
    return choice(UNKNOWN_MESSAGES)