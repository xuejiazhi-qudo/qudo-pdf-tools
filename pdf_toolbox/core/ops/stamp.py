"""叠加类操作：水印、页码页眉页脚、表单填写与签名。"""

from __future__ import annotations

import datetime as _dt
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from ..worker import Progress

Progress_ = Optional[Progress]

CJK_FONT = "china-s"
_LATIN1 = re.compile(r"^[\x00-\xff]*$")


def _font_for(text: str, latin_font: str = "helv") -> str:
    """含非 Latin-1 字符（中文等）时自动切到内置 CJK 字体。"""
    return latin_font if _LATIN1.match(text or "") else CJK_FONT


def _rgb(hex_or_tuple) -> Tuple[float, float, float]:
    if isinstance(hex_or_tuple, str):
        s = hex_or_tuple.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        return (int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255)
    seq = tuple(hex_or_tuple)
    if seq and max(seq) > 1.0:
        return tuple(v / 255 for v in seq[:3])
    return tuple(seq[:3])


def _text_width(page: pymupdf.Page, text: str, fontname: str, fontsize: float) -> float:
    try:
        return float(page.get_text_length(text, fontname=fontname, fontsize=fontsize))
    except Exception:
        return len(text) * fontsize * 0.55


# ====================================================================== 水印

POS_TL, POS_TC, POS_TR = "tl", "tc", "tr"
POS_ML, POS_MC, POS_MR = "ml", "mc", "mr"
POS_BL, POS_BC, POS_BR = "bl", "bc", "br"

POSITIONS = [POS_TL, POS_TC, POS_TR, POS_ML, POS_MC, POS_MR, POS_BL, POS_BC, POS_BR]


@dataclass
class WatermarkSettings:
    type: str = "text"                    # text | image
    text: str = "CONFIDENTIAL"
    font_size: float = 48.0
    color: Tuple[float, float, float] = (0.6, 0.6, 0.6)
    opacity: float = 0.25
    rotation: float = -45.0
    bold: bool = False

    image_path: Optional[str] = None
    image_bytes: Optional[bytes] = None
    image_width_pct: float = 25.0         # 占页面宽度百分比

    position: str = POS_MC
    h_margin: float = 20.0
    v_margin: float = 20.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    mode: str = "single"                  # single | tiled
    tile_spacing_x: float = 100.0
    tile_spacing_y: float = 100.0
    staggered: bool = False

    above_content: bool = True
    pages: Optional[Sequence[int]] = None

    def validate(self) -> None:
        if self.type == "text" and not (self.text or "").strip():
            raise ValueError("水印文字不能为空")
        if self.type == "image" and not (self.image_path or self.image_bytes):
            raise ValueError("请先选择水印图片")
        if self.position not in POSITIONS:
            raise ValueError(f"未知的水印位置：{self.position}")
        if not 0.0 < self.opacity <= 1.0:
            raise ValueError("不透明度必须在 1%–100% 之间")


def _anchor(page: pymupdf.Page, s: WatermarkSettings) -> pymupdf.Point:
    w, h = page.rect.width, page.rect.height
    p = s.position
    if "l" in p:
        x = s.h_margin + s.offset_x
    elif "r" in p:
        x = w - s.h_margin + s.offset_x
    else:
        x = w / 2 + s.offset_x
    if "t" in p:
        y = s.v_margin + s.offset_y
    elif "b" in p:
        y = h - s.v_margin + s.offset_y
    else:
        y = h / 2 + s.offset_y
    return pymupdf.Point(x, y)


def _tile_anchors(page: pymupdf.Page, s: WatermarkSettings) -> List[pymupdf.Point]:
    w, h = page.rect.width, page.rect.height
    sx = max(20.0, s.tile_spacing_x)
    sy = max(20.0, s.tile_spacing_y)
    out: List[pymupdf.Point] = []
    row = 0
    y = sy / 2
    while y < h + sy:
        x = sx / 2
        shift = (sx / 2) if (s.staggered and row % 2 == 1) else 0.0
        while x + shift < w + sx:
            out.append(pymupdf.Point(x + shift, y))
            x += sx
        y += sy
        row += 1
    return out


