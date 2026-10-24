"""PDF 压缩：四档压缩策略，输出新文件。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
)

from ...core.doc import PdfDoc
from ...core.ops import compress as compress_ops
from ..theme import human_size
from .. import i18n
from ..widgets import OutputPathField, info
from .base import ToolDialog


class CompressDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 压缩", 600, 640)
        self.set_run_text("压缩")

        group = QGroupBox("压缩级别")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._level = QComboBox()
        for key, label in compress_ops.LEVEL_LABELS.items():
            self._level.addItem(label, key)
        self._level.setCurrentIndex(1)
        self._level.currentIndexChanged.connect(self._sync)
        layout.addRow("级别", self._level)

        self._desc = QLabel("")
        self._desc.setWordWrap(True)
        layout.addRow("", self._desc)

        self._dpi = QSpinBox()
        self._dpi.setRange(0, 600)
        self._dpi.setSpecialValueText("使用默认值")
        layout.addRow("目标 DPI", self._dpi)

        self._quality = QSpinBox()
        self._quality.setRange(0, 100)
        self._quality.setSpecialValueText("使用默认值")
        layout.addRow("图像质量", self._quality)

        self._grayscale = QCheckBox("转灰度")
        layout.addRow("", self._grayscale)
        self.add(group)

        opt = QGroupBox("附加优化")
        ol = QFormLayout(opt)
        ol.setLabelAlignment(Qt.AlignRight)
        self._remove_metadata = QCheckBox("移除元数据")
        ol.addRow("", self._remove_metadata)
        self._remove_embedded = QCheckBox("移除附件/内嵌文件")
        ol.addRow("", self._remove_embedded)
        self._linearize = QCheckBox("线性化（便于网络浏览）")
        ol.addRow("", self._linearize)
        self.add(opt)

        self._out = OutputPathField("选择压缩结果保存位置")
        self.add(self._out)

        self._result = QLabel("")
        self._result.setWordWrap(True)
        self.add(self._result)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        key = self._level.currentData()
        self._desc.setText(i18n.translate(compress_ops.LEVEL_DESC.get(key, "")))
        raster = key in (compress_ops.LEVEL_BALANCED, compress_ops.LEVEL_STRONG,
                         compress_ops.LEVEL_EXTREME)
        self._dpi.setVisible(raster)
        self._quality.setVisible(raster)

    def on_run(self) -> None:
        out = self._out.text()
        if not out:
            base = os.path.splitext(self.doc.path or "output")[0]
            out = f"{base}-compressed.pdf"
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        options = compress_ops.CompressOptions(
            level=self._level.currentData(),
            grayscale=self._grayscale.isChecked(),
            remove_metadata=self._remove_metadata.isChecked(),
            remove_embedded=self._remove_embedded.isChecked(),
            linearize=self._linearize.isChecked(),
            dpi_target=self._dpi.value() or None,
            quality=self._quality.value() or None,
        )

        def _done(result: compress_ops.CompressResult) -> None:
            self._result.setText(i18n.translate(
                f"压缩前 {human_size(result.before)} → 压缩后 {human_size(result.after)}"
                f"（{result.ratio:.1%}），节省 {human_size(result.saved)}。\n{result.output}"
            ))
            info(self, "压缩完成", self._result.text())

        self.run(
            "压缩 PDF", compress_ops.compress_file,
            self.doc.path, out, options=options, on_done=_done,
        )


def create(parent, doc: PdfDoc) -> CompressDialog:
    return CompressDialog(parent, doc)
