"""
PDFの読み取りを担当するモジュール。

処理方針:
- まずPyMuPDFでページごとのテキスト抽出を試す。
- 抽出結果が不自然なページだけを画像化し、Gemini Visionで読み取る。
- PDFのページ数上限は画像添付の上限とは別に管理する。

PDFそのものをAIに丸ごと渡すのではなく、Aster側で「読めるページ」と
「画像として読むべきページ」を切り分けることで、通常の文字PDFを高速に
処理しつつ、スキャンPDFや文字化けにも対応する。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF

from aster.ai import describe_image

# PDFは画像添付とは別の上限で管理する。
MAX_PDF_PAGES = 10

# PDFを画像化するときの解像度。
# 教材の文字を読みやすくしつつ、画像が巨大になりすぎないようにする。
PDF_RENDER_SCALE = 2.0

# テキスト抽出結果の妥当性チェックに使う基準。
MIN_TEXT_LENGTH = 20
MAX_REPLACEMENT_RATIO = 0.02
MAX_CONTROL_RATIO = 0.02
MIN_NORMAL_CHAR_RATIO = 0.45

# 制御文字のうち、通常の文章で許容する改行・タブ・復帰は除外する。
_ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t"}


@dataclass
class PDFPageResult:
    """1ページ分の読み取り結果。"""

    page_number: int
    text: str
    used_vision: bool = False
    readable: bool = True


@dataclass
class PDFResult:
    """PDF全体の読み取り結果。"""

    text: str
    page_count: int
    unreadable_pages: list[int]
    vision_pages: list[int]


def _normal_char_ratio(text: str) -> float:
    """文章として扱いやすい文字(日本語・英数字など)の割合を返す。"""

    if not text:
        return 0.0

    normal_count = 0

    for char in text:
        category = unicodedata.category(char)
        if category[0] in {"L", "N"}:
            normal_count += 1

    return normal_count / len(text)


def _control_ratio(text: str) -> float:
    """許容されない制御文字の割合を返す。"""

    if not text:
        return 0.0

    control_count = sum(
        1
        for char in text
        if unicodedata.category(char) == "Cc" and char not in _ALLOWED_CONTROL_CHARS
    )

    return control_count / len(text)


def _replacement_ratio(text: str) -> float:
    """Unicodeの置換文字「�」の割合を返す。"""

    if not text:
        return 0.0

    return text.count("�") / len(text)


def is_text_valid(text: str) -> bool:
    """
    PyMuPDFが抽出したテキストを簡易判定する。

    「文字が少ない」「置換文字が多い」「制御文字が多い」「通常の文字が
    極端に少ない」のいずれかに該当する場合は、テキストを信用せず、
    ページ画像によるVision読み取りへ切り替える。
    """

    normalized = re.sub(r"\s+", "", text)

    if len(normalized) < MIN_TEXT_LENGTH:
        return False

    if _replacement_ratio(text) > MAX_REPLACEMENT_RATIO:
        return False

    if _control_ratio(text) > MAX_CONTROL_RATIO:
        return False

    if _normal_char_ratio(text) < MIN_NORMAL_CHAR_RATIO:
        return False

    return True


def _render_page(page: fitz.Page) -> bytes:
    """PDFページをPNG画像としてバイト列に変換する。"""

    matrix = fitz.Matrix(PDF_RENDER_SCALE, PDF_RENDER_SCALE)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    return pixmap.tobytes("png")


def _read_page_with_vision(page: fitz.Page) -> tuple[str, bool]:
    """1ページを画像化してGemini Visionで読み取る。"""

    image_data = _render_page(page)
    result = describe_image(
        [(image_data, "image/png")],
        prompt=(
            "この画像はPDFの1ページです。画像内の文章、数式、表、図の内容を、"
            "後で別のAIが問題を解くための資料として使えるように、できるだけ"
            "正確に日本語で文字起こし・説明してください。\n"
            "文章だけでなく、数式や表の数値も省略しないでください。"
        ),
    )

    text = result.strip()
    return text, bool(text)


def process_pdf(data: bytes) -> PDFResult:
    """
    PDFを読み取り、Geminiへ渡せるテキストにまとめる。

    Returns
    -------
    PDFResult
        全ページの内容、ページ数、Visionへ切り替えたページ、
        最終的に読み取れなかったページを含む結果。
    """

    document = fitz.open(stream=data, filetype="pdf")

    try:
        page_count = len(document)

        if page_count == 0:
            raise ValueError("PDFにページがありません。")

        if page_count > MAX_PDF_PAGES:
            raise ValueError(
                f"PDFのページ数が上限({MAX_PDF_PAGES}ページ)を超えています。"
            )

        pages: list[PDFPageResult] = []
        unreadable_pages: list[int] = []
        vision_pages: list[int] = []

        for index, page in enumerate(document):
            page_number = index + 1
            extracted_text = page.get_text("text").strip()

            if is_text_valid(extracted_text):
                pages.append(
                    PDFPageResult(
                        page_number=page_number,
                        text=extracted_text,
                    )
                )
                continue

            vision_pages.append(page_number)

            try:
                vision_text, readable = _read_page_with_vision(page)
            except Exception:
                vision_text = ""
                readable = False

            if not readable:
                unreadable_pages.append(page_number)

            pages.append(
                PDFPageResult(
                    page_number=page_number,
                    text=vision_text,
                    used_vision=True,
                    readable=readable,
                )
            )

        combined_text = _combine_pages(pages)

        return PDFResult(
            text=combined_text,
            page_count=page_count,
            unreadable_pages=unreadable_pages,
            vision_pages=vision_pages,
        )

    finally:
        document.close()


def _combine_pages(pages: list[PDFPageResult]) -> str:
    """ページごとの内容を、AIが参照しやすい形にまとめる。"""

    sections: list[str] = []

    for page in pages:
        if not page.text:
            body = "(読み取りできませんでした)"
        else:
            body = page.text

        source = "画像から読み取り" if page.used_vision else "テキスト抽出"
        sections.append(f"【PDF {page.page_number}ページ目 / {source}】\n{body}")

    return "\n\n".join(sections)