def apply_watermark(
    doc: pymupdf.Document,
    settings: WatermarkSettings,
    progress: Progress_ = None,
) -> int:
    """把水印画到选中页面内容之上（或之下）。返回处理页数。"""
    pr = progress or Progress()
    settings.validate()
    targets = (
        [i for i in settings.pages if 0 <= i < doc.page_count]
        if settings.pages is not None
        else list(range(doc.page_count))
    )
    if not targets:
        return 0

    overlay = settings.above_content
    color = _rgb(settings.color)

    img_png: Optional[bytes] = None
    img_aspect = 1.0
    if settings.type == "image":
        img_png, img_aspect = _prepare_image(settings)

    for k, pno in enumerate(targets):
        pr.step(k, len(targets), f"加水印第 {pno + 1} 页")
        page = doc.load_page(pno)

        if settings.mode == "tiled":
            anchors = _tile_anchors(page, settings)
        else:
            anchors = [_anchor(page, settings)]

        for anchor in anchors:
            if settings.type == "text":
                _draw_text_watermark(page, settings, anchor, color, overlay)
            else:
                _draw_image_watermark(page, settings, anchor, img_png, img_aspect, overlay)

    pr.report(100, "完成")
    return len(targets)


def _draw_text_watermark(
    page: pymupdf.Page,
    s: WatermarkSettings,
    anchor: pymupdf.Point,
    color: Tuple[float, float, float],
    overlay: bool,
) -> None:
    font = _font_for(s.text, "hebo" if s.bold else "helv")
    width = _text_width(page, s.text, font, s.font_size)

    # 以锚点为旋转中心；水平/垂直居中在锚点上
    start = pymupdf.Point(anchor.x - width / 2, anchor.y + s.font_size * 0.35)
    matrix = pymupdf.Matrix(s.rotation)
    page.insert_text(
        start,
        s.text,
        fontsize=s.font_size,
        fontname=font,
        color=color,
        fill_opacity=s.opacity,
        morph=(anchor, matrix),
        overlay=overlay,
    )


def _prepare_image(settings: WatermarkSettings) -> Tuple[bytes, float]:
    from PIL import Image

    src = settings.image_bytes or (
        open(settings.image_path, "rb").read() if settings.image_path else None
    )
    if not src:
        raise ValueError("水印图片读取失败")

    im = Image.open(io.BytesIO(src)).convert("RGBA")
    alpha = im.getchannel("A").point(lambda v: int(v * settings.opacity))
    im.putalpha(alpha)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue(), im.width / max(1, im.height)


def _draw_image_watermark(
    page: pymupdf.Page,
    s: WatermarkSettings,
    anchor: pymupdf.Point,
    png: bytes,
    aspect: float,
    overlay: bool,
) -> None:
    w = page.rect.width * max(0.05, min(1.0, s.image_width_pct / 100.0))
    h = w / aspect if aspect else w
    rect = pymupdf.Rect(anchor.x - w / 2, anchor.y - h / 2, anchor.x + w / 2, anchor.y + h / 2)

    if abs(s.rotation) < 0.5:
        page.insert_image(rect, stream=png, overlay=overlay)
        return

    # 旋转：先画到临时页再 show_pdf_page 带旋转贴回
    tmp = pymupdf.open()
    try:
        tp = tmp.new_page(width=max(1.0, w), height=max(1.0, h))
        tp.insert_image(tp.rect, stream=png)
        page.show_pdf_page(rect, tmp, 0, rotate=int(round(s.rotation)), overlay=overlay)
    finally:
        tmp.close()


# ====================================================================== 页码 / 页眉页脚

FMT_NUMBER = "1"
FMT_ZERO2 = "01"
FMT_ZERO3 = "001"
FMT_PAGE_N = "page-1"
FMT_PAGE_N_OF = "page-1-of-n"
FMT_N_OF = "1-of-n"
FMT_ZH = "zh-1"
FMT_ZH_OF = "zh-1-of-n"
FMT_CUSTOM = "custom"

FORMAT_LABELS = {
    FMT_NUMBER: "1, 2, 3",
    FMT_ZERO2: "01, 02, 03",
    FMT_ZERO3: "001, 002, 003",
    FMT_PAGE_N: "Page 1",
    FMT_PAGE_N_OF: "Page 1 of 20",
    FMT_N_OF: "1 / 20",
    FMT_ZH: "第 1 页",
    FMT_ZH_OF: "第 1 页，共 20 页",
    FMT_CUSTOM: "自定义模板",
}

FONT_MAP = {
    "Helvetica": "helv",
    "Helvetica-Bold": "hebo",
    "Times-Roman": "tiro",
    "Times-Roman-Bold": "tibo",
    "Courier": "cour",
    "CJK": CJK_FONT,
}


