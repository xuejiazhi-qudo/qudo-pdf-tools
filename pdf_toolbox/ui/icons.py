"""运行时绘制的矢量小图标。

不依赖外部图片资源：用 QPainter 在 24×24 视图盒里画单色线条图形，
同时提供 1x/2x 两档像素图，打包进 exe 也不会缺资源。
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

INK = QColor(52, 58, 66)
VIEW = 24.0


def _new_painter(pm: QPixmap) -> QPainter:
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(pm.width() / VIEW, pm.height() / VIEW)
    pen = QPen(INK)
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    return p


def _line(p: QPainter, x1, y1, x2, y2) -> None:
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _poly(p: QPainter, pts, closed=False) -> None:
    poly = QPolygonF([QPointF(x, y) for x, y in pts])
    if closed:
        p.drawPolygon(poly)
    else:
        p.drawPolyline(poly)


def _rect(p: QPainter, x, y, w, h) -> None:
    p.drawRect(QRectF(x, y, w, h))


def _circle(p: QPainter, cx, cy, r) -> None:
    p.drawEllipse(QPointF(cx, cy), r, r)


def _arc(p: QPainter, x, y, w, h, a0, sweep) -> None:
    from PySide6.QtCore import QRectF as _R

    p.drawArc(_R(x, y, w, h), int(a0 * 16), int(sweep * 16))


# ---------------------------------------------------------------- 图形定义


def _open(p: QPainter) -> None:
    _poly(p, [(3, 7), (9, 7), (11, 9), (21, 9), (21, 19), (3, 19)], closed=True)
    _line(p, 3, 12, 21, 12)


def _save(p: QPainter) -> None:
    _poly(p, [(4, 4), (17, 4), (20, 7), (20, 20), (4, 20)], closed=True)
    _rect(p, 8, 4, 8, 5)
    _rect(p, 7, 13, 10, 7)


def _undo(p: QPainter) -> None:
    _poly(p, [(8, 5), (4, 9), (8, 13)])
    _line(p, 4, 9, 14, 9)
    _arc(p, 10, 9, 10, 10, -90, -180)


def _redo(p: QPainter) -> None:
    _poly(p, [(16, 5), (20, 9), (16, 13)])
    _line(p, 20, 9, 10, 9)
    _arc(p, 4, 9, 10, 10, -90, 180)


def _zoom_in(p: QPainter) -> None:
    _circle(p, 10, 10, 6)
    _line(p, 14.5, 14.5, 20, 20)
    _line(p, 7.5, 10, 12.5, 10)
    _line(p, 10, 7.5, 10, 12.5)


def _zoom_out(p: QPainter) -> None:
    _circle(p, 10, 10, 6)
    _line(p, 14.5, 14.5, 20, 20)
    _line(p, 7.5, 10, 12.5, 10)


def _fit_width(p: QPainter) -> None:
    _line(p, 3, 5, 3, 19)
    _line(p, 21, 5, 21, 19)
    _line(p, 5, 12, 19, 12)
    _poly(p, [(8, 9), (5, 12), (8, 15)])
    _poly(p, [(16, 9), (19, 12), (16, 15)])


def _fit_page(p: QPainter) -> None:
    _rect(p, 6, 4, 12, 16)
    _line(p, 3, 7, 3, 3)
    _line(p, 3, 3, 7, 3)
    _line(p, 21, 17, 21, 21)
    _line(p, 21, 21, 17, 21)


def _prev(p: QPainter) -> None:
    _poly(p, [(14, 5), (8, 12), (14, 19)])


def _next(p: QPainter) -> None:
    _poly(p, [(10, 5), (16, 12), (10, 19)])


def _annotate(p: QPainter) -> None:
    _poly(p, [(5, 19), (6, 15), (16, 5), (19, 8), (9, 18)], closed=True)
    _line(p, 4, 21, 12, 21)


def _redact(p: QPainter) -> None:
    p.setBrush(INK)
    _rect(p, 4, 9, 16, 7)
    p.setBrush(Qt.NoBrush)
    _line(p, 4, 5, 20, 5)
    _line(p, 4, 20, 20, 20)


def _edit_content(p: QPainter) -> None:
    _poly(p, [(4, 20), (5, 16), (15, 6), (18, 9), (8, 19)], closed=True)
    _line(p, 13, 8, 16, 11)
    _line(p, 12, 20, 21, 20)


def _fill_sign(p: QPainter) -> None:
    _poly(p, [(4, 16), (7, 11), (10, 15), (13, 9), (16, 14), (20, 8)])
    _line(p, 4, 20, 20, 20)


def _merge(p: QPainter) -> None:
    _rect(p, 4, 3, 7, 9)
    _rect(p, 13, 3, 7, 9)
    _poly(p, [(12, 14), (12, 18), (9, 18)])
    _line(p, 12, 14, 12, 20)
    _poly(p, [(9, 18), (12, 21), (15, 18)])


def _split(p: QPainter) -> None:
    _rect(p, 4, 4, 16, 16)
    p.setPen(_dashed(p))
    _line(p, 12, 4, 12, 20)
    p.setPen(_solid(p))
    _poly(p, [(8, 9), (5, 12), (8, 15)])
    _poly(p, [(16, 9), (19, 12), (16, 15)])


def _dashed(p: QPainter) -> QPen:
    pen = QPen(INK)
    pen.setWidthF(1.4)
    pen.setStyle(Qt.DashLine)
    return pen


def _solid(p: QPainter) -> QPen:
    pen = QPen(INK)
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _rotate(p: QPainter) -> None:
    _arc(p, 5, 5, 14, 14, 30, 300)
    _poly(p, [(19, 3), (21, 8), (16, 8)])


def _crop(p: QPainter) -> None:
    _poly(p, [(7, 3), (7, 17), (21, 17)])
    _poly(p, [(17, 21), (17, 7), (3, 7)])


def _compress(p: QPainter) -> None:
    _line(p, 4, 4, 20, 4)
    _line(p, 4, 20, 20, 20)
    _poly(p, [(9, 7), (12, 10), (15, 7)])
    _poly(p, [(9, 17), (12, 14), (15, 17)])


def _protect(p: QPainter) -> None:
    _rect(p, 5, 10, 14, 10)
    _arc(p, 8, 4, 8, 10, 0, 180)
    _circle(p, 12, 15, 1.6)


def _unlock(p: QPainter) -> None:
    _rect(p, 5, 10, 14, 10)
    _arc(p, 8, 2, 8, 10, 0, 180)
    _line(p, 8, 7, 8, 10)
    _circle(p, 12, 15, 1.6)


def _watermark(p: QPainter) -> None:
    _poly(p, [(12, 3), (18, 11), (12, 21), (6, 11)], closed=True)
    _line(p, 9, 12, 15, 12)


def _page_numbers(p: QPainter) -> None:
    _line(p, 9, 4, 7, 20)
    _line(p, 17, 4, 15, 20)
    _line(p, 4, 9, 20, 9)
    _line(p, 4, 15, 20, 15)


def _extract_text(p: QPainter) -> None:
    _line(p, 4, 6, 20, 6)
    _line(p, 4, 11, 20, 11)
    _line(p, 4, 16, 14, 16)
    _line(p, 4, 21, 10, 21)


def _extract_images(p: QPainter) -> None:
    _rect(p, 3, 5, 18, 14)
    _circle(p, 9, 10, 1.8)
    _poly(p, [(5, 17), (10, 12), (14, 16), (17, 13), (19, 17)])


def _metadata(p: QPainter) -> None:
    _poly(p, [(4, 4), (12, 4), (20, 12), (12, 20), (4, 12)], closed=True)
    _circle(p, 9, 9, 1.5)


def _word(p: QPainter) -> None:
    _poly(p, [(5, 3), (15, 3), (19, 7), (19, 21), (5, 21)], closed=True)
    _line(p, 15, 3, 15, 7)
    _line(p, 15, 7, 19, 7)
    _poly(p, [(8, 12), (9.5, 17), (11, 13), (12.5, 17), (14, 12)])


def _excel(p: QPainter) -> None:
    _rect(p, 4, 4, 16, 16)
    _line(p, 4, 10, 20, 10)
    _line(p, 4, 15, 20, 15)
    _line(p, 10, 4, 10, 20)


def _image_to_pdf(p: QPainter) -> None:
    _rect(p, 3, 4, 11, 9)
    _circle(p, 6.5, 7, 1.2)
    _poly(p, [(4, 12), (7, 9), (10, 12)])
    _poly(p, [(17, 8), (17, 16), (13, 16)])
    _line(p, 17, 8, 17, 18)
    _poly(p, [(14, 15), (17, 19), (20, 15)])


def _pdf_to_image(p: QPainter) -> None:
    _rect(p, 10, 4, 11, 9)
    _line(p, 12, 7, 19, 7)
    _line(p, 12, 10, 17, 10)
    _poly(p, [(7, 8), (7, 16), (3, 16)])
    _line(p, 7, 8, 7, 18)
    _rect(p, 3, 15, 11, 6)


def _organize(p: QPainter) -> None:
    _rect(p, 3, 4, 8, 7)
    _rect(p, 13, 4, 8, 7)
    _rect(p, 3, 13, 8, 7)
    p.setPen(_dashed(p))
    _rect(p, 13, 13, 8, 7)
    p.setPen(_solid(p))


def _outline(p: QPainter) -> None:
    _line(p, 4, 6, 6, 6)
    _line(p, 8, 6, 20, 6)
    _line(p, 8, 12, 20, 12)
    _line(p, 8, 18, 20, 18)
    _line(p, 4, 12, 6, 12)
    _line(p, 4, 18, 6, 18)


def _pages(p: QPainter) -> None:
    _rect(p, 7, 3, 13, 15)
    _poly(p, [(4, 6), (4, 21), (17, 21)])


def _sel_all(p: QPainter) -> None:
    _poly(p, [(7, 3), (20, 3), (20, 16)])
    _rect(p, 4, 7, 13, 13)
    _poly(p, [(7, 13), (10, 16), (15, 10)])


def _sel_none(p: QPainter) -> None:
    _rect(p, 4, 4, 16, 16)


def _sel_invert(p: QPainter) -> None:
    from PySide6.QtCore import QRectF

    _rect(p, 4, 4, 16, 16)
    p.save()
    p.setPen(Qt.NoPen)
    p.setBrush(INK)
    p.drawRect(QRectF(4.9, 4.9, 7, 14.2))
    p.restore()


def _digit(p: QPainter, text: str) -> None:
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont

    font = QFont(p.font())
    font.setPixelSize(15)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(2, 2, 20, 20), Qt.AlignCenter, text)


def _odd(p: QPainter) -> None:
    _digit(p, "1")


def _even(p: QPainter) -> None:
    _digit(p, "2")


def _new(p: QPainter) -> None:
    _poly(p, [(5, 3), (14, 3), (18, 7), (18, 21), (5, 21)], closed=True)
    _line(p, 14, 3, 14, 7)
    _line(p, 14, 7, 18, 7)
    _line(p, 8, 12, 14, 12)
    _line(p, 8, 16, 12, 16)


def _ins_text(p: QPainter) -> None:
    _line(p, 5, 5, 15, 5)
    _line(p, 10, 5, 10, 19)
    _line(p, 17, 14, 22, 14)
    _line(p, 19.5, 11.5, 19.5, 16.5)


def _ins_img(p: QPainter) -> None:
    _rect(p, 3, 4, 13, 11)
    _circle(p, 7, 8, 1.4)
    _poly(p, [(4, 13), (8, 9), (12, 13)])
    _line(p, 17, 16, 22, 16)
    _line(p, 19.5, 13.5, 19.5, 18.5)


def _img_swap(p: QPainter) -> None:
    _rect(p, 3, 6, 12, 10)
    _circle(p, 6.5, 9.5, 1.3)
    _poly(p, [(4, 14), (7.5, 10.5), (11, 14)])
    _arc(p, 14, 6, 8, 8, -60, 240)
    _poly(p, [(21, 4), (22.5, 8), (18.5, 7.5)])


def _img_del(p: QPainter) -> None:
    _rect(p, 3, 4, 13, 12)
    _circle(p, 7, 8, 1.4)
    _poly(p, [(4, 14), (8, 10), (12, 14)])
    _line(p, 17, 13, 22, 18)
    _line(p, 22, 13, 17, 18)


def _cursor(p: QPainter) -> None:
    _poly(p, [(6, 3), (6, 17), (10, 13.5), (12.5, 19), (15, 18), (12.5, 12.5), (17, 12)], closed=True)


GLYPHS: Dict[str, Callable[[QPainter], None]] = {
    "open": _open,
    "save": _save,
    "new": _new,
    "undo": _undo,
    "redo": _redo,
    "zoom_in": _zoom_in,
    "zoom_out": _zoom_out,
    "fit_width": _fit_width,
    "fit_page": _fit_page,
    "prev": _prev,
    "next": _next,
    "outline": _outline,
    "pages": _pages,
    "sel_all": _sel_all,
    "sel_none": _sel_none,
    "sel_invert": _sel_invert,
    "odd": _odd,
    "even": _even,
    "ins_text": _ins_text,
    "ins_img": _ins_img,
    "img_swap": _img_swap,
    "img_del": _img_del,
    "cursor": _cursor,
    # 工具（与 toolregistry 的 key 对应）
    "merge": _merge,
    "split": _split,
    "organize": _organize,
    "rotate": _rotate,
    "crop": _crop,
    "image_to_pdf": _image_to_pdf,
    "pdf_to_image": _pdf_to_image,
    "pdf_to_word": _word,
    "pdf_to_excel": _excel,
    "extract_text": _extract_text,
    "extract_images": _extract_images,
    "metadata": _metadata,
    "watermark": _watermark,
    "page_numbers": _page_numbers,
    "edit_content": _edit_content,
    "fill_sign": _fill_sign,
    "annotate": _annotate,
    "redact": _redact,
    "compress": _compress,
    "protect": _protect,
    "unlock": _unlock,
}

_cache: Dict[tuple, QIcon] = {}


def _render(name: str, px: int) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    draw = GLYPHS.get(name)
    if draw is None:
        return pm
    p = _new_painter(pm)
    draw(p)
    p.end()
    return pm


def icon(name: str, px: int = 20) -> QIcon:
    """取指定名字的图标；缺失名字返回空图标。"""
    key = (name, px)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    ic = QIcon()
    ic.addPixmap(_render(name, px))
    ic.addPixmap(_render(name, px * 2))
    _cache[key] = ic
    return ic
