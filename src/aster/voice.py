"""
voice.py
--------
VOICEVOXエンジン(別アプリとして起動しておく音声合成サーバー)と通信するモジュール。

VOICEVOX自体はPythonのライブラリではなく、HTTPサーバーとして動くエンジン。
事前に公式サイトからダウンロードして起動しておく必要がある
(デフォルトで http://127.0.0.1:50021 にAPIが立つ)。

このファイルの役割は「テキストを渡したら、喋らせられる音声(wav)を返す」ことだけ。
Discordの音声再生の仕組み(VCに繋ぐ・再生する)はlistenersの側で扱う。
"""

from __future__ import annotations

import logging

import requests

from aster.config import VOICEVOX_SPEAKER_ID, VOICEVOX_URL

logger = logging.getLogger("aster.voice")


class VoicevoxError(Exception):
    """VOICEVOXエンジンとの通信で問題が起きた時の例外。"""


def synthesize(text: str, speaker_id: int = VOICEVOX_SPEAKER_ID) -> bytes:
    """
    テキストを読み上げた音声(wav形式のバイト列)を返す。

    VOICEVOXは2段階のAPIになっている:
    1. /audio_query でテキストから「読み方・イントネーション等の設計図」を作る
    2. /synthesis でその設計図から実際の音声(wav)を合成する
    分けられているのは、ユーザーが読み方を修正してから合成する、という
    VOICEVOX本来のGUI操作を想定した設計のため。Asterでは1と2を続けて呼ぶだけでよい。
    """

    try:
        query_response = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker_id},
            timeout=10,
        )
        query_response.raise_for_status()
        audio_query = query_response.json()

        synthesis_response = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker_id},
            json=audio_query,
            timeout=30,
        )
        synthesis_response.raise_for_status()

        return synthesis_response.content

    except requests.exceptions.ConnectionError as e:
        # VOICEVOXエンジンが起動していない時に一番起きやすいエラー
        raise VoicevoxError(
            "VOICEVOXエンジンに接続できませんでした。エンジンが起動しているか確認してください。"
        ) from e
    except requests.exceptions.RequestException as e:
        raise VoicevoxError(f"VOICEVOXとの通信に失敗しました: {e}") from e


def list_speakers() -> list[dict]:
    """
    現在利用可能な話者一覧を返す(speaker_idの確認用のデバッグ関数)。
    VOICEVOXのバージョンが上がるとIDがずれることがあるため、
    実際に使いたい話者のIDが分からない時はこの関数の結果を確認する。
    """

    response = requests.get(f"{VOICEVOX_URL}/speakers", timeout=10)
    response.raise_for_status()
    return response.json()