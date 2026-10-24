"""PDF 转 Word。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QLabel

from ...core.doc import PdfDoc
from ...core.ops import convert
from ..theme import human_size
from .. import i18n
from ..widgets import OutputPathField, PageScopeWidget, info, warn
from .base import ToolDialog


class WordDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 转 Word", 540, 460)
        self.set_run_text("转换")

        group = QGroupBox("转换模式")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._mode = QComboBox()
        for key, label in (
            (convert.WORD_EDITABLE, "可编辑（保留文字与表格版式，推荐）"),
            (convert.WORD_TEXT, "纯文字（按段落重排）"),
            (convert.WORD_FIDELITY, "版式还原（整页图片，文字不可选）"),
        ):
            self._mode.addItem(label, key)
        self._mode.currentIndexChanged.connect(self._sync)
        layout.addRow("模式", self._mode)

        self._desc = QLabel(convert.__doc__ or "")
        self._desc.setWordWrap(True)
        layout.addRow("", self._desc)
        self.add(group)

        self._scope = PageScopeWidget(include_selected=False)
        self.add(self._scope)

        self._out = OutputPathField("选择 DOCX 保存位置")
        self.add(self._out)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        desc = {
            convert.WORD_EDITABLE: "使用 pdf2docx 还原文字、表格与基本版式，输出可直接编辑的 DOCX。",
            convert.WORD_TEXT: "只提取文字并按视觉段落重排，适合纯文本文档。",
            convert.WORD_FIDELITY: "每页渲染成高清图片插入 Word，版式 100% 一致但文字不可选中。",
        }[self._mode.currentData()]
        self._desc.setText(i18n.translate(desc))

    def on_run(self) -> None:
        out = self._out.text()
        if not out:
            out = os.path.splitext(self.doc.path or "output")[0] + ".docx"
        if not out.lower().endswith(".docx"):
            out += ".docx"

        try:
            targets = self._scope.resolve(
                self.doc.page_count, self.parent().view.current_page
            )
        except Exception as exc:  # noqa: BLE001
            warn(self, "范围无效", str(exc))
            return

        def _done(path: str) -> None:
            info(self, "转换完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run(
            "PDF 转 Word", convert.pdf_to_word,
            self.doc.path, out,
            mode=self._mode.currentData(),
            pages=targets or None,
            on_done=_done,
        )


def create(parent, doc: PdfDoc) -> WordDialog:
    return WordDialog(parent, doc)
