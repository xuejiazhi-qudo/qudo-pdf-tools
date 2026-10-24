"""交互模式用的临时覆盖图层元。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem


class DragRectItem(QGraphicsItem):
    """拖拽过程中的矩形预览。坐标为场景坐标。"""

    def __init__(self, color: QColor = QColor(255, 0, 0), fill: Optional[QColor] = None) -> None:
        super().__init__()
        self._rect = QRectF()
        self._color = color
        self._fill = fill
        self.setZValue(1000)

    def set_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._rect = QRectF(rect).normalized()
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        pen = QPen(self._color, 0)
        pen.setCosmetic(True)
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        painter.setPen(pen)
        if self._fill is not None:
            painter.setBrush(self._fill)
        else:
            painter.setBrush(Qt.NoBrush)
        painter.drawRect(self._rect)


class InkItem(QGraphicsItem):
    """手绘路径预览。points 为场景坐标。"""

    def __init__(self, color: QColor = QColor(255, 0, 0), width: float = 2.0) -> None:
        super().__init__()
        self._points: List[QPointF] = []
        self._color = color
        self._width = width
        self.setZValue(1000)

    def add_point(self, point: QPointF) -> None:
        self.prepareGeometryChange()
        self._points.append(QPointF(point))
        self.update()

    def points(self) -> List[QPointF]:
        return list(self._points)

    def boundingRect(self) -> QRectF:  # noqa: N802
        if not self._points:
            return QRectF()
        xs = [p.x() for p in self._points]
        ys = [p.y() for p in self._points]
        pad = self._width + 4
        return QRectF(min(xs) - pad, min(ys) - pad,
                      max(xs) - min(xs) + pad * 2, max(ys) - min(ys) + pad * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        if len(self._points) < 2:
            return
        pen = QPen(self._color, 0)
        pen.setCosmetic(True)
        pen.setWidthF(max(1.0, self._width))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(QPolygonF(self._points))


class ElementItem(QGraphicsItem):
    """插入文字/图片的浮动元素（应用进 PDF 之前可自由拖动）。"""

    def __init__(
        self,
        rect: QRectF,
        kind: str,
        on_changed=None,
        text: str = "",
        fontsize: float = 14.0,
        color: QColor = QColor(0, 0, 0),
        align: int = 0,
        pixmap: Optional[QPixmap] = None,
        family: str = "",
    ) -> None:
        super().__init__()
        self.kind = kind
        self.text = text
        self.fontsize = fontsize
        self.color = QColor(color)
        self.align = align
        self.pixmap = pixmap
        self.family = family
        self._on_changed = on_changed
        self.element = None
        # 不用 ItemIsMovable：我们的 PdfView 子类里 Qt 内建图元拖拽不生效，
        # 拖拽改由 EditContentMode 在 press/move/release 里手动 setPos 接管。
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setZValue(900)
        self._size = QRectF(0, 0, rect.width(), rect.height())
        self.setPos(rect.topLeft())

    def scene_rect(self) -> QRectF:
        return QRectF(self.pos().x(), self.pos().y(),
                      self._size.width(), self._size.height())

    HANDLE_SIZE = 8.0

    def _handle_size(self) -> float:
        """手柄保持约 8 屏幕像素：按视图缩放换算成场景单位。"""
        view = None
        if self.scene() is not None and self.scene().views():
            view = self.scene().views()[0]
        zoom = view.transform().m11() if view is not None else 1.0
        return self.HANDLE_SIZE / max(0.2, abs(zoom))

    def handle_rects(self) -> Dict[str, QRectF]:
        """8 个缩放手柄的场景坐标矩形（屏幕恒定大小）。"""
        r = self.scene_rect()
        hs = self._handle_size()
        cx = r.center().x()
        cy = r.center().y()
        pts = {
            "tl": (r.left(), r.top()), "t": (cx, r.top()), "tr": (r.right(), r.top()),
            "l": (r.left(), cy), "r": (r.right(), cy),
            "bl": (r.left(), r.bottom()), "b": (cx, r.bottom()), "br": (r.right(), r.bottom()),
        }
        return {k: QRectF(x - hs / 2, y - hs / 2, hs, hs) for k, (x, y) in pts.items()}

    def handle_at(self, scene_pos: QPointF, tol: float = 3.0) -> Optional[str]:
        for key, hr in self.handle_rects().items():
            if hr.adjusted(-tol, -tol, tol, tol).contains(scene_pos):
                return key
        return None

    def set_scene_rect(self, rect: QRectF) -> None:
        self.prepareGeometryChange()
        self._size = QRectF(0, 0, rect.width(), rect.height())
        self.setPos(rect.topLeft())
        self.update()

    def boundingRect(self) -> QRectF:  # noqa: N802
        return self._size.adjusted(-2, -2, 2, 2)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.ItemPositionHasChanged and self._on_changed is not None:
            self._on_changed(self)
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        painter.setRenderHint(QPainter.Antialiasing, True)
        local = QRectF(QPointF(0, 0), self._size.bottomRight())
        if self.kind == "image" and self.pixmap is not None:
            painter.drawPixmap(local, self.pixmap, QRectF(self.pixmap.rect()))
        elif self.kind == "text":
            from PySide6.QtGui import QFont

            # 白底避免与页面原有内容叠显造成视觉杂乱
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 240))
            painter.drawRect(local)
            painter.setBrush(Qt.NoBrush)

            font = QFont(self.family) if self.family else QFont(painter.font())
            font.setPixelSize(max(6, int(self.fontsize)))
            painter.setFont(font)
            painter.setPen(self.color)
            flags = int(Qt.AlignTop | Qt.TextWordWrap)
            flags |= {0: int(Qt.AlignLeft), 1: int(Qt.AlignHCenter), 2: int(Qt.AlignRight)}.get(
                self.align, int(Qt.AlignLeft)
            )
            painter.drawText(local, flags, self.text)

        pen = QPen(QColor(47, 111, 208), 0)
        pen.setCosmetic(True)
        pen.setWidth(1)
        pen.setStyle(Qt.SolidLine if self.isSelected() else Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(local)

        if self.isSelected():
            origin = self.scene_rect().topLeft()
            painter.setPen(QPen(QColor(47, 111, 208), 0))
            painter.setBrush(QColor(255, 255, 255))
            for hr in self.handle_rects().values():
                painter.drawRect(hr.translated(-origin))


def scene_rect_from(p1: QPointF, p2: QPointF) -> QRectF:
    return QRectF(p1, p2).normalized()
