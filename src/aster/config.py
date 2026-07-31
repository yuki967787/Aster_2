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

# 読み込むCog
COGS = [
    "aster.cogs.ping",
    "aster.cogs.help",
    # AI
    "aster.listeners.message",
]