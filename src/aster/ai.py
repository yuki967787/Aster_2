from pathlib import Path

from google import genai

from aster.config import GEMINI_API_KEY, GEMINI_MODEL

# Geminiクライアント
client = genai.Client(api_key=GEMINI_API_KEY)

# 人格プロンプト
PROMPT = Path("prompts/persona.txt").read_text(
    encoding="utf-8"
)


def ask_gemini(message: str) -> str:
    """Geminiへメッセージを送り、返答を取得する"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"{PROMPT}\n\nユーザー: {message}"
    )

    return response.text.strip()