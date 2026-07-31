"""
note_messages.py
----------------
手書きノート画像を送る前に、一言だけ挟むための短いセリフ集。

画像の生成にはGemini呼び出し+描画の時間がかかるので、
無言でいきなり画像が来るより「ちょっと待って」の一言があった方が
不自然に間が空いた印象を与えにくい。error_messages.py と同じ発想の仕組み。
"""

import random

_NOTE_WAIT_MESSAGES = [
    "…ちょっと待って、整理するから",
    "んー、ちょっと待ってて",
    "…書くから少し待ってて",
    "ちょっとまとめるから待ってて",
]


def get_note_wait_message() -> str:
    return random.choice(_NOTE_WAIT_MESSAGES)