@dataclass
class PageNumberSettings:
    position: str = "bottom-center"
    position_mode: str = "same"           # same | mirror
    mirror_odd: str = "bottom-right"
    mirror_even: str = "bottom-left"

    fmt: str = FMT_NUMBER
    custom_template: str = "{page} / {pages}"
    start_number: int = 1
    skip_pages: int = 0
    page_range_mode: str = "all"          # all | except-cover | odd | even | custom
    custom_range: str = ""
    numbering_mode: str = "continuous"    # continuous | original
    use_document_total: bool = False

    font: str = "Helvetica"
    font_size: float = 10.0
    color: Tuple[float, float, float] = (0.27, 0.27, 0.27)
    opacity: float = 1.0
    bold: bool = False

    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = ""
    footer_right: str = ""

    margin_top: float = 24.0
    margin_bottom: float = 24.0
    margin_lr: float = 32.0
    offset_x: float = 0.0
    offset_y: float = 0.0

    pages: Optional[Sequence[int]] = None


def _format_number(
    s: PageNumberSettings,
    number: int,
    total: int,
    page_index: int,
    doc_pages: int,
    filename: str,
) -> str:
    if s.fmt == FMT_NUMBER:
        return str(number)
    if s.fmt == FMT_ZERO2:
        return f"{number:02d}"
    if s.fmt == FMT_ZERO3:
        return f"{number:03d}"
    if s.fmt == FMT_PAGE_N:
        return f"Page {number}"
    if s.fmt == FMT_PAGE_N_OF:
        return f"Page {number} of {total}"
    if s.fmt == FMT_N_OF:
        return f"{number} / {total}"
    if s.fmt == FMT_ZH:
        return f"第 {number} 页"
    if s.fmt == FMT_ZH_OF:
        return f"第 {number} 页，共 {total} 页"
    return _expand_template(
        s.custom_template, number, total, page_index + 1, doc_pages, filename
    )


def _expand_template(
    tpl: str, number: int, total: int, doc_page: int, doc_pages: int, filename: str
) -> str:
    return (
        tpl.replace("{page}", str(number))
        .replace("{pages}", str(total))
        .replace("{documentPage}", str(doc_page))
        .replace("{documentPages}", str(doc_pages))
        .replace("{filename}", filename)
    )


def _resolve_targets(doc: pymupdf.Document, s: PageNumberSettings) -> List[int]:
    from .. import pagerange

    n = doc.page_count
    if s.pages is not None:
        base = [i for i in s.pages if 0 <= i < n]
    elif s.page_range_mode == "except-cover":
        base = list(range(1, n))
    elif s.page_range_mode == "odd":
        base = list(range(0, n, 2))
    elif s.page_range_mode == "even":
        base = list(range(1, n, 2))
    elif s.page_range_mode == "custom":
        base = pagerange.parse(s.custom_range, n)
    else:
        base = list(range(n))

    return [i for i in base if i >= s.skip_pages]


def apply_page_numbers(
    doc: pymupdf.Document,
    settings: PageNumberSettings,
    progress: Progress_ = None,
) -> Dict[str, int]:
    """添加页码与页眉页脚。返回处理/跳过页数。"""
    pr = progress or Progress()
    targets = _resolve_targets(doc, settings)
    total_label = doc.page_count if settings.use_document_total else len(targets)
    filename = doc.name or ""
    if filename:
        filename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        filename = filename.rsplit(".", 1)[0]

    color = _rgb(settings.color)
    processed = 0

    for k, pno in enumerate(targets):
        pr.step(k, len(targets), f"第 {pno + 1} 页")
        page = doc.load_page(pno)

        if settings.numbering_mode == "original":
            number = pno + 1
        else:
            number = settings.start_number + k

        label = _format_number(
            settings, number, total_label, pno, doc.page_count, filename
        )

        pos = settings.position
        if settings.position_mode == "mirror":
            pos = settings.mirror_odd if (pno % 2 == 1) else settings.mirror_even

        _draw_page_number(page, settings, pos, label, color)

        # 页眉页脚
        header = {
            "left": _expand_template(settings.header_left, number, total_label, pno + 1, doc.page_count, filename),
            "center": _expand_template(settings.header_center, number, total_label, pno + 1, doc.page_count, filename),
            "right": _expand_template(settings.header_right, number, total_label, pno + 1, doc.page_count, filename),
        }
        footer = {
            "left": _expand_template(settings.footer_left, number, total_label, pno + 1, doc.page_count, filename),
            "center": _expand_template(settings.footer_center, number, total_label, pno + 1, doc.page_count, filename),
            "right": _expand_template(settings.footer_right, number, total_label, pno + 1, doc.page_count, filename),
        }
        for align, text in header.items():
            if text.strip():
                _draw_header_footer(page, settings, "top", align, text, color)
        for align, text in footer.items():
            if text.strip():
                _draw_header_footer(page, settings, "bottom", align, text, color)

        processed += 1

    pr.report(100, "完成")
    return {"processed": processed, "skipped": doc.page_count - processed}


