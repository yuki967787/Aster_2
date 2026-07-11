from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

PROMPT = Path("prompts/persona.txt").read_text(
    encoding="utf-8"
)


def ask_gemini(message: str) -> str:

    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=f"{PROMPT}\n\nユーザー:{message}"
    )

    return response.text