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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Bot設定
BOT_NAME = "Aster"

# 読み込むCog
COGS = [
    "aster.cogs.ping",
    "aster.cogs.help",
    # AI
    "aster.listeners.message",
]