def _fontname_for(settings: PageNumberSettings, text: str) -> str:
    if not _LATIN1.match(text or ""):
        return CJK_FONT
    if settings.bold and settings.font == "Helvetica":
        return FONT_MAP["Helvetica-Bold"]
    return FONT_MAP.get(settings.font, "helv")


def _draw_page_number(
    page: pymupdf.Page,
    s: PageNumberSettings,
    pos: str,
    label: str,
    color: Tuple[float, float, float],
) -> None:
    font = _fontname_for(s, label)
    width = _text_width(page, label, font, s.font_size)
    pw, ph = page.rect.width, page.rect.height

    part, _, align = pos.partition("-")
    if part == "top":
        y = s.margin_top + s.offset_y
    else:
        y = ph - s.margin_bottom + s.offset_y

    if align == "left":
        x = s.margin_lr + s.offset_x
    elif align == "right":
        x = pw - s.margin_lr - width + s.offset_x
    else:
        x = (pw - width) / 2 + s.offset_x

    page.insert_text(
        pymupdf.Point(x, y),
        label,
        fontsize=s.font_size,
        fontname=font,
        color=color,
        fill_opacity=s.opacity,
        overlay=True,
    )


def _draw_header_footer(
    page: pymupdf.Page,
    s: PageNumberSettings,
    edge: str,
    align: str,
    text: str,
    color: Tuple[float, float, float],
) -> None:
    font = _fontname_for(s, text)
    width = _text_width(page, text, font, s.font_size)
    pw, ph = page.rect.width, page.rect.height

    if edge == "top":
        y = s.margin_top + s.offset_y
    else:
        y = ph - s.margin_bottom + s.offset_y

    if align == "left":
        x = s.margin_lr + s.offset_x
    elif align == "right":
        x = pw - s.margin_lr - width + s.offset_x
    else:
        x = (pw - width) / 2 + s.offset_x

    page.insert_text(
        pymupdf.Point(x, y),
        text,
        fontsize=s.font_size,
        fontname=font,
        color=color,
        fill_opacity=s.opacity,
        overlay=True,
    )


# ====================================================================== 填写与签名

KIND_TEXT = "text"
KIND_DATE = "date"
KIND_CHECK = "checkmark"
KIND_CROSS = "cross"
KIND_DOT = "dot"
KIND_HOLLOW_DOT = "hollow-dot"
KIND_SQUARE = "square"
KIND_LINE = "line"
KIND_INITIALS = "initials"
KIND_TYPED_SIG = "typed-signature"
KIND_DRAWN_SIG = "drawn-signature"
KIND_IMAGE_SIG = "image-signature"

_VECTOR_SYMBOLS = {KIND_CHECK, KIND_CROSS, KIND_DOT, KIND_SQUARE}


def _draw_vector_symbol(
    page: pymupdf.Page,
    el: "FillElement",
    rect: pymupdf.Rect,
    color: Tuple[float, float, float],
) -> None:
    """用矢量图形画符号，避免依赖字体字形（内置字体缺 ✓✗ 等）。"""
    shape = page.new_shape()
    width = max(0.75, el.font_size / 8)
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1

    if el.kind == KIND_CHECK:
        shape.draw_polyline(
            [
                pymupdf.Point(x0 + rect.width * 0.10, y0 + rect.height * 0.55),
                pymupdf.Point(x0 + rect.width * 0.38, y0 + rect.height * 0.85),
                pymupdf.Point(x0 + rect.width * 0.92, y0 + rect.height * 0.12),
            ]
        )
        shape.finish(color=color, width=width, stroke_opacity=el.opacity, closePath=False)
    elif el.kind == KIND_CROSS:
        shape.draw_line(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1))
        shape.draw_line(pymupdf.Point(x1, y0), pymupdf.Point(x0, y1))
        shape.finish(color=color, width=width, stroke_opacity=el.opacity, closePath=False)
    elif el.kind == KIND_DOT:
        center = pymupdf.Point(x0 + rect.width / 2, y0 + rect.height / 2)
        shape.draw_circle(center, min(rect.width, rect.height) / 2)
        shape.finish(color=color, fill=color, fill_opacity=el.opacity,
                     stroke_opacity=el.opacity)
    elif el.kind == KIND_SQUARE:
        shape.draw_rect(rect)
        shape.finish(color=color, fill=color, fill_opacity=el.opacity,
                     stroke_opacity=el.opacity)

    shape.commit()

