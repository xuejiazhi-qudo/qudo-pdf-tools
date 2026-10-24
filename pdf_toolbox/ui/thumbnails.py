"""缩略图侧栏：懒加载渲染 + 多选 + 快捷选择。"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QThread, Qt, QSize, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core import pagerange
from ..core.doc import PdfDoc
from . import icons


class ThumbRenderThread(QThread):
    thumbReady = Signal(int, QImage)

    def __init__(self, doc: PdfDoc, size: int = 150, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._size = size
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # noqa: D102
        for i in range(self._doc.page_count):
            if self._stop:
                return
            img = self._doc.thumbnail(i, self._size)
            if not img.isNull():
                self.thumbReady.emit(i, img)


class ThumbnailPanel(QWidget):
    selectionChanged = Signal(list)      # 0 基页索引列表
    currentChanged = Signal(int)

    def __init__(self, doc: PdfDoc, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._thread: Optional[ThumbRenderThread] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        for text, slot, tip, icon_name in (
            ("全选", self.select_all, "选中所有页", "sel_all"),
            ("不选", self.select_none, "清空选择", "sel_none"),
            ("反选", self.invert, "反选", "sel_invert"),
            ("奇", self.select_odd, "只选奇数页", "odd"),
            ("偶", self.select_even, "只选偶数页", "even"),
        ):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setIcon(icons.icon(icon_name, 16))
            btn.setFixedHeight(26)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        layout.addLayout(bar)

        self._range = QLineEdit()
        self._range.setPlaceholderText("页码范围，如 1-3,5,8-")
        self._range.returnPressed.connect(self.apply_range)
        layout.addWidget(self._range)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setSpacing(4)
        self._list.setMovement(QListWidget.Static)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(QSize(152, 198))
        self._list.setIconSize(QSize(140, 190))
        self._list.itemSelectionChanged.connect(self._emit_selection)
        self._list.currentRowChanged.connect(self.currentChanged.emit)
        layout.addWidget(self._list, 1)

        doc.structureChanged.connect(self.rebuild)

    # ---------------------------------------------------------------- 构建

    def rebuild(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread.wait(1500)
        self._list.clear()
        for i in range(self._doc.page_count):
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, i)
            item.setToolTip(str(i + 1))
            self._list.addItem(item)

        self._thread = ThumbRenderThread(self._doc, 150, self)
        self._thread.thumbReady.connect(self._set_thumb)
        self._thread.start()

    def _set_thumb(self, index: int, image: QImage) -> None:
        if 0 <= index < self._list.count():
            from .widgets import thumb_icon

            self._list.item(index).setIcon(thumb_icon(image, 140, 190, badge=str(index + 1)))

    def close(self) -> None:
        if self._thread is not None:
            self._thread.stop()
            self._thread.wait(1500)

    # ---------------------------------------------------------------- 选择

    def _emit_selection(self) -> None:
        self.selectionChanged.emit(self.selected_pages())

    def selected_pages(self) -> List[int]:
        return sorted(
            self._list.item(self._list.row(i)).data(Qt.UserRole)
            for i in self._list.selectedItems()
        )

    def set_selected(self, pages: List[int]) -> None:
        wanted = set(pages)
        self._list.blockSignals(True)
        for r in range(self._list.count()):
            self._list.item(r).setSelected(self._list.item(r).data(Qt.UserRole) in wanted)
        self._list.blockSignals(False)
        self._emit_selection()

    def select_all(self) -> None:
        self.set_selected(list(range(self._doc.page_count)))

    def select_none(self) -> None:
        self.set_selected([])

    def invert(self) -> None:
        cur = set(self.selected_pages())
        self.set_selected([i for i in range(self._doc.page_count) if i not in cur])

    def select_odd(self) -> None:
        self.set_selected(list(range(0, self._doc.page_count, 2)))

    def select_even(self) -> None:
        self.set_selected(list(range(1, self._doc.page_count, 2)))

    def apply_range(self) -> None:
        try:
            pages = pagerange.parse(self._range.text(), self._doc.page_count)
        except pagerange.PageRangeError as exc:
            from . import i18n

            QMessageBox.warning(self, i18n.translate("页码范围无效"), str(exc))
            return
        self.set_selected(pages)

    def set_current(self, index: int) -> None:
        if 0 <= index < self._list.count():
            self._list.blockSignals(True)
            self._list.setCurrentRow(index)
            self._list.blockSignals(False)
