"""新建空白 PDF。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
)

from ...core.doc import PdfDoc
from ..widgets import ColorButton, warn
from .base import ToolDialog

PAGE_SIZES = [
    ("a4", "A4 (210×297mm)", 595.28, 841.89),
    ("a5", "A5 (148×210mm)", 419.53, 595.28),
    ("a3", "A3 (297×420mm)", 841.89, 1190.55),
    ("letter", "Letter (8.5×11in)", 612.0, 792.0),
    ("legal", "Legal (8.5×14in)", 612.0, 1008.0),
    ("custom", "自定义", 595.28, 841.89),
]


class NewPdfDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "新建 PDF", 460, 420)
        self.set_run_text("创建")

        group = QGroupBox("页面设置")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._size = QComboBox()
        for key, label, _w, _h in PAGE_SIZES:
            self._size.addItem(label, key)
        self._size.currentIndexChanged.connect(self._sync)
        layout.addRow("纸张", self._size)

        self._orient = QComboBox()
        self._orient.addItems(["portrait", "landscape"])
        layout.addRow("方向", self._orient)

        self._count = QSpinBox()
        self._count.setRange(1, 500)
        self._count.setValue(1)
        layout.addRow("页数", self._count)

        self._width = QDoubleSpinBox()
        self._width.setRange(20, 5000)
        self._width.setValue(210)
        self._width.setSuffix(" mm")
        layout.addRow("宽", self._width)
        self._height = QDoubleSpinBox()
        self._height.setRange(20, 5000)
        self._height.setValue(297)
        self._height.setSuffix(" mm")
        layout.addRow("高", self._height)

        self._bg = ColorButton("#ffffff")
        layout.addRow("背景色", self._bg)

        self._confirm = QCheckBox("替换当前文档前确认（有未保存修改时）")
        self._confirm.setChecked(True)
        layout.addRow("", self._confirm)

        self.add(group)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        custom = self._size.currentData() == "custom"
        self._width.setVisible(custom)
        self._height.setVisible(custom)

    def _dims(self) -> tuple:
        if self._size.currentData() == "custom":
            w = self._width.value() * 72.0 / 25.4
            h = self._height.value() * 72.0 / 25.4
        else:
            key = self._size.currentData()
            entry = next(e for e in PAGE_SIZES if e[0] == key)
            w, h = entry[2], entry[3]
        if self._orient.currentText() == "landscape":
            w, h = max(w, h), min(w, h)
        else:
            w, h = min(w, h), max(w, h)
        return w, h

    def on_run(self) -> None:
        if self.doc.dirty and self._confirm.isChecked():
            from PySide6.QtWidgets import QMessageBox

            ret = QMessageBox.question(
                self,
                "有未保存的修改",
                "当前文档有未保存的修改，新建会丢弃它们。继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
        w, h = self._dims()
        s = self._bg.hex().lstrip("#")
        self.doc.new_blank(
            page_count=self._count.value(),
            width=w,
            height=h,
            background=(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)),
        )
        self.parent().view.set_zoom(1.0)
        self.parent().view.fit_page()
        self.accept()


def create(parent, doc: PdfDoc) -> NewPdfDialog:
    return NewPdfDialog(parent, doc)
