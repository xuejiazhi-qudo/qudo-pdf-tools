"""PDF 拆分。"""

from __future__ import annotations

import os
import zipfile
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
)

from ...core import pagerange
from ...core.doc import PdfDoc
from ...core.ops import pages
from ..theme import human_size
from .. import i18n
from ..widgets import OutputPathField, error, form, info, vbox, warn
from .base import ToolDialog

MODE_LABELS = [
    (pages.SPLIT_RANGES, "按范围拆分（每段一个文件）"),
    (pages.SPLIT_FIXED, "每 N 页一个文件"),
    (pages.SPLIT_SINGLE, "每页一个文件"),
    (pages.SPLIT_PARTS, "平均切成 N 份"),
    (pages.SPLIT_EVEN_ODD, "奇偶页分开"),
    ("extract", "提取选中页为一个文件"),
]


class SplitDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 拆分", 560, 560)
        self.set_run_text("拆分")

        group = QGroupBox("拆分方式")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._mode = QComboBox()
        for key, label in MODE_LABELS:
            self._mode.addItem(label, key)
        self._mode.currentIndexChanged.connect(self._sync_visibility)
        layout.addRow("模式", self._mode)

        self._ranges_label = QLabel("范围")
        self._ranges = QLineEdit()
        self._ranges.setPlaceholderText("用分号分隔各段，如 1-3;4-6;7-")
        self._ranges.textChanged.connect(self._preview)
        layout.addRow(self._ranges_label, self._ranges)

        self._every_label = QLabel("每份页数")
        self._every = QSpinBox()
        self._every.setRange(1, 9999)
        self._every.setValue(1)
        layout.addRow(self._every_label, self._every)

        self._parts_label = QLabel("份数")
        self._parts = QSpinBox()
        self._parts.setRange(1, 9999)
        self._parts.setValue(2)
        layout.addRow(self._parts_label, self._parts)

        self.add(group)

        out_group = QGroupBox("输出")
        out_layout = form([])
        out_group.setLayout(out_layout)
        self._dir = OutputPathField("选择输出目录", is_dir=True)
        out_layout.addRow("输出目录", self._dir)
        self._prefix = QLineEdit()
        self._prefix.setPlaceholderText("留空则使用原文件名")
        out_layout.addRow("文件名前缀", self._prefix)
        self._zip = QCheckBox("多个文件时打包为 ZIP")
        self._zip.setChecked(True)
        out_layout.addRow("", self._zip)
        self.add(out_group)

        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self.add(self._preview_label)
        self.add_stretch()

        self._sync_visibility()

    def _sync_visibility(self) -> None:
        key = self._mode.currentData()
        self._ranges_label.setVisible(key == pages.SPLIT_RANGES)
        self._ranges.setVisible(key == pages.SPLIT_RANGES)
        self._every_label.setVisible(key == pages.SPLIT_FIXED)
        self._every.setVisible(key == pages.SPLIT_FIXED)
        self._parts_label.setVisible(key == pages.SPLIT_PARTS)
        self._parts.setVisible(key == pages.SPLIT_PARTS)
        self._preview()

    def _preview(self, *_args) -> None:
        key = self._mode.currentData()
        n = self.doc.page_count
        try:
            if key == pages.SPLIT_RANGES:
                tokens = [t for t in self._ranges.text().split(";") if t.strip()]
                groups = [pagerange.parse(t, n) for t in tokens] if tokens else []
            elif key == pages.SPLIT_FIXED:
                size = max(1, self._every.value())
                groups = [list(range(i, min(i + size, n))) for i in range(0, n, size)]
            elif key == pages.SPLIT_SINGLE:
                groups = [[i] for i in range(n)]
            elif key == pages.SPLIT_PARTS:
                groups = [list(r) for r in pagerange.chunk_even(n, self._parts.value())]
            elif key == pages.SPLIT_EVEN_ODD:
                groups = [g for g in (list(range(0, n, 2)), list(range(1, n, 2))) if g]
            else:
                selected = self.parent().thumbs.selected_pages()
                groups = [selected] if selected else []
        except pagerange.PageRangeError as exc:
            self._preview_label.setText(i18n.translate(f"⚠ {exc}"))
            return
        detail = "；".join(
            f"{pagerange.format(g)}（{len(g)} 页）" for g in groups[:8]
        )
        more = "…" if len(groups) > 8 else ""
        self._preview_label.setText(i18n.translate(f"将生成 {len(groups)} 个文件：{detail}{more}"))

    def on_run(self) -> None:
        key = self._mode.currentData()
        out_dir = self._dir.text()
        if not out_dir:
            error(self, "缺少输出目录", "请先选择输出目录。")
            return

        base = self._prefix.text().strip() or os.path.splitext(self.doc.title)[0]

        if key == "extract":
            selected = self.parent().thumbs.selected_pages()
            if not selected:
                warn(self, "未选择页面", "请先在左侧缩略图中选择要提取的页面。")
                return
            target = os.path.join(out_dir, f"{pages.sanitize_filename(base)}-extracted.pdf")

            def _done_extract(path: str) -> None:
                info(self, "提取完成", f"{path}\n{human_size(os.path.getsize(path))}")

            self.run(
                "提取页面", pages.extract_pages,
                self.doc.path, selected, target, on_done=_done_extract,
            )
            return

        def _done(result: pages.SplitResult) -> None:
            files = result.files
            if not files:
                warn(self, "没有生成文件", "请检查拆分设置。")
                return
            if self._zip.isChecked() and len(files) > 1:
                zip_path = os.path.join(out_dir, f"{pages.sanitize_filename(base)}-all.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in files:
                        zf.write(f, os.path.basename(f))
                info(self, "拆分完成", f"共 {len(files)} 个文件，已打包：\n{zip_path}")
            else:
                info(self, "拆分完成", f"共生成 {len(files)} 个文件：\n" + "\n".join(files[:10]))

        self.run(
            "拆分 PDF", pages.split_pdf,
            self.doc.path, out_dir,
            mode=key,
            ranges=self._ranges.text(),
            pages_per_file=self._every.value(),
            parts=self._parts.value(),
            name_template=None,
            on_done=_done,
        )


def create(parent, doc: PdfDoc) -> SplitDialog:
    return SplitDialog(parent, doc)
