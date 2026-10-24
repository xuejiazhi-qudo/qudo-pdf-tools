"""内容编辑引擎：修改现有文字、删除区域、替换/删除图片。

PDF 的内容流不是结构化文档，"改字"的标准做法是：
先把原文字区域涂销删除，再在同一位置按原字号/颜色插入新文字。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from .stamp import _font_for

# 可选字体：(key, 显示名, pymupdf fontname, fontfile, Qt 预览族名)
FONT_CHOICES = [
    ("helv", "Helvetica", "helv", None, "Helvetica"),
    ("times", "Times Roman", "tiro", None, "Times New Roman"),
    ("courier", "Courier", "cour", None, "Courier New"),
    ("cjk", "内置中文黑体", "china-s", None, "SimHei"),
    ("yahei", "微软雅黑", None, "C:/Windows/Fonts/msyh.ttc", "Microsoft YaHei"),
    ("simsun", "宋体", None, "C:/Windows/Fonts/simsun.ttc", "SimSun"),
    ("simkai", "楷体", None, "C:/Windows/Fonts/simkai.ttf", "KaiTi"),
    ("simhei", "黑体", None, "C:/Windows/Fonts/simhei.ttf", "SimHei"),
]


def resolve_font(key: str) -> Tuple[Optional[str], Optional[str], str]:
    """返回 (fontname, fontfile, qt_family)；字体文件缺失时回退内置中文黑体。

    注意：fontname 与 fontfile 同时给出时 PyMuPDF 优先 fontname，
    所以使用系统字体文件时必须把 fontname 置为 None。
    """
    import os

    for k, _label, fontname, fontfile, family in FONT_CHOICES:
        if k != key:
            continue
        if fontfile and not os.path.exists(fontfile):
            return "china-s", None, "SimHei"
        if fontfile:
            # fontname 作为 PDF 内字体资源名，不能为 None 也不能撞 base14
            return f"F-{key}", fontfile, family
        return fontname or "china-s", None, family
    return "china-s", None, "SimHei"


@dataclass
class TextLine:
    """点击命中的一行文字及其原始样式。"""

    rect: Tuple[float, float, float, float]
    text: str
    size: float
    color: Tuple[float, float, float]
    font: str
    spans: List[Dict]


@dataclass
class ImageHit:
    xref: int
    rect: Tuple[float, float, float, float]
    width: int
    height: int


def _rgb01(color_int: int) -> Tuple[float, float, float]:
    r = (color_int >> 16) & 255
    g = (color_int >> 8) & 255
    b = color_int & 255
    return (r / 255.0, g / 255.0, b / 255.0)


def find_text_lines_in(page: pymupdf.Page, rect: pymupdf.Rect) -> List[TextLine]:
    """返回与矩形相交的所有文字行，按阅读顺序。"""
    target = pymupdf.Rect(rect)
    data = page.get_text("dict")
    out: List[TextLine] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox")
            if not bbox:
                continue
            lr = pymupdf.Rect(bbox)
            if not lr.intersects(target):
                continue
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            out.append(
                TextLine(
                    rect=(lr.x0, lr.y0, lr.x1, lr.y1),
                    text=text,
                    size=max(float(s.get("size", 11)) for s in spans),
                    color=_rgb01(int(spans[0].get("color", 0))),
                    font=str(spans[0].get("font", "helv")),
                    spans=spans,
                )
            )
    out.sort(key=lambda t: (round(t.rect[1], 1), t.rect[0]))
    return out


def find_text_line(page: pymupdf.Page, point: pymupdf.Point) -> Optional[TextLine]:
    """找到包含该点的所有文字行（优先最小包围行）。"""
    data = page.get_text("dict")
    hits: List[TextLine] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            bbox = line.get("bbox")
            if not bbox:
                continue
            rect = pymupdf.Rect(bbox)
            if not rect.contains(point):
                continue
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans)
            if not text.strip():
                continue
            size = max(float(s.get("size", 11)) for s in spans)
            color = _rgb01(int(spans[0].get("color", 0)))
            font = str(spans[0].get("font", "helv"))
            hits.append(
                TextLine(
                    rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    text=text,
                    size=size,
                    color=color,
                    font=font,
                    spans=spans,
                )
            )
    if not hits:
        return None
    # 取面积最小的行（最精确）
    return min(hits, key=lambda t: (t.rect[2] - t.rect[0]) * (t.rect[3] - t.rect[1]))


def replace_text(
    page: pymupdf.Page,
    line: TextLine,
    new_text: str,
) -> None:
    """删除原文字行并在原位置写入新文字（保留字号与颜色）。"""
    rect = pymupdf.Rect(*line.rect)
    # 略微外扩，确保覆盖字形边缘
    rect = pymupdf.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1)

    page.add_redact_annot(rect, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=0,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )

    size = line.size
    # 保持原字号：框自动向下扩展容纳更多文字；只有扩到页底仍放不下才缩字号
    rc, _used = insert_text_box(
        page, rect, new_text, fontsize=size, color=line.color, align=0, auto_expand=True
    )
    if rc >= 0:
        return
    for _ in range(10):
        size = max(4.0, size * 0.9)
        rc, _used = insert_text_box(
            page, rect, new_text, fontsize=size, color=line.color, align=0, auto_expand=True
        )
        if rc >= 0:
            return


def remove_region(page: pymupdf.Page, rect: pymupdf.Rect) -> None:
    """删除矩形区域内的文字与矢量图形（不动图片像素）。"""
    page.add_redact_annot(rect, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=1,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )


def find_image_at(page: pymupdf.Page, point: pymupdf.Point) -> Optional[ImageHit]:
    """找到包含该点的内嵌图片。"""
    try:
        infos = page.get_image_info(xrefs=True) or []
    except Exception:  # noqa: BLE001
        return None
    hits = []
    for info in infos:
        bbox = info.get("bbox")
        xref = info.get("xref") or 0
        if not bbox or xref <= 0:
            continue
        rect = pymupdf.Rect(bbox)
        if rect.contains(point):
            hits.append(
                ImageHit(
                    xref=xref,
                    rect=(rect.x0, rect.y0, rect.x1, rect.y1),
                    width=int(info.get("width", 0)),
                    height=int(info.get("height", 0)),
                )
            )
    if not hits:
        return None
    return min(hits, key=lambda h: (h.rect[2] - h.rect[0]) * (h.rect[3] - h.rect[1]))


def replace_image(page: pymupdf.Page, xref: int, path: str) -> None:
    """用新图片替换指定 xref 的图片（保持原位置与尺寸）。

    实现为「涂销移除旧图 + 原位插入新图」：PyMuPDF 的 replace_image 会新建
    xref 且旧对象仍挂在资源表上，导致旧图字节残留在文件里。
    """
    bbox = None
    try:
        for info in page.get_image_info(xrefs=True) or []:
            if info.get("xref") == xref:
                bbox = pymupdf.Rect(info["bbox"])
                break
    except Exception:  # noqa: BLE001
        bbox = None

    if bbox is None:
        page.replace_image(xref, filename=path)
        return

    page.add_redact_annot(bbox, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
        graphics=0,
        text=pymupdf.PDF_REDACT_TEXT_NONE,
    )
    page.insert_image(bbox, filename=path)


def move_text_lines(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    dx: float,
    dy: float,
) -> int:
    """把矩形内的文字行整体平移 (dx, dy)，返回移动的行数。"""
    lines = find_text_lines_in(page, rect)
    if not lines:
        return 0

    page.add_redact_annot(rect, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=0,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE,
    )

    for ln in lines:
        font = _font_for(ln.text, "helv")
        base = pymupdf.Point(ln.rect[0] + dx, ln.rect[1] + dy + ln.size * 0.8)
        page.insert_text(
            base,
            ln.text,
            fontsize=ln.size,
            fontname=font,
            color=ln.color,
        )
    return len(lines)


def move_image(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    xref: int,
    dx: float,
    dy: float,
) -> bool:
    """把指定 xref 的图片整体平移 (dx, dy)。"""
    bbox = None
    for info in page.get_image_info(xrefs=True) or []:
        if info.get("xref") == xref:
            bbox = pymupdf.Rect(info["bbox"])
            break
    if bbox is None:
        return False

    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.colorspace and pix.colorspace.n == 4:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        data = pix.tobytes("png")
    except Exception:  # noqa: BLE001
        data = (doc.extract_image(xref) or {}).get("image")
    if not data:
        return False

    page.add_redact_annot(bbox, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
        graphics=0,
        text=pymupdf.PDF_REDACT_TEXT_NONE,
    )
    moved = pymupdf.Rect(bbox.x0 + dx, bbox.y0 + dy, bbox.x1 + dx, bbox.y1 + dy)
    page.insert_image(moved, stream=data)
    return True


def _trial_rc(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    kwargs: Dict,
) -> float:
    """在一次性临时页上试排测量剩余空间。

    render_mode=3 只是"不描边不填充"，文字仍会写进内容流并被提取，
    所以测量必须在临时文档里做，不能污染目标页。
    """
    tmp = pymupdf.open()
    try:
        tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
        return float(tp.insert_textbox(rect, text, render_mode=3, **kwargs))
    finally:
        tmp.close()


def _measure_width(text: str, fontsize: float, fontname: str, fontfile: Optional[str]) -> float:
    """用 Font 对象度量文本宽度（get_text_length 在 2.0 不支持 fontfile）。"""
    try:
        font = pymupdf.Font(fontfile=fontfile) if fontfile else pymupdf.Font(fontname=fontname)
        return float(font.text_length(text, fontsize=fontsize))
    except Exception:  # noqa: BLE001
        return len(text) * fontsize * 0.6


def fit_text_rect(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    fontsize: float,
    font_key: str = "auto",
) -> pymupdf.Rect:
    """把文本框收紧到文字实际占用尺寸：宽=min(拖拽宽, 最长行宽)，高=换行后实际用量。"""
    if font_key == "auto":
        fontname, fontfile = _font_for(text, "helv"), None
    else:
        fontname, fontfile, _fam = resolve_font(font_key)

    lines = text.split("\n") or [""]
    single = max(
        _measure_width(line, fontsize, fontname, fontfile) for line in lines
    )
    width = max(20.0, min(rect.width, single + 4))

    probe = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + width, page.rect.height - 2)
    rc = _trial_rc(
        page, probe, text,
        dict(fontsize=fontsize, fontname=fontname, fontfile=fontfile),
    )
    if rc >= 0:
        height = max(fontsize * 1.2, probe.height - rc + 4)
    else:
        height = rect.height
    return pymupdf.Rect(rect.x0, rect.y0, rect.x0 + width, rect.y0 + height)


def insert_text_box(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    text: str,
    fontsize: float = 12.0,
    color: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    align: int = 0,
    opacity: float = 1.0,
    auto_expand: bool = True,
    font_key: str = "auto",
) -> Tuple[float, pymupdf.Rect]:
    """在矩形内插入多行文字，返回 (剩余空间, 实际使用的矩形)。

    先用 render_mode=3 试排测量；放不下且 auto_expand 时自动向下扩框
    （不超过页面底边），避免用户框选稍小就丢字。剩余空间为负=仍放不下。
    """
    if font_key == "auto":
        fontname, fontfile = _font_for(text, "helv"), None
    else:
        fontname, fontfile, _fam = resolve_font(font_key)
    kwargs = dict(
        fontsize=fontsize,
        fontname=fontname,
        fontfile=fontfile,
        color=color,
        align=align,
        stroke_opacity=opacity,
        fill_opacity=opacity,
    )

    used = pymupdf.Rect(rect)
    rc = _trial_rc(page, used, text, kwargs)
    if rc < 0 and auto_expand:
        grown = pymupdf.Rect(
            used.x0, used.y0, used.x1,
            min(page.rect.height - 2, used.y1 + (-rc) + fontsize),
        )
        rc2 = _trial_rc(page, grown, text, kwargs)
        if rc2 >= 0 or rc2 > rc:
            used, rc = grown, rc2

    rc = page.insert_textbox(used, text, **kwargs)
    return rc, used


def insert_image_rect(
    page: pymupdf.Page,
    rect: pymupdf.Rect,
    path: Optional[str] = None,
    stream: Optional[bytes] = None,
    keep_aspect: bool = True,
) -> None:
    """按矩形插入图片；keep_aspect 为真时等比缩放居中。"""
    if path is not None:
        page.insert_image(rect, filename=path, keep_proportion=keep_aspect)
    elif stream is not None:
        page.insert_image(rect, stream=stream, keep_proportion=keep_aspect)
    else:
        raise ValueError("insert_image_rect 需要 path 或 stream")


def delete_image(page: pymupdf.Page, xref: int) -> None:
    """真正删除图片：用涂销移除图像对象，而不是留占位图。"""
    bbox = None
    try:
        for info in page.get_image_info(xrefs=True) or []:
            if info.get("xref") == xref:
                bbox = pymupdf.Rect(info["bbox"])
                break
    except Exception:  # noqa: BLE001
        bbox = None
    if bbox is None:
        page.delete_image(xref)
        return
    page.add_redact_annot(bbox, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
        graphics=0,
        text=pymupdf.PDF_REDACT_TEXT_NONE,
    )
