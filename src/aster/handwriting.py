"""
handwriting.py
--------------
formatter.pyが整形したBlockのリストを受け取り、「手書きノート風の画像」にして返す。

Discordは通常のチャットでLaTeX($E$ みたいな数式記法)を描画してくれないため、
数式や詳しい解説は、紙の上に手書き文字で書いたような画像にして送ることで読みやすくする。

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
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from aster.formatter import Block, FractionLine, TextLine, format_for_note

# 画像サイズ・余白・フォントサイズ等の定数（これらを先に定義する）
IMAGE_WIDTH = 800
MARGIN_TOP = 60
MARGIN_BOTTOM = 60
MARGIN_LEFT = 90  # 赤い縦線の右側から文字を書き始めるための余白
MARGIN_RIGHT = 50
LINE_HEIGHT = 46
FONT_SIZE = 30
FRACTION_FONT_SIZE = 26

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
    print(f"[Debug] フォントを探している場所: {_FONT_DIR.resolve()}")

    # 1. まず本命フォントを探す
    for name in _PREFERRED_FONT_CANDIDATES:
        candidate = _FONT_DIR / name
        if candidate.exists():
            print(f"[Info] 本命フォントを発見しました: {candidate.name}")
            return candidate

    # 2. 次にフォールバック(Yomogi)を探す
    fallback = _FONT_DIR / _FALLBACK_FONT
    if fallback.exists():
        print(f"[Info] Yomogiフォントを発見しました: {fallback.name}")
        return fallback

    # 3. どちらも無ければ fonts フォルダ内にある既存の .ttf / .otf を探す
    font_files = list(_FONT_DIR.glob("*.otf")) + list(_FONT_DIR.glob("*.ttf"))
    if font_files:
        print(f"[Info] フォルダ内のフォントを発見しました: {font_files[0].name}")
        return font_files[0]

    # 4. 中身を表示してエラー
    existing_files = [p.name for p in _FONT_DIR.glob("*")] if _FONT_DIR.exists() else "フォルダが存在しません"
    print(f"[Debug] {_FONT_DIR} の中身: {existing_files}")

    raise FileNotFoundError(
        f"フォントファイルが見つかりません！ '{_FONT_DIR}' 内を確認してください。"
    )


# 定数が定義されたあとにフォントを読み込む
_font_path = _resolve_font_path()
_font = ImageFont.truetype(str(_font_path), FONT_SIZE)
_fraction_font = ImageFont.truetype(str(_font_path), FRACTION_FONT_SIZE)
_signature_font = ImageFont.truetype(str(_font_path), 22)


def _resolve_font_path() -> Path:
    for name in _PREFERRED_FONT_CANDIDATES:
        candidate = _FONT_DIR / name
        if candidate.exists():
            return candidate
    return _FONT_DIR / _FALLBACK_FONT


_font_path = _resolve_font_path()
_font = ImageFont.truetype(str(_font_path), FONT_SIZE)
_fraction_font = ImageFont.truetype(str(_font_path), FRACTION_FONT_SIZE)
_signature_font = ImageFont.truetype(str(_font_path), 22)


def _make_paper_background(width: int, height: int) -> Image.Image:
    """
    B5ルーズリーフ風の紙背景を作る。
    - わずかに色味のあるオフホワイト
    - 少し青みのある横罏線
    - 左側の赤い縦線(ルーズリーフの定番)
    - 気づく程度の紙の影(周囲をわずかに暗くする)
    """

    base_color = random.choice([(255, 253, 248), (253, 251, 245), (255, 255, 252)])
    img = Image.new("RGB", (width, height), base_color)
    draw = ImageDraw.Draw(img)

    # 横罫線(薄い青)
    rule_color = (185, 205, 232)
    y = MARGIN_TOP
    while y < height - MARGIN_BOTTOM // 2:
        draw.line([(30, y), (width - 20, y)], fill=rule_color, width=1)
        y += LINE_HEIGHT

    # 左の赤い縦線(ルーズリーフ・大学ノートの定番デザイン)
    red_line_x = MARGIN_LEFT - 25
    draw.line(
        [(red_line_x, 10), (red_line_x, height - 10)],
        fill=(215, 110, 110),
        width=2,
    )

    # 紙の影(周囲をわずかに暗くするビネット効果)
    shadow = Image.new("L", (width, height), 0)
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rectangle([0, 0, width, height], fill=0)
    border = 18
    shadow_draw.rectangle(
        [border, border, width - border, height - border], fill=40
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(border))
    dark_overlay = Image.new("RGB", (width, height), (0, 0, 0))
    img = Image.composite(img, dark_overlay, shadow.point(lambda p: 255 - p))

    return img


def _draw_fraction(
    draw: ImageDraw.ImageDraw, x: int, y: int, fraction: FractionLine
) -> int:
    """
    分数(FractionLine)を「分子/横線/分母」の縦組みで描画する。
    戻り値: この分数が占めた高さ(次の行のyを計算するため)。
    """

    cursor_x = x

    if fraction.prefix:
        draw.text((cursor_x, y + 12), fraction.prefix + "  ", font=_font, fill=(30, 30, 40))
        prefix_width = draw.textlength(fraction.prefix + "  ", font=_font)
        cursor_x += int(prefix_width)

    num_width = draw.textlength(fraction.numerator, font=_fraction_font)
    den_width = draw.textlength(fraction.denominator, font=_fraction_font)
    bar_width = int(max(num_width, den_width)) + 12
    bar_x = cursor_x

    # 分子(中央寄せ)
    draw.text(
        (bar_x + (bar_width - num_width) / 2, y),
        fraction.numerator,
        font=_fraction_font,
        fill=(30, 30, 40),
    )
    # 横線
    bar_y = y + FRACTION_FONT_SIZE + 6
    draw.line([(bar_x, bar_y), (bar_x + bar_width, bar_y)], fill=(30, 30, 40), width=2)
    # 分母(中央寄せ)
    draw.text(
        (bar_x + (bar_width - den_width) / 2, bar_y + 4),
        fraction.denominator,
        font=_fraction_font,
        fill=(30, 30, 40),
    )

    return FRACTION_FONT_SIZE * 2 + 24  # 分数が占める高さ


def render_note(text: str) -> bytes:
    """
    Geminiの解説テキストを手書き風ノート画像にして、PNGのバイト列で返す。
    """

    blocks: list[Block] = format_for_note(text)

    # まず高さを見積もる(分数は通常行より高さを取るため)
    total_height = MARGIN_TOP + MARGIN_BOTTOM
    for block in blocks:
        if isinstance(block, FractionLine):
            total_height += FRACTION_FONT_SIZE * 2 + 24
        else:
            total_height += LINE_HEIGHT

    total_height += 60  # 末尾の signature 用の余白

    img = _make_paper_background(IMAGE_WIDTH, max(total_height, 300))
    draw = ImageDraw.Draw(img)

    y = MARGIN_TOP
    for block in blocks:
        if isinstance(block, FractionLine):
            used_height = _draw_fraction(draw, MARGIN_LEFT, y, block)
            y += used_height
        else:
            if block.text:
                x_jitter = random.uniform(-2, 2)
                draw.text(
                    (MARGIN_LEFT + x_jitter, y),
                    block.text,
                    font=_font,
                    fill=(30, 30, 40),
                )
            y += LINE_HEIGHT

    # 右下に小さく "Aster" の署名
    signature = "Aster"
    sig_width = draw.textlength(signature, font=_signature_font)
    draw.text(
        (IMAGE_WIDTH - MARGIN_RIGHT - sig_width, y + 10),
        signature,
        font=_signature_font,
        fill=(150, 150, 160),
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()