"""PDF 转图片。"""

from __future__ import annotations

import os
import zipfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
)

from ...core.doc import PdfDoc
from ...core.ops import pages
from ..theme import human_size
from ..widgets import ColorButton, OutputPathField, PageScopeWidget, error, info, warn
from .base import ToolDialog

RES_CHOICES = [
    ("standard", "标准（96 DPI）", 96),
    ("hd", "高清（150 DPI）", 150),
    ("print", "印刷（300 DPI）", 300),
    ("custom", "自定义", 150),
]


class PdfToImageDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 转图片", 560, 620)
        self.set_run_text("导出图片")

        self._scope = PageScopeWidget(include_selected=True)
        self.add(self._scope)

        group = QGroupBox("导出选项")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._fmt = QComboBox()
        self._fmt.addItems(["jpg", "png", "webp"])
        self._fmt.currentTextChanged.connect(self._sync)
        layout.addRow("格式", self._fmt)

        self._quality = QSpinBox()
        self._quality.setRange(10, 100)
        self._quality.setValue(92)
        layout.addRow("质量", self._quality)

        self._res = QComboBox()
        for key, label, _ in RES_CHOICES:
            self._res.addItem(label, key)
        self._res.currentIndexChanged.connect(self._sync)
        layout.addRow("分辨率", self._res)

        self._dpi = QSpinBox()
        self._dpi.setRange(36, 600)
        self._dpi.setValue(150)
        layout.addRow("自定义 DPI", self._dpi)

        self._maxw = QSpinBox()
        self._maxw.setRange(0, 20000)
        self._maxw.setValue(0)
        self._maxw.setSpecialValueText("不限制")
        self._maxw.setSuffix(" px")
        layout.addRow("最大宽度", self._maxw)

        self._bgmode = QComboBox()
        self._bgmode.addItems(["white", "transparent", "custom"])
        self._bgmode.currentTextChanged.connect(self._sync)
        layout.addRow("背景", self._bgmode)

        self._bgcolor = ColorButton("#ffffff")
        layout.addRow("背景色", self._bgcolor)

        self._gray = QCheckBox("输出灰度")
        layout.addRow("", self._gray)

        self.add(group)

        out_group = QGroupBox("输出")
        out_layout = QFormLayout(out_group)
        self._dir = OutputPathField("选择输出目录", is_dir=True)
        out_layout.addRow("输出目录", self._dir)
        self._prefix = QLineEdit()
        self._prefix.setPlaceholderText("留空则使用原文件名")
        out_layout.addRow("文件名前缀", self._prefix)
        self._zip = QCheckBox("多张图片打包为 ZIP")
        self._zip.setChecked(True)
        out_layout.addRow("", self._zip)
        self.add(out_group)
        self.add_stretch()

        self._sync()

    def _sync(self, *_args) -> None:
        fmt = self._fmt.currentText()
        self._quality.setVisible(fmt != "png")
        custom = self._res.currentData() == "custom"
        self._dpi.setVisible(custom)
        transparent = self._bgmode.currentText() == "transparent"
        self._bgcolor.setVisible(self._bgmode.currentText() == "custom")
        if transparent and fmt != "png":
            self._bgmode.setCurrentText("white")

    def _dpi_value(self) -> int:
        key = self._res.currentData()
        if key == "custom":
            return self._dpi.value()
        return dict((k, v) for k, _l, v in RES_CHOICES)[key]

    def on_run(self) -> None:
        out_dir = self._dir.text()
        if not out_dir:
            error(self, "缺少输出目录", "请先选择输出目录。")
            return
        try:
            targets = self._scope.resolve(
                self.doc.page_count,
                self.parent().view.current_page,
                self.parent().thumbs.selected_pages(),
            )
        except Exception as exc:  # noqa: BLE001
            warn(self, "范围无效", str(exc))
            return
        if not targets:
            warn(self, "未选择页面", "没有要导出的页面。")
            return

        fmt = self._fmt.currentText()
        bgmode = self._bgmode.currentText()
        background = None
        transparent = False
        if bgmode == "custom":
            s = self._bgcolor.hex().lstrip("#")
            background = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
        elif bgmode == "transparent":
            transparent = True

        prefix = self._prefix.text().strip() or None

        def _done(files) -> None:
            if not files:
                warn(self, "没有导出文件", "请检查设置。")
                return
            if self._zip.isChecked() and len(files) > 1:
                zip_path = os.path.join(out_dir, f"{pages.sanitize_filename(prefix or os.path.splitext(self.doc.title)[0])}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in files:
                        zf.write(f, os.path.basename(f))
                info(self, "导出完成", f"共 {len(files)} 张，已打包：\n{zip_path}")
            else:
                info(self, "导出完成", f"共 {len(files)} 张：\n" + "\n".join(files[:8]))

        self.run(
            "PDF 转图片", pages.pdf_to_images,
            self.doc.path, out_dir,
            fmt=fmt,
            dpi=self._dpi_value(),
            quality=self._quality.value(),
            pages=targets,
            prefix=prefix,
            grayscale=self._gray.isChecked(),
            transparent=transparent,
            background=background,
            max_width=self._maxw.value() or None,
            on_done=_done,
        )


def create(parent, doc: PdfDoc) -> PdfToImageDialog:
    return PdfToImageDialog(parent, doc)
