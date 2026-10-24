"""PDF 页面整理：拖拽排序、旋转、复制、删除、插入空白页/外部页、提取。"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

import pymupdf
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
)

from ...core.doc import PdfDoc
from ..theme import human_size
from .. import i18n
from ..widgets import error, info, warn
from .base import ToolDialog

BLANK_SIZES = {
    "a4": (595.28, 841.89),
    "letter": (612.0, 792.0),
}


class OrganizeDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 页面整理", 860, 700)
        self.set_run_text("应用整理")
        self._entries: List[Dict] = []

        bar = QHBoxLayout()
        for text, slot in (
            ("左转", lambda: self.rotate_sel(-90)),
            ("右转", lambda: self.rotate_sel(90)),
            ("复制", self.duplicate_sel),
            ("删除", self.delete_sel),
            ("移到首", lambda: self.move_sel("first")),
            ("移到尾", lambda: self.move_sel("last")),
            ("前移", lambda: self.move_sel("back")),
            ("后移", lambda: self.move_sel("forward")),
            ("插入空白页", self.insert_blank),
            ("从文件插入…", self.insert_from_file),
            ("提取选中…", self.extract_sel),
            ("重置", self.rebuild),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch(1)
        self.add_layout(bar)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setSpacing(4)
        self._list.setMovement(QListWidget.Snap)
        self._list.setDragDropMode(QAbstractItemView.InternalMove)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(QSize(132, 180))
        self._list.setIconSize(QSize(120, 160))
        self.add(self._list, 1)

        warn_label = QLabel(
            "注意：应用整理会重建文档，数字签名将失效，书签/目录、内部链接与表单字段可能丢失。"
        )
        warn_label.setWordWrap(True)
        warn_label.setStyleSheet("color:#b3372f;")
        self.add(warn_label)

        self._status_label = QLabel("")
        self.add(self._status_label)

        self.rebuild()

    # ---------------------------------------------------------------- 模型

    def rebuild(self) -> None:
        self._entries = [
            {"kind": "page", "src": i, "rot": 0} for i in range(self.doc.page_count)
        ]
        self._reload_list()

    def _read_order(self) -> None:
        self._entries = [
            self._list.item(r).data(Qt.UserRole) for r in range(self._list.count())
        ]

    def _reload_list(self) -> None:
        self._list.clear()
        for idx, entry in enumerate(self._entries):
            item = QListWidgetItem(self._label(entry, idx))
            item.setIcon(self._icon(entry))
            item.setData(Qt.UserRole, entry)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._list.addItem(item)
        self._refresh_status()

    def _label(self, entry: Dict, idx: int) -> str:
        base = str(idx + 1)
        if entry.get("rot"):
            base += f"　{entry['rot']}°"
        if entry["kind"] == "blank":
            base += "　空白"
        elif entry["kind"] == "file":
            base += f"　{os.path.basename(entry['path'])}"
        return base

    def _icon(self, entry: Dict) -> QIcon:
        from ..widgets import thumb_icon

        pix = None
        try:
            if entry["kind"] == "page":
                pix = self._render(self.doc.fitz_doc, entry["src"], entry.get("rot", 0))
            elif entry["kind"] == "blank":
                img = QImage(120, 160, QImage.Format_RGB888)
                img.fill(Qt.white)
                return thumb_icon(img, 120, 160)
            else:
                with pymupdf.open(entry["path"]) as d:
                    pix = self._render(d, entry["page"], entry.get("rot", 0))
        except Exception:  # noqa: BLE001
            pass
        if pix is None:
            img = QImage(120, 160, QImage.Format_RGB888)
            img.fill(Qt.lightGray)
            return thumb_icon(img, 120, 160)
        return thumb_icon(pix, 120, 160)

    @staticmethod
    def _render(doc: pymupdf.Document, index: int, rot: int) -> QImage:
        page = doc.load_page(index)
        matrix = pymupdf.Matrix(0.35, 0.35)
        if rot:
            matrix = matrix.prerotate(rot)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return QImage(pix.samples, pix.width, pix.height, pix.stride,
                      QImage.Format_RGB888).copy()

    def _refresh_status(self) -> None:
        self._status_label.setText(i18n.translate(
            f"共 {self._list.count()} 页（原文档 {self.doc.page_count} 页）"
        ))

    # ---------------------------------------------------------------- 操作

    def _selected_rows(self) -> List[int]:
        return sorted(self._list.row(i) for i in self._list.selectedItems())

    def rotate_sel(self, delta: int) -> None:
        self._read_order()
        for row in self._selected_rows():
            entry = self._list.item(row).data(Qt.UserRole)
            entry["rot"] = (entry.get("rot", 0) + delta) % 360
            self._list.item(row).setData(Qt.UserRole, entry)
            self._list.item(row).setIcon(self._icon(entry))
            self._list.item(row).setText(self._label(entry, row))
        self._read_order()

    def duplicate_sel(self) -> None:
        self._read_order()
        rows = self._selected_rows()
        inserts = []
        for row in rows:
            entry = dict(self._entries[row])
            inserts.append((row + 1, entry))
        for offset, (row, entry) in enumerate(inserts):
            self._entries.insert(row + offset, entry)
        self._reload_list()

    def delete_sel(self) -> None:
        rows = self._selected_rows()
        if len(rows) == self._list.count():
            warn(self, "不能删除全部", "至少保留一页。")
            return
        for row in reversed(rows):
            self._list.takeItem(row)
        self._read_order()
        self._reload_list()

    def move_sel(self, where: str) -> None:
        self._read_order()
        rows = self._selected_rows()
        if not rows:
            return
        moving = [self._entries[r] for r in rows]
        rest = [e for i, e in enumerate(self._entries) if i not in set(rows)]
        if where == "first":
            self._entries = moving + rest
        elif where == "last":
            self._entries = rest + moving
        elif where == "back":
            first = rows[0]
            rest_first = first - len([r for r in rows if r < first])
            self._entries = rest[:rest_first] + moving + rest[rest_first:]
        else:  # forward
            last = rows[-1]
            count_before = len([r for r in rows if r <= last])
            pos = last - count_before + 1
            pos = min(pos, len(rest))
            self._entries = rest[:pos] + moving + rest[pos:]
        self._reload_list()

    def insert_blank(self) -> None:
        dlg = _BlankPageDialog(self, self.doc)
        if dlg.exec() != _BlankPageDialog.Accepted:
            return
        w, h, pos = dlg.result()
        entry = {"kind": "blank", "w": w, "h": h, "rot": 0}
        rows = self._selected_rows()
        self._read_order()
        if pos == "start":
            self._entries.insert(0, entry)
        elif pos == "end":
            self._entries.append(entry)
        elif pos == "before" and rows:
            self._entries.insert(rows[0], entry)
        elif pos == "after" and rows:
            self._entries.insert(rows[-1] + 1, entry)
        else:
            self._entries.append(entry)
        self._reload_list()

    def insert_from_file(self) -> None:
        path = QFileDialog.getOpenFileName(self, "选择要插入的 PDF", "", "PDF (*.pdf)")[0]
        if not path:
            return
        from ..widgets import PagePickDialog

        pick = PagePickDialog(path, self, "选择要插入的页面")
        if pick.exec() != PagePickDialog.Accepted or not pick.selected:
            return
        rows = self._selected_rows()
        self._read_order()
        new_entries = [{"kind": "file", "path": path, "page": p, "rot": 0} for p in pick.selected]
        at = rows[-1] + 1 if rows else len(self._entries)
        self._entries[at:at] = new_entries
        self._reload_list()

    def extract_sel(self) -> None:
        self._read_order()
        rows = self._selected_rows()
        if not rows:
            warn(self, "未选择页面", "请先选择要提取的页面。")
            return
        out = QFileDialog.getSaveFileName(self, "保存提取结果", "extracted.pdf", "PDF (*.pdf)")[0]
        if not out:
            return

        built = pymupdf.open()
        try:
            src_bytes = self.doc.save_bytes(garbage=0, deflate=0)
            with pymupdf.open(stream=src_bytes, filetype="pdf") as src:
                for row in rows:
                    entry = self._entries[row]
                    if entry["kind"] != "page":
                        continue
                    built.insert_pdf(src, from_page=entry["src"], to_page=entry["src"])
                    if entry.get("rot"):
                        built.load_page(built.page_count - 1).set_rotation(
                            (src.load_page(entry["src"]).rotation + entry["rot"]) % 360
                        )
            if built.page_count == 0:
                warn(self, "没有可提取的页面", "选中的都是空白页或外部页，暂不支持提取。")
                return
            built.save(out, garbage=4, deflate=1, use_objstms=1)
        finally:
            built.close()
        info(self, "提取完成", f"{out}\n{human_size(os.path.getsize(out))}")

    # ---------------------------------------------------------------- 应用

    def on_run(self) -> None:
        self._read_order()
        if not self._entries:
            warn(self, "没有页面", "至少保留一页。")
            return

        self.doc.snapshot()
        src_bytes = self.doc.save_bytes(garbage=0, deflate=0)

        out = pymupdf.open()
        try:
            with pymupdf.open(stream=src_bytes, filetype="pdf") as src:
                externals: Dict[str, pymupdf.Document] = {}
                for entry in self._entries:
                    if entry["kind"] == "page":
                        out.insert_pdf(src, from_page=entry["src"], to_page=entry["src"])
                        if entry.get("rot"):
                            out.load_page(out.page_count - 1).set_rotation(
                                (src.load_page(entry["src"]).rotation + entry["rot"]) % 360
                            )
                    elif entry["kind"] == "blank":
                        out.new_page(width=entry["w"], height=entry["h"])
                    else:
                        ext = externals.get(entry["path"])
                        if ext is None:
                            ext = pymupdf.open(entry["path"])
                            externals[entry["path"]] = ext
                        out.insert_pdf(ext, from_page=entry["page"], to_page=entry["page"])
                        if entry.get("rot"):
                            out.load_page(out.page_count - 1).set_rotation(
                                (ext.load_page(entry["page"]).rotation + entry["rot"]) % 360
                            )
                for d in externals.values():
                    d.close()

            data = out.tobytes(garbage=4, deflate=1, use_objstms=1)
        finally:
            out.close()

        self.doc.load_bytes_keep_path(data)
        self.rebuild()
        info(self, "整理完成", f"现在共 {self.doc.page_count} 页。记得保存。")


class _BlankPageDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "插入空白页", 420, 380)
        self.set_run_text("插入")
        group = QGroupBox("空白页设置")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._size = QComboBox()
        self._size.addItems(["a4", "letter", "same", "custom"])
        self._size.currentTextChanged.connect(self._sync)
        layout.addRow("尺寸", self._size)

        self._w = QDoubleSpinBox()
        self._w.setRange(10, 5000)
        self._w.setValue(210)
        layout.addRow("宽", self._w)
        self._h = QDoubleSpinBox()
        self._h.setRange(10, 5000)
        self._h.setValue(297)
        layout.addRow("高", self._h)

        self._unit = QComboBox()
        self._unit.addItems(["mm", "in", "pt"])
        layout.addRow("单位", self._unit)

        self._orient = QComboBox()
        self._orient.addItems(["portrait", "landscape"])
        layout.addRow("方向", self._orient)

        self._pos = QComboBox()
        for key, label in (
            ("end", "文档末尾"),
            ("start", "文档开头"),
            ("before", "选中页之前"),
            ("after", "选中页之后"),
        ):
            self._pos.addItem(label, key)
        layout.addRow("位置", self._pos)
        self.add(group)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        custom = self._size.currentText() == "custom"
        self._w.setVisible(custom)
        self._h.setVisible(custom)
        self._unit.setVisible(custom)

    def result(self):
        unit = self._unit.currentText()
        factor = {"mm": 72 / 25.4, "in": 72.0, "pt": 1.0}[unit]
        key = self._size.currentText()
        if key == "same":
            idx = self.parent().view.current_page if hasattr(self.parent(), "view") else 0
            rect = self.doc.page_rect(min(idx, self.doc.page_count - 1))
            w, h = rect.width, rect.height
        elif key in BLANK_SIZES:
            w, h = BLANK_SIZES[key]
        else:
            w, h = self._w.value() * factor, self._h.value() * factor
        if self._orient.currentText() == "landscape":
            w, h = max(w, h), min(w, h)
        else:
            w, h = min(w, h), max(w, h)
        return w, h, self._pos.currentData()

    def on_run(self) -> None:
        self.accept()


def create(parent, doc: PdfDoc) -> OrganizeDialog:
    return OrganizeDialog(parent, doc)
