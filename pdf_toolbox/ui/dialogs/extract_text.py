"""提取 PDF 文字：分页查看、搜索、清理、导出 TXT/Markdown/JSON。"""

from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from ...core.ops import extract
from ..theme import human_size
from .. import i18n
from ..widgets import info, warn
from .base import ToolDialog


class ExtractTextDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "提取 PDF 文字", 980, 720)
        self.set_run_text("重新提取")
        self._pages: list[extract.PageText] = []
        self._matches: list[tuple] = []
        self._match_idx = -1

        top = QHBoxLayout()
        self._view_mode = QComboBox()
        self._view_mode.addItems(["per-page", "merged"])
        self._view_mode.currentTextChanged.connect(self._render_text)
        top.addWidget(QLabel("视图"))
        top.addWidget(self._view_mode)

        self._search = QLineEdit()
        self._search.setPlaceholderText("在结果中搜索…")
        self._search.returnPressed.connect(lambda: self._search_next(1))
        top.addWidget(self._search, 1)
        for text, delta in (("上一个", -1), ("下一个", 1)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, d=delta: self._search_next(d))
            top.addWidget(btn)
        self.add_layout(top)

        clean = QGroupBox("文本清理")
        clean_bar = QHBoxLayout(clean)
        self._clean_spaces = QCheckBox("合并多余空格")
        self._clean_blank = QCheckBox("合并空行")
        self._clean_trim = QCheckBox("去除行首尾空白")
        for cb in (self._clean_spaces, self._clean_blank, self._clean_trim):
            cb.toggled.connect(lambda _=False: self._render_text())
            clean_bar.addWidget(cb)
        clean_bar.addStretch(1)
        self.add(clean)

        splitter = QSplitter(Qt.Horizontal)
        self._page_list = QListWidget()
        self._page_list.currentRowChanged.connect(self._render_text)
        splitter.addWidget(self._page_list)

        right = QVBoxLayout()
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        right.addWidget(self._text, 1)
        self._stats = QLabel("")
        right.addWidget(self._stats)
        widget = QWidget()
        widget.setLayout(right)
        splitter.addWidget(widget)
        splitter.setSizes([180, 760])
        self.add(splitter, 1)

        bar = QHBoxLayout()
        for text, fmt in (("导出 TXT", extract.FMT_TEXT),
                          ("导出 Markdown", extract.FMT_MARKDOWN),
                          ("导出 JSON", extract.FMT_JSON),
                          ("导出 HTML", extract.FMT_HTML)):
            btn = QPushButton(text)
            btn.clicked.connect(lambda _=False, f=fmt: self.export(f))
            bar.addWidget(btn)
        copy = QPushButton("复制到剪贴板")
        copy.clicked.connect(self.copy)
        bar.addWidget(copy)
        bar.addStretch(1)
        self.add_layout(bar)

        self.extract()

    # ---------------------------------------------------------------- 提取

    def extract(self) -> None:
        def _done(pages) -> None:
            self._pages = pages
            self._page_list.clear()
            for p in pages:
                status = "无文字" if p.char_count == 0 else f"{p.char_count} 字"
                self._page_list.addItem(f"第 {p.index + 1} 页　{status}")
            total_chars = sum(p.char_count for p in pages)
            total_words = sum(p.word_count for p in pages)
            blank = sum(1 for p in pages if p.char_count == 0)
            self._stats.setText(i18n.translate(
                f"共 {len(pages)} 页　字符 {total_chars}　词 {total_words}　无文字页 {blank}"
            ))
            if self._page_list.count():
                self._page_list.setCurrentRow(0)
            self._render_text()

        self.run("提取文字", extract.extract_text_pages, self.doc.path, on_done=_done)

    def on_run(self) -> None:
        self.extract()

    # ---------------------------------------------------------------- 显示

    def _cleaned(self, text: str) -> str:
        if self._clean_trim.isChecked():
            text = "\n".join(line.strip() for line in text.split("\n"))
        if self._clean_spaces.isChecked():
            text = re.sub(r"[ \t]{2,}", " ", text)
        if self._clean_blank.isChecked():
            text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _current_text(self) -> str:
        if self._view_mode.currentText() == "merged":
            return "\n\n".join(self._cleaned(p.text) for p in self._pages)
        row = self._page_list.currentRow()
        if 0 <= row < len(self._pages):
            return self._cleaned(self._pages[row].text)
        return ""

    def _render_text(self, *_args) -> None:
        self._text.setPlainText(self._current_text())
        self._matches = []
        self._match_idx = -1

    def _search_next(self, delta: int) -> None:
        query = self._search.text()
        if not query:
            return
        cursor = self._text.textCursor()
        found = self._text.find(query)
        if not found:
            # 回绕
            cursor.movePosition(QTextCursor.Start)
            self._text.setTextCursor(cursor)
            self._text.find(query)

    # ---------------------------------------------------------------- 导出

    def export(self, fmt: str) -> None:
        ext = {"txt": "txt", "markdown": "md", "json": "json", "html": "html"}[fmt]
        path = QFileDialog.getSaveFileName(
            self, "保存", f"{os.path.splitext(self.doc.title)[0]}-extracted.{ext}",
            f"*.{ext}",
        )[0]
        if not path:
            return

        def _done(_content) -> None:
            info(self, "导出完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run(
            "导出文字", extract.extract_text,
            self.doc.path, path, fmt=fmt, on_done=_done,
        )

    def copy(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self._current_text())
        info(self, "已复制", "结果已复制到剪贴板。")


def create(parent, doc: PdfDoc) -> ExtractTextDialog:
    return ExtractTextDialog(parent, doc)
