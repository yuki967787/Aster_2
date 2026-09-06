"""
handwriting.py
--------------
formatter.pyが整形したBlockのリストを受け取り、「手書きノート風の画像」にして返す。

Discordは通常のチャットでLaTeX($E$ みたいな数式記法)を描画してくれないため、
数式や詳しい解説は、紙の上に手書き文字で書いたような画像にして送ることで読みやすくする。

【重要】折り返しはここで行う。
formatter.pyは文字数を見ず、テキストの意味的な整形(数式の分離など)だけを担当する。
実際に「何文字で折り返すか」は、フォントサイズ・紙の幅によって変わるため、
draw.textbbox() で実際の描画幅を測りながらここで折り返す。
こうしておくと、将来フォントサイズや画像サイズを変えてもレイアウトが自動で最適化される。

フォントについて:
- 本命は「ぴょすふぉんと」(BOOTH配布、無料・商用可・ただし二次配布禁止)。
  ライセンス上Gitにはコミットできないため、手元で
  src/aster/assets/fonts/pyos.otf に配置してもらう想定(.gitignore対象)。
- 上記が無い環境では、同梱している Yomogi(Google Fonts, OFLライセンス、再配布可)に
  自動でフォールバックする。
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from aster.formatter import Block, FormulaLine, FractionLine, TextLine, format_for_note

# 画像サイズ・余白・フォントサイズ等の定数
IMAGE_WIDTH = 800
MARGIN_TOP = 60
MARGIN_BOTTOM = 60
MARGIN_LEFT = 90  # 赤い縦線の右側から文字を書き始めるための余白
MARGIN_RIGHT = 50
MAX_WIDTH = IMAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT  # 実際に文字を置ける横幅
LINE_HEIGHT = 46
FONT_SIZE = 30
FRACTION_FONT_SIZE = 26

# 折り返し時に優先的に改行してよい文字(句読点・閉じ括弧・スペースの直後)
_BREAK_CHARS = "、。)]）】」』 "

# --- フォントパス解決処理 ---
_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"

_PREFERRED_FONT_CANDIDATES = [
    "pyos.otf",
    "pyos.ttf",
    "PyosuFontFree.otf",
    "PyosuFontFree .otf",
    "PyosuFontFree.ttf",
]
_FALLBACK_FONT = "Yomogi-Regular.ttf"


def _resolve_font_path() -> Path:
    for name in _PREFERRED_FONT_CANDIDATES:
        candidate = _FONT_DIR / name
        if candidate.exists():
            return candidate

    fallback = _FONT_DIR / _FALLBACK_FONT
    if fallback.exists():
        return fallback

    font_files = list(_FONT_DIR.glob("*.otf")) + list(_FONT_DIR.glob("*.ttf"))
    if font_files:
        return font_files[0]

    raise FileNotFoundError(
        f"フォントファイルが見つかりません。'{_FONT_DIR}' 内を確認してください。"
    )


_font_path = _resolve_font_path()
_font = ImageFont.truetype(str(_font_path), FONT_SIZE)
_fraction_font = ImageFont.truetype(str(_font_path), FRACTION_FONT_SIZE)
_signature_font = ImageFont.truetype(str(_font_path), 22)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    return draw.textbbox((0, 0), text, font=font)[2]


def _wrap_by_pixel_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    """
    実際の描画幅(textbbox)を測りながら、max_widthを超えないように1文字ずつ足していく。
    句読点・閉じ括弧・スペースの直後(_BREAK_CHARS)を優先的な改行ポイントにすることで、
    「電場は「斜/面」」のような不自然な位置で切れるのを避ける。
    """

    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    last_break_index = -1  # current内の「ここで区切ってよい」最後の位置

    for ch in text:
        test = current + ch

        if _text_width(draw, test, font) <= max_width:
            current = test
            if ch in _BREAK_CHARS:
                last_break_index = len(current)
            continue

        # 幅を超えた場合: 直前に良い区切り位置があればそこで折り返す
        if last_break_index > 0:
            lines.append(current[:last_break_index])
            current = current[last_break_index:] + ch
        else:
            # 区切り位置が無ければ、その場で強制的に折り返す
            lines.append(current)
            current = ch
        last_break_index = -1

    if current:
        lines.append(current)

    return lines


@dataclass
class _DrawItem:
    kind: str  # "text" | "formula" | "fraction"
    payload: object
    height: int


def _build_draw_items(draw: ImageDraw.ImageDraw, blocks: list[Block]) -> list[_DrawItem]:
    """
    Blockのリストを、実際の描画幅で折り返し済みの _DrawItem リストに変換する。
    ここで初めて「何行になるか」が確定するので、事前に高さの合計も分かるようになる。
    """

    items: list[_DrawItem] = []

    for block in blocks:
        if isinstance(block, FractionLine):
            items.append(
                _DrawItem(kind="fraction", payload=block, height=FRACTION_FONT_SIZE * 2 + 24)
            )
        elif isinstance(block, FormulaLine):
            # 数式もスペース区切りで折り返す(記号の途中では絶対に切らない)。
            # _wrap_by_pixel_width は " " も優先改行ポイントに含めているため、
            # 単語(トークン)の途中で改行されることはない
            wrapped = _wrap_by_pixel_width(draw, block.text, _font, MAX_WIDTH)
            for line in wrapped:
                items.append(_DrawItem(kind="formula", payload=line, height=LINE_HEIGHT))
        else:
            wrapped = _wrap_by_pixel_width(draw, block.text, _font, MAX_WIDTH)
            for line in wrapped:
                items.append(_DrawItem(kind="text", payload=line, height=LINE_HEIGHT))

    return items


def _make_paper_background(width: int, height: int) -> Image.Image:
    """
    B5ルーズリーフ風の紙背景を作る。
    - わずかに色味のあるオフホワイト
    - 少し青みのある横罫線
    - 左側の赤い縦線(ルーズリーフの定番)
    - 気づく程度の紙の影(周囲をわずかに暗くする)
    """

    base_color = random.choice([(255, 253, 248), (253, 251, 245), (255, 255, 252)])
    img = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(img)

    rule_color = (185, 205, 232)
    y = MARGIN_TOP
    while y < height - MARGIN_BOTTOM // 2:
        draw.line([(30, y), (width - 20, y)], fill=rule_color, width=1)
        y += LINE_HEIGHT

    red_line_x = MARGIN_LEFT - 25
    draw.line(
        [(red_line_x, 10), (red_line_x, height - 10)],
        fill=(215, 110, 110),
        width=2,
    )

    shadow = Image.new("L", (width, height), 0)
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rectangle([0, 0, width, height], fill=0)
    border = 18
    shadow_draw.rectangle([border, border, width - border, height - border], fill=40)
    shadow = shadow.filter(ImageFilter.GaussianBlur(border))
    dark_overlay = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.composite(img, dark_overlay, shadow.point(lambda p: 255 - p))

    return img


def _draw_fraction(draw: ImageDraw.ImageDraw, x: int, y: int, fraction: FractionLine) -> None:
    """分数(FractionLine)を「分子/横線/分母」の縦組みで描画する。"""

    cursor_x = x

    if fraction.prefix:
        draw.text((cursor_x, y + 12), fraction.prefix + "  ", font=_font, fill=(30, 30, 40))
        cursor_x += int(_text_width(draw, fraction.prefix + "  ", _font))

    num_width = _text_width(draw, fraction.numerator, _fraction_font)
    den_width = _text_width(draw, fraction.denominator, _fraction_font)
    bar_width = int(max(num_width, den_width)) + 12
    bar_x = cursor_x

    draw.text(
        (bar_x + (bar_width - num_width) / 2, y),
        fraction.numerator,
        font=_fraction_font,
        fill=(30, 30, 40),
    )
    bar_y = y + FRACTION_FONT_SIZE + 6
    draw.line([(bar_x, bar_y), (bar_x + bar_width, bar_y)], fill=(30, 30, 40), width=2)
    draw.text(
        (bar_x + (bar_width - den_width) / 2, bar_y + 4),
        fraction.denominator,
        font=_fraction_font,
        fill=(30, 30, 40),
    )

    if fraction.suffix:
        suffix_x = bar_x + bar_width + 10
        draw.text((suffix_x, y + 12), fraction.suffix, font=_font, fill=(30, 30, 40))


def render_note(text: str) -> bytes:
    """
    Geminiの解説テキストを手書き風ノート画像にして、PNGのバイト列で返す。
    """

    blocks: list[Block] = format_for_note(text)

    # 折り返しにはtextbboxが必要なので、まず仮の画像でdrawを作ってから折り返し・高さ計算を行う
    probe_img = Image.new("RGB", (IMAGE_WIDTH, 10))
    probe_draw = ImageDraw.Draw(probe_img)
    draw_items = _build_draw_items(probe_draw, blocks)

    total_height = MARGIN_TOP + MARGIN_BOTTOM + 60  # 60は末尾の signature 用
    for item in draw_items:
        total_height += item.height

    img = _make_paper_background(IMAGE_WIDTH, max(total_height, 300))
    draw = ImageDraw.Draw(img)

    y = MARGIN_TOP
    for item in draw_items:
        if item.kind == "fraction":
            _draw_fraction(draw, MARGIN_LEFT, y, item.payload)
        elif item.payload:
            x_jitter = random.uniform(-2, 2)
            draw.text((MARGIN_LEFT + x_jitter, y), item.payload, font=_font, fill=(30, 30, 40))
        y += item.height

    signature = "Aster"
    sig_width = _text_width(draw, signature, _signature_font)
    draw.text(
        (IMAGE_WIDTH - MARGIN_RIGHT - sig_width, y + 10),
        signature,
        font=_signature_font,
        fill=(150, 150, 160),
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()