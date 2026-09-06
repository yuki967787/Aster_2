"""
formatter.py
------------
Geminiの返答テキストを、手書きノート画像として描画しやすい形に整形するモジュール。

役割はここまで:
- LaTeX記法の除去(念のための保険。基本はGemini自身に使わせない指示をしている)
- Markdown記法(**太字**, `コード`など)の除去
- 数式(分数・単純な数式)を検出して、専用の構造に変換
- それ以外の行は「プレーンな文字列の行」として渡す(折り返しはしない)

【重要】このファイルは「文字の折り返し」をしない。
以前は textwrap.wrap() で文字数ベースの折り返しをしていたが、
フォントや紙の幅を一切見ていないため「電場は「斜/面」」のような
不自然な位置で切れる問題があった。
折り返しは実際の描画幅を知っている handwriting.py 側の責務にした
(draw.textbbox() で実際のピクセル幅を測りながら折り返す)。
formatter.pyは「何を描くか」を決めるだけで、Pillowには一切触れない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# LaTeXでよく使われる記号の簡易除去(Gemini側に使わせない指示はしているが、念のための保険)
_LATEX_PATTERNS = [
    (re.compile(r"\$\$?(.+?)\$\$?"), r"\1"),  # $x$ や $$x$$ の$を剥がす
    (re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}"), r"\1/\2"),  # \frac{a}{b} → a/b
    (re.compile(r"\\[a-zA-Z]+"), ""),  # \Phi, \pi などの残りのLaTeXコマンド
    (re.compile(r"[{}]"), ""),  # 残った波括弧
]

# Markdownの装飾記法の簡易除去
_MARKDOWN_PATTERNS = [
    (re.compile(r"\*\*(.+?)\*\*"), r"\1"),  # **太字**
    (re.compile(r"`(.+?)`"), r"\1"),  # `コード`
]

# シンプルな分数 "A/B" を検出する(A, Bは英数字・ギリシャ文字・記号少々を想定)
_FRACTION_PATTERN = re.compile(
    r"([A-Za-zΑ-ωπΦφΔθ0-9\.\+\-\*]+)/([A-Za-zΑ-ωπΦφΔθ0-9\.\+\-\*\(\)]+)"
)

# 式(=を含む行)かどうかの簡易判定。日本語の通常文には"="はまず出てこないため、
# "="の有無を「これは数式行だ」の目印として使う。
_HAS_EQUALS = re.compile(r"=")


@dataclass
class TextLine:
    """普通のテキスト行。折り返しはhandwriting.py側で行う。"""

    text: str


@dataclass
class FormulaLine:
    """
    数式として「絶対に途中で改行しない」行。
    (分数として縦組みするほど単純ではないが、数式なので変な位置で
    折り返されると読めなくなるもの。例: "E = kQ/r + mv²" のような複合式)
    """

    text: str


@dataclass
class FractionLine:
    """分数として描画してほしい行(分子・分母を分けて持つ)。"""

    numerator: str
    denominator: str
    prefix: str = ""  # 分数の前に付く部分("E = " など)
    suffix: str = ""  # 分数の後に続く部分("÷ 2πr" など、あれば)


Block = TextLine | FormulaLine | FractionLine


def _strip_latex(text: str) -> str:
    for pattern, replacement in _LATEX_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# 分数のprefix/suffixとして許容する最大文字数。
# これを超える場合は「短い前置き」の範囲を逸脱しているとみなし、
# 分数化を諦めて通常のFormulaLine/TextLineとして扱う。
# (番号付き説明文と数式が混ざった長い行を無理に分数化すると、
#  はみ出したprefix/suffixが紙の右端で切れてしまうため)
_MAX_AFFIX_LENGTH = 12


def _try_parse_fraction(line: str) -> FractionLine | None:
    """
    "E = V/(2πr)" のような、単純な分数を含む行を検出する。
    分数の前後にテキストが残っていれば prefix / suffix として保持するが、
    それが長すぎる場合は分数化しない(呼び出し側でFormulaLine等として扱われる)。
    複数の分数が混在する複雑な式は対象外(そのままFormulaLineとして扱われる)。
    """

    match = _FRACTION_PATTERN.search(line)

    if not match:
        return None

    # 行の中に分数のパターンが複数ある場合は、単純な分数としては扱わない
    # (無理に1つだけ抜き出すと誤変換のリスクが上がるため)
    if _FRACTION_PATTERN.search(line[match.end() :]):
        return None

    numerator = match.group(1).strip("()")
    denominator = match.group(2).strip("()")

    if not numerator or not denominator:
        return None

    prefix = line[: match.start()].strip()
    suffix = line[match.end() :].strip()

    if len(prefix) > _MAX_AFFIX_LENGTH or len(suffix) > _MAX_AFFIX_LENGTH:
        return None

    return FractionLine(
        numerator=numerator, denominator=denominator, prefix=prefix, suffix=suffix
    )


def format_for_note(text: str) -> list[Block]:
    """
    Geminiの返答テキストを、handwriting.pyが描画しやすい Block のリストに変換する。
    折り返しはしない(handwriting.py側の責務)。
    """

    text = _strip_latex(text)
    text = _strip_markdown(text)

    blocks: list[Block] = []

    for paragraph in text.splitlines():
        stripped = paragraph.strip()

        if not stripped:
            blocks.append(TextLine(text=""))
            continue

        fraction = _try_parse_fraction(stripped)
        if fraction:
            blocks.append(fraction)
            continue

        if _HAS_EQUALS.search(stripped):
            # 分数化できなかった数式行(複合式など)は、折り返さない専用ブロックにする
            blocks.append(FormulaLine(text=stripped))
            continue

        blocks.append(TextLine(text=stripped))

    return blocks