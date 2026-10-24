"""标注与批注：生成真实 PDF Annotation 对象，可选压平。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf

from ..worker import Progress
from .stamp import CJK_FONT, _font_for, _rgb

Progress_ = Optional[Progress]

T_HIGHLIGHT = "highlight"
T_UNDERLINE = "underline"
T_STRIKEOUT = "strikethrough"
T_FREEHAND = "freehand"
T_TEXT = "text"
T_NOTE = "sticky-note"
T_STAMP = "stamp"
T_IMAGE = "image"
T_RECT = "rect"
T_CIRCLE = "circle"
T_ARROW = "arrow"
T_LINE = "line"

ALL_TYPES = [
    T_HIGHLIGHT, T_UNDERLINE, T_STRIKEOUT, T_FREEHAND, T_TEXT, T_NOTE,
    T_STAMP, T_IMAGE, T_RECT, T_CIRCLE, T_ARROW, T_LINE,
]

TYPE_LABELS = {
    T_HIGHLIGHT: "高亮",
    T_UNDERLINE: "下划线",
    T_STRIKEOUT: "删除线",
    T_FREEHAND: "画笔",
    T_TEXT: "文字",
    T_NOTE: "便签",
    T_STAMP: "图章",
    T_IMAGE: "图片",
    T_RECT: "矩形",
    T_CIRCLE: "圆形",
    T_ARROW: "箭头",
    T_LINE: "直线",
}

STAMP_PRESETS = ["APPROVED", "REJECTED", "DRAFT", "REVIEWED", "CONFIDENTIAL", "COMPLETED"]

PRESET_COLORS = [
    "#FFFF00", "#FF0000", "#00FF00", "#0000FF", "#FF00FF",
    "#00FFFF", "#FFA500", "#808080", "#000000", "#FFFFFF",
]

_LINE_END_NONE = 0
_LINE_END_CLOSED_ARROW = 5


@dataclass
class AnnotationSpec:
    type: str
    page: int
    rect: Tuple[float, float, float, float] = (0, 0, 0, 0)
    points: List[List[Tuple[float, float]]] = field(default_factory=list)
    p1: Tuple[float, float] = (0, 0)
    p2: Tuple[float, float] = (0, 0)
    text: str = ""
    color: str = "#FFFF00"
    fill_color: Optional[str] = None
    line_width: float = 2.0
    opacity: float = 1.0
    font_size: float = 14.0
    bold: bool = False
    italic: bool = False
    align: str = "left"
    note_author: str = ""
    note_content: str = ""
    stamp_text: str = "APPROVED"
    image_bytes: Optional[bytes] = None
    locked: bool = False

    def validate(self) -> None:
        if self.type not in ALL_TYPES:
            raise ValueError(f"未知的标注类型：{self.type}")


def add_annotation(doc: pymupdf.Document, spec: AnnotationSpec) -> Optional[int]:
    """添加一条标注，返回所在页索引；image 类型直接压平绘制。"""
    spec.validate()
    if not 0 <= spec.page < doc.page_count:
        raise ValueError(f"页码超出范围：{spec.page + 1}")

    page = doc.load_page(spec.page)
    color = _rgb(spec.color)
    fill = _rgb(spec.fill_color) if spec.fill_color else None
    rect = pymupdf.Rect(*spec.rect)

    annot: Optional[pymupdf.Annot] = None

    if spec.type == T_HIGHLIGHT:
        annot = page.add_highlight_annot(rect)
    elif spec.type == T_UNDERLINE:
        annot = page.add_underline_annot(rect)
    elif spec.type == T_STRIKEOUT:
        annot = page.add_strikeout_annot(rect)
    elif spec.type == T_FREEHAND:
        strokes = [list(s) for s in spec.points if len(s) >= 1]
        if not strokes:
            raise ValueError("画笔路径为空")
        annot = page.add_ink_annot(strokes)
    elif spec.type == T_TEXT:
        font = _font_for(spec.text, "hebo" if spec.bold else "helv")
        annot = page.add_freetext_annot(
            rect,
            spec.text,
            fontsize=spec.font_size,
            fontname=font,
            text_color=color,
            fill_color=fill if fill else (1, 1, 0.85),
            align={"left": 0, "center": 1, "right": 2}.get(spec.align, 0),
        )
    elif spec.type == T_NOTE:
        annot = page.add_text_annot(rect.tl, spec.note_content or spec.text)
        if spec.note_author:
            annot.set_info(title=spec.note_author)
    elif spec.type == T_STAMP:
        idx = STAMP_PRESETS.index(spec.stamp_text) if spec.stamp_text in STAMP_PRESETS else 0
        annot = page.add_stamp_annot(rect, stamp=idx)
    elif spec.type == T_IMAGE:
        if not spec.image_bytes:
            raise ValueError("图片标注缺少图片数据")
        page.insert_image(rect, stream=spec.image_bytes, overlay=True)
        return spec.page
    elif spec.type == T_RECT:
        annot = page.add_rect_annot(rect)
    elif spec.type == T_CIRCLE:
        annot = page.add_circle_annot(rect)
    elif spec.type == T_LINE:
        annot = page.add_line_annot(pymupdf.Point(*spec.p1), pymupdf.Point(*spec.p2))
    elif spec.type == T_ARROW:
        annot = page.add_line_annot(pymupdf.Point(*spec.p1), pymupdf.Point(*spec.p2))
        annot.set_line_ends(_LINE_END_NONE, _LINE_END_CLOSED_ARROW)

    if annot is None:
        raise ValueError(f"标注创建失败：{spec.type}")

    _style(annot, spec, color, fill)
    annot.update()
    return spec.page


_FILL_TYPES = {T_RECT, T_CIRCLE, T_TEXT}
_BORDER_TYPES = {T_RECT, T_CIRCLE, T_LINE, T_ARROW, T_FREEHAND}


def _style(
    annot: pymupdf.Annot,
    spec: AnnotationSpec,
    color: Tuple[float, float, float],
    fill: Optional[Tuple[float, float, float]],
) -> None:
    try:
        if spec.type in _FILL_TYPES:
            annot.set_colors(stroke=color, fill=fill if fill is not None else color)
        else:
            annot.set_colors(stroke=color)
    except Exception:
        pass
    try:
        annot.set_opacity(max(0.05, min(1.0, spec.opacity)))
    except Exception:
        pass
    if spec.type in _BORDER_TYPES:
        try:
            annot.set_border(width=max(0.25, spec.line_width))
        except Exception:
            pass
    if spec.locked:
        try:
            annot.set_flags(pymupdf.PDF_ANNOT_IS_LOCKED)
        except Exception:
            pass


def list_annotations(
    doc: pymupdf.Document,
    page: Optional[int] = None,
    type_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """列出文档中的标注（含页码、类型、摘要）。"""
    out: List[Dict[str, Any]] = []
    pages = [page] if page is not None else range(doc.page_count)
    for pno in pages:
        if not 0 <= pno < doc.page_count:
            continue
        pg = doc.load_page(pno)
        for annot in pg.annots():
            t = _map_type(annot.type[0])
            if t is None:
                continue
            if type_filter and t != type_filter:
                continue
            out.append(
                {
                    "page": pno,
                    "xref": annot.xref,
                    "type": t,
                    "type_label": TYPE_LABELS.get(t, t),
                    "rect": tuple(annot.rect),
                    "opacity": annot.opacity,
                    "colors": annot.colors,
                    "text": _annot_text(annot),
                    "author": (annot.info or {}).get("title", ""),
                    "locked": bool(annot.flags & pymupdf.PDF_ANNOT_IS_LOCKED),
                }
            )
    return out


def _map_type(code: int) -> Optional[str]:
    return {
        pymupdf.PDF_ANNOT_HIGHLIGHT: T_HIGHLIGHT,
        pymupdf.PDF_ANNOT_UNDERLINE: T_UNDERLINE,
        pymupdf.PDF_ANNOT_STRIKE_OUT: T_STRIKEOUT,
        pymupdf.PDF_ANNOT_INK: T_FREEHAND,
        pymupdf.PDF_ANNOT_FREE_TEXT: T_TEXT,
        pymupdf.PDF_ANNOT_TEXT: T_NOTE,
        pymupdf.PDF_ANNOT_STAMP: T_STAMP,
        pymupdf.PDF_ANNOT_SQUARE: T_RECT,
        pymupdf.PDF_ANNOT_CIRCLE: T_CIRCLE,
        pymupdf.PDF_ANNOT_LINE: T_LINE,
    }.get(code)


def _annot_text(annot: pymupdf.Annot) -> str:
    try:
        info = annot.info or {}
        txt = info.get("content") or ""
        if not txt:
            txt = annot.get_text("text") or ""
        return txt.strip()
    except Exception:
        return ""


def update_annotation(
    doc: pymupdf.Document,
    page: int,
    xref: int,
    color: Optional[str] = None,
    fill_color: Optional[str] = None,
    opacity: Optional[float] = None,
    line_width: Optional[float] = None,
    rect: Optional[Tuple[float, float, float, float]] = None,
    text: Optional[str] = None,
    locked: Optional[bool] = None,
) -> bool:
    if not 0 <= page < doc.page_count:
        return False
    pg = doc.load_page(page)
    annot = pg.load_annot(xref)
    if annot is None:
        return False

    if color is not None:
        annot.set_colors(stroke=_rgb(color))
    if fill_color is not None:
        annot.set_colors(fill=_rgb(fill_color))
    if opacity is not None:
        annot.set_opacity(max(0.05, min(1.0, opacity)))
    if line_width is not None:
        annot.set_border(width=max(0.25, line_width))
    if rect is not None:
        annot.set_rect(pymupdf.Rect(*rect))
    if text is not None:
        annot.set_info(content=text)
    if locked is not None:
        annot.set_flags(pymupdf.PDF_ANNOT_IS_LOCKED if locked else 0)

    annot.update()
    return True


def delete_annotation(doc: pymupdf.Document, page: int, xref: int) -> bool:
    if not 0 <= page < doc.page_count:
        return False
    pg = doc.load_page(page)
    annot = pg.load_annot(xref)
    if annot is None:
        return False
    pg.delete_annot(annot)
    return True


def duplicate_annotation(
    doc: pymupdf.Document,
    page: int,
    xref: int,
    dx: float = 6.0,
    dy: float = -6.0,
) -> bool:
    if not 0 <= page < doc.page_count:
        return False
    pg = doc.load_page(page)
    annot = pg.load_annot(xref)
    if annot is None:
        return False
    r = annot.rect
    annot.set_rect(pymupdf.Rect(r.x0 + dx, r.y0 + dy, r.x1 + dx, r.y1 + dy))
    annot.update()
    return True


def flatten_annotations(
    doc: pymupdf.Document,
    pages: Optional[Sequence[int]] = None,
    include_widgets: bool = False,
) -> int:
    """把标注压平为页面内容（不可再编辑）。"""
    count = len(list_annotations(doc))
    doc.bake(annots=True, widgets=include_widgets)
    return count


def annotation_summary(item: Dict[str, Any]) -> str:
    t = item["type"]
    if t in (T_TEXT, T_NOTE):
        return (item.get("text") or "")[:40] or "(空)"
    if t == T_STAMP:
        return item.get("text") or "STAMP"
    if t == T_FREEHAND:
        return "手绘路径"
    r = item["rect"]
    return f"{r[0]:.0f},{r[1]:.0f} {r[2] - r[0]:.0f}×{r[3] - r[1]:.0f}"
