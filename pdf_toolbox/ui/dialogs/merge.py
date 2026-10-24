"""PDF 合并。"""

from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ...core import pagerange
from ...core.doc import PdfDoc
from ...core.ops import pages
from ..theme import human_size
from ..widgets import OutputPathField, error, hbox, info, vbox
from .. import i18n
from .base import ToolDialog


class MergeDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 合并", 680, 620)
        self.set_run_text("合并")

        bar = QHBoxLayout()
        for text, slot in (
            ("添加文件…", self.add_files),
            ("移除", self.remove_selected),
            ("上移", lambda: self.move(-1)),
            ("下移", lambda: self.move(1)),
            ("清空", self.clear),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch(1)
        self.add_layout(bar)

        self._list = QListWidget()
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.itemDoubleClicked.connect(self.edit_range)
        self.add(self._list)

        tip = QLabel("拖拽可调整顺序；双击某一项可为该文件设置页码范围（默认全部页）。")
        tip.setWordWrap(True)
        self.add(tip)

        self._range_edit = QLineEdit()
        self._range_edit.setPlaceholderText("选中项的页码范围，如 1-3,5（留空=全部）")
        self._range_edit.editingFinished.connect(self.apply_range_to_selected)
        self.add(self._range_edit)

        self._out = OutputPathField("选择合并结果保存位置")
        self.add(QLabel("输出文件"))
        self.add(self._out)
        self.add_stretch()

    # ---------------------------------------------------------------- 列表

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要合并的 PDF", "", "PDF 文件 (*.pdf)"
        )
        for path in paths:
            try:
                import pymupdf

                with pymupdf.open(path) as d:
                    count = d.page_count
                    encrypted = d.needs_pass
            except Exception as exc:  # noqa: BLE001
                error(self, "无法读取", f"{path}\n{exc}")
                continue
            item = QListWidgetItem(f"{os.path.basename(path)}　{count} 页")
            item.setData(Qt.UserRole, {"path": path, "range": "", "encrypted": encrypted})
            item.setToolTip(path)
            self._list.addItem(item)
        self._refresh_summary()

    def remove_selected(self) -> None:
        for item in reversed(self._list.selectedItems()):
            self._list.takeItem(self._list.row(item))
        self._refresh_summary()

    def clear(self) -> None:
        self._list.clear()
        self._refresh_summary()

    def move(self, delta: int) -> None:
        row = self._list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self._list.count():
            return
        item = self._list.takeItem(row)
        self._list.insertItem(target, item)
        self._list.setCurrentRow(target)

    def edit_range(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        text, ok = QInputDialog.getText(
            self, i18n.translate("页码范围"),
            i18n.translate(f"《{os.path.basename(data['path'])}》要合并的页码（留空=全部）："),
            text=data.get("range", ""),
        )
        if ok:
            data["range"] = text.strip()
            item.setData(Qt.UserRole, data)
            self._refresh_item(item)

    def apply_range_to_selected(self) -> None:
        items = self._list.selectedItems()
        if len(items) == 1:
            data = items[0].data(Qt.UserRole)
            data["range"] = self._range_edit.text().strip()
            items[0].setData(Qt.UserRole, data)
            self._refresh_item(items[0])

    def _refresh_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        import pymupdf

        with pymupdf.open(data["path"]) as d:
            count = d.page_count
        suffix = f"　页码 {data['range']}" if data.get("range") else f"　{count} 页"
        item.setText(f"{os.path.basename(data['path'])}{suffix}")

    def _refresh_summary(self) -> None:
        total = 0
        for r in range(self._list.count()):
            data = self._list.item(r).data(Qt.UserRole)
            try:
                import pymupdf

                with pymupdf.open(data["path"]) as d:
                    if data.get("range"):
                        total += len(pagerange.parse(data["range"], d.page_count))
                    else:
                        total += d.page_count
            except Exception:  # noqa: BLE001
                pass
        self.set_status(f"共 {self._list.count()} 个文件，合并后约 {total} 页")

    # ---------------------------------------------------------------- 执行

    def on_run(self) -> None:
        if self._list.count() < 2:
            error(self, "文件不足", "至少需要两个 PDF 才能合并。")
            return

        inputs: List[pages.MergeInput] = []
        for r in range(self._list.count()):
            data = self._list.item(r).data(Qt.UserRole)
            pages_list: List[int] = []
            if data.get("range"):
                import pymupdf

                with pymupdf.open(data["path"]) as d:
                    try:
                        pages_list = pagerange.parse(data["range"], d.page_count)
                    except pagerange.PageRangeError as exc:
                        error(self, "页码范围无效", str(exc))
                        return
            password = None
            if data.get("encrypted"):
                password, ok = QInputDialog.getText(
                    self, i18n.translate("需要密码"),
                    i18n.translate(f"《{os.path.basename(data['path'])}》的打开密码："),
                    echo=QInputDialog.Password,
                )
                if not ok:
                    return
            inputs.append(pages.MergeInput(path=data["path"], password=password, pages=pages_list))

        out = self._out.text()
        if not out:
            out = QFileDialog.getSaveFileName(self, "保存合并结果", "merged.pdf", "PDF (*.pdf)")[0]
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        def _done(path: str) -> None:
            size = os.path.getsize(path)
            info(self, "合并完成", f"已保存到：\n{path}\n大小 {human_size(size)}")

        self.run("合并 PDF", pages.merge_pdfs, inputs, out, on_done=_done)


def create(parent, doc: PdfDoc) -> MergeDialog:
    return MergeDialog(parent, doc)
