from pathlib import Path
from dotenv import load_dotenv
import os

# プロジェクトルート
BASE_DIR = Path(__file__).resolve().parents[2]

# .env を読み込む
load_dotenv(BASE_DIR / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

BOT_NAME = "Aster"

COGS = [
    "aster.cogs.ping",
    "aster.cogs.help",
]