DATE_FORMATS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD Mon YYYY": "%d %b %Y",
    "Month DD, YYYY": "%B %d, %Y",
}


def format_date(value: Optional[_dt.date], fmt: str) -> str:
    d = value or _dt.date.today()
    return d.strftime(DATE_FORMATS.get(fmt, DATE_FORMATS["YYYY-MM-DD"]))


@dataclass
class FillElement:
    kind: str
    page: int
    x: float
    y: float
    width: float = 100.0
    height: float = 20.0
    text: str = ""
    font_size: float = 12.0
    color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    opacity: float = 1.0
    rotation: float = 0.0
    font_family: str = "Helvetica"
    align: str = "left"
    image_bytes: Optional[bytes] = None


def apply_fill_elements(
    doc: pymupdf.Document,
    elements: Sequence[FillElement],
    progress: Progress_ = None,
) -> int:
    """把填写/签名元素压平绘制到页面内容流（与网页版行为一致）。"""
    pr = progress or Progress()
    by_page: Dict[int, List[FillElement]] = {}
    for el in elements:
        by_page.setdefault(el.page, []).append(el)

    drawn = 0
    keys = sorted(by_page.keys())
    for k, pno in enumerate(keys):
        pr.step(k, len(keys), f"第 {pno + 1} 页")
        if not 0 <= pno < doc.page_count:
            continue
        page = doc.load_page(pno)
        for el in by_page[pno]:
            _draw_fill_element(page, el)
            drawn += 1

    pr.report(100, "完成")
    return drawn


def _draw_fill_element(page: pymupdf.Page, el: FillElement) -> None:
    color = _rgb(el.color)
    rect = pymupdf.Rect(el.x, el.y, el.x + el.width, el.y + el.height)

    if el.kind in (KIND_DRAWN_SIG, KIND_IMAGE_SIG) and el.image_bytes:
        page.insert_image(rect, stream=el.image_bytes, overlay=True)
        return

    if el.kind == KIND_HOLLOW_DOT:
        shape = page.new_shape()
        shape.draw_circle(rect.tl + pymupdf.Point(rect.width / 2, rect.height / 2),
                          min(rect.width, rect.height) / 2)
        shape.finish(color=color, fill=None, width=max(0.5, el.font_size / 8),
                     stroke_opacity=el.opacity)
        shape.commit()
        return

    if el.kind == KIND_LINE:
        shape = page.new_shape()
        mid_y = el.y + el.height / 2
        shape.draw_line(pymupdf.Point(el.x, mid_y), pymupdf.Point(el.x + el.width, mid_y))
        shape.finish(color=color, width=max(0.5, el.font_size / 8), stroke_opacity=el.opacity)
        shape.commit()
        return

    if el.kind in _VECTOR_SYMBOLS:
        _draw_vector_symbol(page, el, rect, color)
        return

    text = el.text
    font = _font_for(text, FONT_MAP.get(el.font_family, "helv"))
    size = el.font_size

    if not text:
        return

    width = _text_width(page, text, font, size)
    if el.align == "center":
        x = el.x + (el.width - width) / 2
    elif el.align == "right":
        x = el.x + el.width - width
    else:
        x = el.x

    morph = None
    if abs(el.rotation) > 0.5:
        pivot = pymupdf.Point(x, el.y + el.height)
        morph = (pivot, pymupdf.Matrix(el.rotation))

    page.insert_text(
        pymupdf.Point(x, el.y + el.height * 0.8),
        text,
        fontsize=size,
        fontname=font,
        color=color,
        fill_opacity=el.opacity,
        morph=morph,
        overlay=True,
    )


