from google import genai

from aster.config import BASE_DIR, GEMINI_API_KEY, GEMINI_MODEL

# Geminiクライアント
client = genai.Client(api_key=GEMINI_API_KEY)

# 人格プロンプト
# BASE_DIR(リポジトリのルート)からの絶対パスで読み込むことで、
# どのディレクトリから起動しても persona.txt を見つけられるようにする
PROMPT = (BASE_DIR / "prompts" / "persona.txt").read_text(
    encoding="utf-8"
)


def ask_gemini(
    message: str,
    history_context: str = "",
    long_term_notes: str = "",
) -> str:
    """
    Geminiへメッセージを送り、返答を取得する。

    history_context: memory.ConversationHistory.get_context() で得た
        「直近の会話」の文字列(短期記憶)。
    long_term_notes: db.get_notes() で得た、このユーザーについて
        覚えている内容(長期記憶)。
    どちらも空文字なら、その項目は無いものとして扱う。
    """

    sections = [PROMPT]

    if long_term_notes:
        sections.append(f"# このユーザーについて覚えていること\n{long_term_notes}")

    if history_context:
        sections.append(f"# これまでの会話\n{history_context}")

    sections.append(f"ユーザー: {message}")

    contents = "\n\n".join(sections)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )

    return response.text.strip()


MEMORY_EXTRACTION_PROMPT = """\
あなたはAsterの「長期記憶」を整理する係です。キャラクターとして返答しないでください。
以下の「これまでの記憶」と「直近の会話」を読み、今後も覚えておくべき情報だけを
日本語の箇条書きで300字程度にまとめて出力してください。

ルール:
- 名前、好み、関係性、継続している話題など、次の会話でも役立つ情報だけ残す
- その場限りの雑談内容(挨拶、天気の話など)は含めない
- 「これまでの記憶」に既にある内容と重複させず、統合・整理する
- 新しく覚えるべき情報が無ければ、「これまでの記憶」をそのまま出力する
- 説明や前置きは書かず、箇条書きの本文だけを出力する
"""


def extract_memory_update(existing_notes: str, recent_exchange: str) -> str:
    """
    既存の長期記憶(existing_notes)と直近の会話(recent_exchange)を渡し、
    更新後の長期記憶(notes全文)をGeminiに書かせて返す。

    通常の会話用ask_gemini()とは別の、記憶整理専用の呼び出し。
    """

    contents = (
        f"{MEMORY_EXTRACTION_PROMPT}\n\n"
        f"# これまでの記憶\n{existing_notes or '(まだ無し)'}\n\n"
        f"# 直近の会話\n{recent_exchange}"
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )

    return response.text.strip()