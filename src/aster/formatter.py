"""
formatter.py
------------
Geminiの返答テキストを、手書きノート画像として描画しやすい形に整形するモジュール。

役割はここまで:
- LaTeX記法の除去(念のための保険。基本はGemini自身に使わせない指示をしている)
- Markdown記法(**太字**, `コード`など)の除去
- 簡単な分数(A/B の形)を検出して、分数として描画できる構造に変換
- それ以外の行は「プレーンな文字列の行」として渡す

描画そのもの(フォント選択・紙の背景・実際の画像化)は handwriting.py の役割。
このファイルは「どう描くか」を決めるだけで、Pillowには一切触れない。
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass

# 1行あたりのだいたいの最大文字数(日本語想定)
WRAP_WIDTH = 22

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
_FRACTION_PATTERN = re.compile(r"([A-Za-zΑ-ωπΦφΔθ0-9\.\+\-\*]+)/([A-Za-zΑ-ωπΦφΔθ0-9\.\+\-\*\(\)]+)")


@dataclass
class TextLine:
    """普通のテキスト行。"""

    text: str


@dataclass
class FractionLine:
    """分数として描画してほしい行(分子・分母を分けて持つ)。"""

    numerator: str
    denominator: str
    prefix: str = ""  # 分数の前に付く部分("E = " など)


Block = TextLine | FractionLine


def _strip_latex(text: str) -> str:
    for pattern, replacement in _LATEX_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _strip_markdown(text: str) -> str:
    for pattern, replacement in _MARKDOWN_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _try_parse_fraction(line: str) -> FractionLine | None:
    """
    "E = V/(2πr)" のような、末尾が単純な分数になっている行を検出する。
    複数の分数が混在する複雑な式や、累乗・添字が入る式は対象外(そのまま通常行として扱う)。
    """

    match = _FRACTION_PATTERN.search(line)

    if not match:
        return None

    # 行の中に分数が1つだけ、かつそれが行の後半にあるようなケースに限定する
    # (複雑な式まで無理に分数化しようとすると誤変換のリスクが上がるため)
    numerator = match.group(1).strip("()")
    denominator = match.group(2).strip("()")

    if not numerator or not denominator:
        return None

    prefix = line[: match.start()].strip()

    return FractionLine(numerator=numerator, denominator=denominator, prefix=prefix)


def format_for_note(text: str) -> list[Block]:
    """
    Geminiの返答テキストを、handwriting.pyが描画しやすい Block のリストに変換する。
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

        # 折り返しが必要な長い行は複数のTextLineに分ける
        for wrapped in textwrap.wrap(stripped, width=WRAP_WIDTH) or [stripped]:
            blocks.append(TextLine(text=wrapped))

    return blocks