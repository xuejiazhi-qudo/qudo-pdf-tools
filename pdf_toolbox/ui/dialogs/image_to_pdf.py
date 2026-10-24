"""图片转 PDF。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
)

from ...core.doc import PdfDoc
from ...core.ops import pages
from ..theme import human_size
from ..widgets import ColorButton, OutputPathField, ask_open_images, error, info
from .base import ToolDialog

MARGIN_CHOICES = [
    ("none", "无边距", 0.0),
    ("small", "小（10mm）", 28.35),
    ("medium", "中（20mm）", 56.69),
    ("large", "大（30mm）", 85.04),
]


class ImageToPdfDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "图片转 PDF", 700, 660)
        self.set_run_text("生成 PDF")

        bar = QHBoxLayout()
        for text, slot in (
            ("添加图片…", self.add_images),
            ("移除", self.remove_selected),
            ("左转", lambda: self.rotate(-90)),
            ("右转", lambda: self.rotate(90)),
            ("上移", lambda: self.move(-1)),
            ("下移", lambda: self.move(1)),
            ("清空", lambda: (self._list.clear(), self._refresh())),
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
        self._list.setSpacing(6)
        self._list.setIconSize(QSize(110, 110))
        self.add(self._list)

        group = QGroupBox("页面设置")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._page_size = QComboBox()
        for key, label in (
            (pages.PAGE_SIZE_FIT, "贴合图片尺寸"),
            (pages.PAGE_SIZE_A4, "A4"),
            (pages.PAGE_SIZE_A4_LANDSCAPE, "A4 横向"),
            (pages.PAGE_SIZE_LETTER, "Letter"),
        ):
            self._page_size.addItem(label, key)
        layout.addRow("页面尺寸", self._page_size)

        self._orientation = QComboBox()
        self._orientation.addItems(["auto", "portrait", "landscape"])
        layout.addRow("方向", self._orientation)

        self._margin = QComboBox()
        for key, label, _ in MARGIN_CHOICES:
            self._margin.addItem(label, key)
        layout.addRow("边距", self._margin)

        self._bg = ColorButton("#ffffff")
        layout.addRow("背景色", self._bg)

        self.add(group)

        self._out = OutputPathField("选择输出 PDF 位置")
        self.add(self._out)
        self.add_stretch()

    # ---------------------------------------------------------------- 列表

    def add_images(self) -> None:
        for path in ask_open_images(self):
            pix = QPixmap(path)
            if pix.isNull():
                error(self, "无法读取图片", path)
                continue
            item = QListWidgetItem(os.path.basename(path))
            item.setIcon(QIcon(pix.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            item.setData(Qt.UserRole, {"path": path, "rot": 0})
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._list.addItem(item)
        self._refresh()

    def remove_selected(self) -> None:
        for item in reversed(self._list.selectedItems()):
            self._list.takeItem(self._list.row(item))
        self._refresh()

    def rotate(self, delta: int) -> None:
        for item in self._list.selectedItems():
            data = item.data(Qt.UserRole)
            data["rot"] = (data["rot"] + delta) % 360
            item.setData(Qt.UserRole, data)
            pix = QPixmap(data["path"]).transformed(
                QTransform().rotate(data["rot"]), Qt.SmoothTransformation,
            )
            item.setIcon(QIcon(pix.scaled(110, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            item.setText(f"{os.path.basename(data['path'])}　{data['rot']}°" if data["rot"] else os.path.basename(data["path"]))

    def move(self, delta: int) -> None:
        row = self._list.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self._list.count():
            return
        item = self._list.takeItem(row)
        self._list.insertItem(target, item)
        self._list.setCurrentRow(target)

    def _refresh(self) -> None:
        self.set_status(f"共 {self._list.count()} 张图片")

    # ---------------------------------------------------------------- 执行

    def on_run(self) -> None:
        if self._list.count() == 0:
            error(self, "没有图片", "请先添加至少一张图片。")
            return
        out = self._out.text()
        if not out:
            out = QFileDialog.getSaveFileName(self, "保存", "images-to-pdf.pdf", "PDF (*.pdf)")[0]
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        paths = [self._list.item(r).data(Qt.UserRole)["path"] for r in range(self._list.count())]
        rots = [self._list.item(r).data(Qt.UserRole)["rot"] for r in range(self._list.count())]
        margin = dict((k, v) for k, _l, v in MARGIN_CHOICES)[self._margin.currentData()]

        options = pages.ImageToPdfOptions(
            page_size=self._page_size.currentData(),
            margin=margin,
            orientation=self._orientation.currentText(),
            background=_hex_to_rgb(self._bg.hex()),
        )

        def _done(path: str) -> None:
            info(self, "生成完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run("图片转 PDF", pages.images_to_pdf, paths, out,
                 options=options, rotations=rots, on_done=_done)


def _hex_to_rgb(value: str):
    s = value.lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def create(parent, doc: PdfDoc) -> ImageToPdfDialog:
    return ImageToPdfDialog(parent, doc)
