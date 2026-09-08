from pathlib import Path
from dotenv import load_dotenv
import os

# プロジェクトルート
BASE_DIR = Path(__file__).resolve().parents[2]

# .env を読み込む
load_dotenv(BASE_DIR / ".env")

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 通常会話・画像認識用(精度重視。画像の読み取り精度を落としたくないため
# describe_imageもこちらを使う)
# 2026年7月時点: gemini-2.5-flashは新規利用不可、gemini-flash-latest(=3.5 Flash)は
# 前日の使用で上限に近いため、最新のGA版である3.6 Flashを指定
GEMINI_MODEL_MAIN = os.getenv("GEMINI_MODEL_MAIN", "gemini-3.6-flash")

# 長期記憶の抽出用(テキストの要約だけなので、精度への影響が小さい軽量モデルでよい)
GEMINI_MODEL_LIGHT = os.getenv("GEMINI_MODEL_LIGHT", "gemini-3.5-flash-lite")

# Bot設定
BOT_NAME = "Aster"

# VOICEVOX(音声合成エンジン)
# エンジン自体は別アプリとして起動しておく必要がある(公式サイトからダウンロード)
# デフォルトのURLはVOICEVOXアプリ起動時にlocalhostで立つAPIのもの
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")

# 話者ID。ナースロボ＿タイプT(ノーマル)を既定値にしているが、
# VOICEVOXのバージョンによってIDがずれることがあるため、
# 実際に使う前に起動中のエンジンの /speakers エンドポイントで確認すること
VOICEVOX_SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", "47"))

# VC参加までのランダムな間(ユーザーがVCに入ってから、少し遅れてAsterが入る演出)
VOICE_JOIN_DELAY_MIN = 3.0
VOICE_JOIN_DELAY_MAX = 7.0

# ユーザーがVCから抜けてから、Asterも退出するまでの猶予(誤って抜けた場合等を考慮)
VOICE_USER_LEFT_GRACE_SECONDS = 120  # 2分

# テキストでの会話が止まってからAsterがVC退出するまでの時間(ランダム幅)
VOICE_IDLE_TIMEOUT_MIN = 180  # 3分
VOICE_IDLE_TIMEOUT_MAX = 300  # 5分

# 読み込むCog
COGS = [
    "aster.cogs.ping",
    "aster.cogs.help",
    # AI
    "aster.listeners.message",
    # Voice
    "aster.listeners.voice_state",
    # Voice Recieve
    "aster.listeners.voice_receive",
]