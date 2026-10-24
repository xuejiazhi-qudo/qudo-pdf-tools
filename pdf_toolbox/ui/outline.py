"""目录（书签/Outline）面板：有目录时用于跳转导航。"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..core.doc import PdfDoc


class OutlinePanel(QWidget):
    """显示 PDF 的书签目录树；点击条目跳转到对应页。"""

    gotoPage = Signal(int)          # 0 基页索引

    def __init__(self, doc: PdfDoc, parent=None) -> None:
        super().__init__(parent)
        self._doc = doc
        self._entries: List[List] = []
        self._suppress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setExpandsOnDoubleClick(True)
        self._tree.itemClicked.connect(self._on_click)
        layout.addWidget(self._tree, 1)

        self._empty = QLabel("该文档没有目录。\n已切换到按页浏览。")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.hide()
        layout.addWidget(self._empty)

        doc.structureChanged.connect(self.rebuild)

    # ---------------------------------------------------------------- 构建

    @property
    def has_outline(self) -> bool:
        return bool(self._entries)

    def rebuild(self) -> None:
        self._tree.clear()
        self._entries = []
        if not self._doc.is_open:
            self._empty.show()
            return

        try:
            with self._doc.lock:
                toc = self._doc.fitz_doc.get_toc(simple=False) or []
        except Exception:  # noqa: BLE001
            toc = []

        self._entries = toc
        if not toc:
            self._empty.show()
            self._tree.hide()
            return

        self._empty.hide()
        self._tree.show()

        stack: List[QTreeWidgetItem] = []
        for entry in toc:
            level = max(1, int(entry[0]))
            title = str(entry[1])
            page = int(entry[2])
            item = QTreeWidgetItem([f"{title}　·　第 {page} 页"])
            item.setData(0, Qt.UserRole, max(0, page - 1))
            item.setToolTip(0, title)

            while len(stack) > level - 1:
                stack.pop()
            if stack:
                stack[-1].addChild(item)
            else:
                self._tree.addTopLevelItem(item)
            stack.append(item)

        self._tree.expandToDepth(1)

    # ---------------------------------------------------------------- 交互

    def _on_click(self, item: QTreeWidgetItem, _column: int) -> None:
        page = item.data(0, Qt.UserRole)
        if page is not None:
            self.gotoPage.emit(int(page))

    def set_current(self, page: int) -> None:
        """高亮当前页所属的最深目录条目。"""
        if not self._entries:
            return
        target: Optional[QTreeWidgetItem] = None
        target_page = -1

        def walk(item: QTreeWidgetItem) -> None:
            nonlocal target, target_page
            p = item.data(0, Qt.UserRole)
            if p is not None and p <= page and p >= target_page:
                target_page = p
                target = item
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))

        if target is not None and not self._suppress:
            self._suppress = True
            self._tree.setCurrentItem(target)
            self._tree.scrollToItem(target)
            self._suppress = False
