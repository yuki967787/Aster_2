import re

from google import genai
from google.genai import types

from aster.config import BASE_DIR, GEMINI_API_KEY, GEMINI_MODEL_LIGHT, GEMINI_MODEL_MAIN

# Geminiクライアント
client = genai.Client(api_key=GEMINI_API_KEY)

# 人格プロンプト
# BASE_DIR(リポジトリのルート)からの絶対パスで読み込むことで、
# どのディレクトリから起動しても persona.txt を見つけられるようにする
PROMPT = (BASE_DIR / "prompts" / "persona.txt").read_text(
    encoding="utf-8"
)

# 1メッセージあたりGeminiに渡す画像の上限枚数
MAX_IMAGES = 6

# 返答の最後に付けさせる絵文字タグ・ノートモードタグの形式
# 例: "ちょっと待ってね\n---NOTE---\n本文...\n[MODE: NOTE]\n[EMOJI: 🎉]"
# 抜き出した後は本文から取り除くので、Discordには表示されない
_EMOJI_TAG_PATTERN = re.compile(r"\[EMOJI:\s*(\S+)\]")
_MODE_NOTE_PATTERN = re.compile(r"\[MODE:\s*NOTE\]")
_NOTE_SPLIT_PATTERN = re.compile(r"-{3,}\s*NOTE\s*-{3,}")

# Geminiに出力フォーマットを指示する追加プロンプト
_RESPONSE_FORMAT_INSTRUCTION = """

# 出力フォーマットについて
- 数式を書く時は $E$ や \\frac{a}{b} のようなLaTeX記法を絶対に使わないでください。
  E = V / (2πr) のように、誰でもそのまま読めるプレーンな書き方をしてください。
- 数式は演算子(=, +, -, *, /など)の前後に必ずスペースを入れてください。
  「a=root((g*t))」ではなく「a = root(g * t)」のように書いてください
  (ノート画像で長い数式を折り返す時、スペースが無いと不自然な位置で
  切らざるを得なくなるためです)。
- 数式を使った説明や、手順を追った詳しい解説をする場合は、返答を次の2つに分けてください。
  1. チャットにそのまま送る短い一言(「ちょっと待ってて、整理するね」のような、キャラクターらしい一言)
  2. `---NOTE---` という区切り線
  3. ノート画像に書く実際の解説内容(数式や手順)
  例:
    んー、ちょっと待って。
    ---NOTE---
    E = V / (2πr) になる理由を整理すると...
  この形式にした場合は、返答の最後に `[MODE: NOTE]` というタグも付けてください
  (手書きノート画像として送るための目印です)。
  普通の雑談ではこの区切りやタグを付けず、いつも通り話してください。
- 返答の最後に、必要な場合だけ `[EMOJI: 絵文字]` の形で1つだけ絵文字を付けてください。
  普段は淡々としているキャラクターなので、よほど心が動いた瞬間(すごく嬉しい、驚いた、笑える等)
  以外は付けないでください。ほとんどの返答では付けなくて問題ありません。
  付けない場合は何も書かないでください(空のタグやダミーは不要です)。
"""


def _extract_tags(text: str) -> tuple[str, str, str | None, bool]:
    """
    Geminiの返答テキストから [EMOJI: X] と [MODE: NOTE] タグ、
    ---NOTE--- 区切りを取り除いて分解する。

    戻り値: (チャットに送る前置き, ノートに書く本文, 絵文字 or None, ノートモードかどうか)

    ノートモードでない場合は、チャット前置きは空文字、ノート本文に返答全体が入る
    (呼び出し側は is_note を見て、どちらを使うか判断する)。
    """

    is_note = bool(_MODE_NOTE_PATTERN.search(text))
    text = _MODE_NOTE_PATTERN.sub("", text)

    emoji_match = _EMOJI_TAG_PATTERN.search(text)
    emoji = emoji_match.group(1) if emoji_match else None
    text = _EMOJI_TAG_PATTERN.sub("", text)

    text = text.strip()

    split_match = _NOTE_SPLIT_PATTERN.search(text)
    if is_note and split_match:
        chat_intro = text[: split_match.start()].strip()
        note_body = text[split_match.end() :].strip()
    else:
        chat_intro = ""
        note_body = text

    return chat_intro, note_body, emoji, is_note


def ask_gemini(
    message: str,
    history_context: str = "",
    long_term_notes: str = "",
    images: list[tuple[bytes, str]] | None = None,
) -> tuple[str, str, str | None, bool]:
    """
    Geminiへメッセージを送り、返答を取得する。

    history_context: memory.ConversationHistory.get_context() で得た
        「直近の会話」の文字列(短期記憶)。
    long_term_notes: db.get_notes() で得た、このユーザーについて
        覚えている内容(長期記憶)。
    images: [(画像バイト列, mime_type), ...] のリスト。多くてもMAX_IMAGES枚まで使う
        (それ以上は呼び出し側で絞り込んでいても、念のためここでも切り詰める)。
    どれも無ければ、その項目は無いものとして扱う。

    戻り値: (チャット前置き, ノート本文(通常会話ならこちらに全文が入る),
             リアクション絵文字 or None, ノートモードかどうか)
    """

    sections = [PROMPT + _RESPONSE_FORMAT_INSTRUCTION]

    if long_term_notes:
        sections.append(f"# このユーザーについて覚えていること\n{long_term_notes}")

    if history_context:
        sections.append(f"# これまでの会話\n{history_context}")

    sections.append(f"ユーザー: {message}")

    # テキスト部分をひとまとめにし、画像パートを後ろに続ける
    # (google-genai SDKはcontentsにテキストと画像パートを混在させたリストを渡せる)
    contents: list = ["\n\n".join(sections)]

    for data, mime_type in (images or [])[:MAX_IMAGES]:
        contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))

    response = client.models.generate_content(
        model=GEMINI_MODEL_MAIN,
        contents=contents,
    )

    return _extract_tags(response.text.strip())


IMAGE_DESCRIPTION_PROMPT = """\
これらの画像に何が写っているか、次の会話でも参照できるように
日本語で120字程度の客観的な説明文にまとめてください。
キャラクターとして振る舞わず、事実の説明だけを簡潔に書いてください。
"""


def describe_image(images: list[tuple[bytes, str]]) -> str:
    """
    画像の内容を短い説明文(120字程度)にして返す。

    短期記憶(会話履歴)には画像そのものではなくこのテキストだけを残すことで、
    データ量を抑えつつ、後の会話でも「何が写っていたか」を参照できるようにする。
    """

    contents: list = [IMAGE_DESCRIPTION_PROMPT]

    for data, mime_type in images[:MAX_IMAGES]:
        contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))

    response = client.models.generate_content(
        model=GEMINI_MODEL_MAIN,
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
        model=GEMINI_MODEL_LIGHT,
        contents=contents,
    )

    return response.text.strip()