def render_signature_image(
    strokes: Sequence[Sequence[Tuple[float, float, float]]],
    width: int,
    height: int,
    pen_color: Tuple[int, int, int] = (0, 0, 0),
    pen_width: float = 2.0,
    crop_whitespace: bool = True,
) -> bytes:
    """把手写板笔画（x, y, pressure）渲染成透明背景 PNG。"""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (max(8, width), max(8, height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for stroke in strokes:
        pts = [(p[0], p[1]) for p in stroke]
        if len(pts) == 1:
            pts = [pts[0], (pts[0][0] + 0.6, pts[0][1] + 0.6)]
        if len(pts) >= 2:
            draw.line(pts, fill=(*pen_color, 255), width=max(1, int(round(pen_width))), joint="curve")

    if crop_whitespace:
        bbox = img.getbbox()
        if bbox:
            pad = 2
            bbox = (
                max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                min(img.width, bbox[2] + pad), min(img.height, bbox[3] + pad),
            )
            img = img.crop(bbox)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_typed_signature(
    name: str,
    font_path: Optional[str] = None,
    font_size: int = 48,
    color: Tuple[int, int, int] = (0, 0, 0),
    slant: float = 0.0,
) -> bytes:
    """把打字签名渲染成透明背景 PNG。"""
    from PIL import Image, ImageDraw, ImageFont

    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = _pick_script_font(font_size)

    img = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), name, font=font)
    w = int(bbox[2] - bbox[0]) + 24
    h = int(bbox[3] - bbox[1]) + 24
    img = Image.new("RGBA", (max(8, w), max(8, h)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((12 - bbox[0], 12 - bbox[1]), name, font=font, fill=(*color, 255))

    if abs(slant) > 0.5:
        img = img.transform(
            img.size,
            Image.AFFINE,
            (1, _dt_mod_tan(slant), -_dt_mod_tan(slant) * img.height / 2, 0, 1, 0),
            resample=Image.BICUBIC,
        )

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _dt_mod_tan(deg: float) -> float:
    import math

    return math.tan(math.radians(deg))


_SCRIPT_FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoesc.ttf",
    "C:/Windows/Fonts/BRUSHSCI.TTF",
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/georgia.ttf",
    "C:/Windows/Fonts/msyh.ttf",
]


def _pick_script_font(size: int):
    from PIL import ImageFont

    for path in _SCRIPT_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def remove_white_background(
    image_bytes: bytes, tolerance: int = 30, crop_whitespace: bool = True
) -> bytes:
    """把签名图片的白底抠成透明。"""
    from PIL import Image

    im = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    data = im.getdata()
    out = []
    for r, g, b, a in data:
        if r >= 255 - tolerance and g >= 255 - tolerance and b >= 255 - tolerance:
            out.append((r, g, b, 0))
        else:
            out.append((r, g, b, a))
    im.putdata(out)

    if crop_whitespace:
        bbox = im.getbbox()
        if bbox:
            im = im.crop(bbox)

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def detect_form_info(doc: pymupdf.Document) -> Dict[str, object]:
    """检测表单字段与数字签名，供界面提示。"""
    fields = 0
    signatures = 0
    per_page: List[Dict[str, object]] = []
    for pno, page in enumerate(doc.pages()):
        pf = 0
        for w in page.widgets():
            pf += 1
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                signatures += 1
        fields += pf
        per_page.append({"page": pno, "has_form_fields": pf > 0})

    return {
        "has_form_fields": fields > 0,
        "form_field_count": fields,
        "has_digital_signature": signatures > 0,
        "pages": per_page,
    }


def list_form_fields(doc: pymupdf.Document) -> List[Dict[str, object]]:
    """列出所有表单字段，供填写面板展示。"""
    out: List[Dict[str, object]] = []
    for pno, page in enumerate(doc.pages()):
        for w in page.widgets():
            out.append(
                {
                    "page": pno,
                    "name": w.field_name or "",
                    "label": w.field_label or "",
                    "type": w.field_type_string or "",
                    "value": w.field_value or "",
                    "rect": tuple(w.rect),
                    "choices": list(w.choice_values or []),
                }
            )
    return out


def set_form_field_value(doc: pymupdf.Document, page: int, name: str, value: str) -> bool:
    if not 0 <= page < doc.page_count:
        return False
    pg = doc.load_page(page)
    for w in pg.widgets():
        if w.field_name == name:
            w.field_value = value
            w.update()
            return True
    return False
