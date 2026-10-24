"""PDF 查看器：连续垂直滚动 + 后台异步渲染 + 缩放/翻页。"""

from __future__ import annotations

import threading
from collections import deque
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QEvent, QPointF, Qt, QThread, Signal, QRectF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QKeyEvent,
    QPainter,
    QPen,
    QPixmap,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView

from ..core.doc import PdfDoc

PAGE_GAP = 18.0
SHADOW = QColor(0, 0, 0, 90)
PAGE_BG = QColor(255, 255, 255)
PLACEHOLDER = QColor(232, 234, 237)


class RenderThread(QThread):
    """后台渲染线程：消费 (index, zoom) 请求，产出 QImage。"""

    pageReady = Signal(int, float, QImage)

    def __init__(self, doc: PdfDoc, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._queue: deque = deque()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = False

    def request(self, index: int, zoom: float) -> None:
        with self._cond:
            # 同一页只保留最新请求
            self._queue = deque(
                [(i, z) for (i, z) in self._queue if i != index]
            )
            self._queue.append((index, zoom))
            self._cond.notify_all()

    def clear(self) -> None:
        with self._cond:
            self._queue.clear()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    def run(self) -> None:  # noqa: D102
        while True:
            with self._cond:
                while not self._queue and not self._stop:
                    self._cond.wait(0.2)
                if self._stop and not self._queue:
                    return
                if not self._queue:
                    continue
                index, zoom = self._queue.popleft()

            img = self._doc.render(index, zoom)
            if not img.isNull():
                self.pageReady.emit(index, zoom, img)


class PageItem(QGraphicsItem):
    """一页。场景单位 = PDF 点（zoom=1）。"""

    def __init__(self, index: int, width: float, height: float) -> None:
        super().__init__()
        self.index = index
        self._w = float(width)
        self._h = float(height)
        self._images: Dict[float, QImage] = {}
        self._requested: Optional[float] = None
        self.setCacheMode(QGraphicsItem.NoCache)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

    @property
    def width(self) -> float:
        return self._w

    @property
    def height(self) -> float:
        return self._h

    def boundingRect(self) -> QRectF:  # noqa: N802
        return QRectF(-6, -6, self._w + 12, self._h + 12)

    def set_size(self, width: float, height: float) -> None:
        self.prepareGeometryChange()
        self._w, self._h = float(width), float(height)
        self._images.clear()
        self.update()

    def set_image(self, zoom: float, image: QImage) -> None:
        self._images[round(zoom, 2)] = image
        self._requested = None
        self.update()

    def has_image(self, zoom: float) -> bool:
        return round(zoom, 2) in self._images

    def mark_requested(self, zoom: float) -> None:
        self._requested = round(zoom, 2)

    def needs_render(self, zoom: float) -> bool:
        z = round(zoom, 2)
        return z not in self._images and self._requested != z

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: D102
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # 阴影
        painter.setPen(Qt.NoPen)
        painter.setBrush(SHADOW)
        painter.drawRect(QRectF(2, 3, self._w, self._h))

        painter.setBrush(PAGE_BG)
        painter.setPen(QPen(QColor(160, 164, 170), 0))
        painter.drawRect(QRectF(0, 0, self._w, self._h))

        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        zoom = view.transform().m11() if view else 1.0
        dpr = view.devicePixelRatioF() if view else 1.0
        bucket = round(zoom * dpr, 2)

        img = self._images.get(bucket)
        if img is None:
            # 找一张相近缩放档的图先顶上；差距过大就显示占位块等新图，避免拉伸残影
            if self._images:
                best = min(self._images.keys(), key=lambda z: abs(z - bucket))
                if abs(best - bucket) <= bucket * 0.3:
                    img = self._images[best]
            if img is None:
                painter.setBrush(PLACEHOLDER)
                painter.drawRect(QRectF(0, 0, self._w, self._h))
                return

        painter.drawImage(QRectF(0, 0, self._w, self._h), img)


class PdfView(QGraphicsView):
    """连续滚动的 PDF 视图。"""

    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    pageClicked = Signal(int, QPointF)          # 页索引 + 页内坐标（点）
    pageDoubleClicked = Signal(int, QPointF)

    MIN_ZOOM = 0.1
    MAX_ZOOM = 8.0

    def __init__(self, doc: PdfDoc, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._items: list[PageItem] = []
        self._current = 0
        self._zoom = 1.0
        self._mode = None                      # 交互模式（标注/涂销/填写等）
        self._suppress_scroll_signal = False

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QBrush(QColor(82, 86, 89)))
        self.setFrameShape(QGraphicsView.NoFrame)

        self._render_thread = RenderThread(doc, self)
        self._render_thread.pageReady.connect(self._on_page_ready)
        self._render_thread.start()

        doc.structureChanged.connect(self.rebuild)
        doc.changed.connect(self._refresh_all)

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    # ---------------------------------------------------------------- 结构

    def rebuild(self) -> None:
        self._scene.clear()
        self._items = []
        self._render_thread.clear()

        y = 0.0
        for i in range(self._doc.page_count):
            rect = self._doc.page_rect(i)
            item = PageItem(i, rect.width, rect.height)
            item.setPos(-rect.width / 2, y)
            self._scene.addItem(item)
            self._items.append(item)
            y += rect.height + PAGE_GAP

        if self._items:
            widths = [it.width for it in self._items]
            self._scene.setSceneRect(-max(widths) / 2 - 60, -60,
                                     max(widths) + 120, y + 60)
        else:
            self._scene.setSceneRect(0, 0, 100, 100)

        self._current = 0
        self.currentPageChanged.emit(0)
        self._request_visible()

    def _refresh_all(self) -> None:
        sizes = self._doc.page_sizes()
        if len(sizes) != len(self._items):
            self.rebuild()
            return
        for item, (w, h) in zip(self._items, sizes):
            if abs(item.width - w) > 0.5 or abs(item.height - h) > 0.5:
                item.set_size(w, h)
            else:
                item._images.clear()
                item.update()
        self._request_visible()

    def close(self) -> None:
        self._render_thread.stop()
        self._render_thread.wait(2000)
        super().close()

    # ---------------------------------------------------------------- 渲染调度

    def _effective_zoom(self) -> float:
        return round(self.transform().m11() * self.devicePixelRatioF(), 2)

    def _request_visible(self) -> None:
        if not self._items:
            return
        zoom = self._effective_zoom()
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        for item in self._items:
            if not item.isVisible():
                continue
            br = item.mapToScene(item.boundingRect()).boundingRect()
            if br.intersects(rect) and item.needs_render(zoom):
                item.mark_requested(zoom)
                self._render_thread.request(item.index, zoom)

    def _on_page_ready(self, index: int, zoom: float, image: QImage) -> None:
        if 0 <= index < len(self._items):
            self._items[index].set_image(zoom, image)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802
        super().scrollContentsBy(dx, dy)
        self._request_visible()
        if not self._suppress_scroll_signal:
            self._update_current_page()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._request_visible()

    def _on_scroll(self, _value: int) -> None:
        self._update_current_page()

    def _update_current_page(self) -> None:
        if not self._items:
            return
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        mid = rect.center().y()
        best = 0
        best_dist = None
        for i, item in enumerate(self._items):
            cy = item.scenePos().y() + item.height / 2
            d = abs(cy - mid)
            if best_dist is None or d < best_dist:
                best_dist = d
                best = i
        if best != self._current:
            self._current = best
            self.currentPageChanged.emit(best)

    @property
    def current_page(self) -> int:
        return self._current

    def goto_page(self, index: int) -> None:
        if not 0 <= index < len(self._items):
            return
        item = self._items[index]
        self._suppress_scroll_signal = True
        self.centerOn(item.scenePos() + QPointF(item.width / 2, item.height / 2))
        self._suppress_scroll_signal = False
        self._current = index
        self.currentPageChanged.emit(index)
        self._request_visible()

    # ---------------------------------------------------------------- 缩放

    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, zoom: float) -> None:
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom))
        if abs(zoom - self._zoom) < 1e-6:
            return
        self._zoom = zoom
        self.setTransform(QTransform().scale(zoom, zoom))
        self.zoomChanged.emit(zoom)
        self._request_visible()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.2)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.2)

    def fit_width(self) -> None:
        if not self._items:
            return
        w = max(it.width for it in self._items)
        avail = self.viewport().width() - 24
        self.set_zoom(avail / w if w else 1.0)

    def fit_page(self) -> None:
        if not self._items:
            return
        item = self._items[min(self._current, len(self._items) - 1)]
        avail_w = self.viewport().width() - 24
        avail_h = self.viewport().height() - 24
        self.set_zoom(min(avail_w / item.width, avail_h / item.height))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            elif delta < 0:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    # ---------------------------------------------------------------- 交互模式

    def set_mode(self, mode) -> None:
        self._mode = mode
        if mode is not None:
            mode.attach(self)
        self.viewport().update()

    @property
    def mode(self):
        return self._mode

    def view_to_page_point(self, view_pos, ) -> Optional[Tuple[int, QPointF]]:
        """把视口坐标转成 (页索引, 页内点坐标)。"""
        scene_pos = self.mapToScene(view_pos)
        for item in self._items:
            local = item.mapFromScene(scene_pos)
            if QRectF(0, 0, item.width, item.height).contains(local):
                return item.index, QPointF(local)
        return None

    def page_item(self, index: int) -> Optional[PageItem]:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def scene_to_page(self, index: int, scene_pos: QPointF) -> QPointF:
        item = self.page_item(index)
        if item is None:
            return QPointF()
        return item.mapFromScene(scene_pos)

    def page_to_scene(self, index: int, page_pos: QPointF) -> QPointF:
        item = self.page_item(index)
        if item is None:
            return QPointF()
        return item.mapToScene(page_pos)

    def mousePressEvent(self, event):  # noqa: N802
        if self._mode is not None and self._mode.mouse_press(event):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._mode is not None and self._mode.mouse_move(event):
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        if self._mode is not None and self._mode.mouse_release(event):
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        hit = self.view_to_page_point(event.position().toPoint())
        if hit:
            self.pageDoubleClicked.emit(hit[0], hit[1])
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key_PageDown, Qt.Key_Space):
            self.goto_page(min(self._current + 1, len(self._items) - 1))
            event.accept()
            return
        if key == Qt.Key_PageUp:
            self.goto_page(max(self._current - 1, 0))
            event.accept()
            return
        if key == Qt.Key_Home:
            self.goto_page(0)
            event.accept()
            return
        if key == Qt.Key_End:
            self.goto_page(len(self._items) - 1)
            event.accept()
            return
        if self._mode is not None and self._mode.key_press(event):
            event.accept()
            return
        super().keyPressEvent(event)
