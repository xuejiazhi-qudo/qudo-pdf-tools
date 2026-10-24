"""PDF 转 Excel：检测表格 + 可编辑网格 + 导出 XLSX/CSV。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
)

from ...core.doc import PdfDoc
from ...core.ops import convert
from ..theme import human_size
from .. import i18n
from ..widgets import OutputPathField, info, warn
from .base import ToolDialog


class ExcelDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 转 Excel", 900, 700)
        self.set_run_text("导出")
        self._tables: list[convert.TableData] = []

        top = QHBoxLayout()
        self._detect_btn = QPushButton("重新检测表格")
        self._detect_btn.clicked.connect(self.detect)
        top.addWidget(self._detect_btn)
        self._detect_label = QLabel("正在检测…")
        top.addWidget(self._detect_label, 1)
        self.add_layout(top)

        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._show_table)
        self.add(self._combo)

        bar = QHBoxLayout()
        for text, slot in (
            ("添加行", self.add_row),
            ("删除选中行", self.del_row),
            ("添加列", self.add_col),
            ("删除选中列", self.del_col),
            ("排除/包含此表", self.toggle_selected),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch(1)
        self.add_layout(bar)

        self._grid = QTableWidget()
        self._grid.setAlternatingRowColors(True)
        self.add(self._grid, 1)

        group = QGroupBox("导出选项")
        layout = QFormLayout(group)
        layout.setLabelAlignment(Qt.AlignRight)

        self._fmt = QComboBox()
        self._fmt.addItems([convert.EXCEL_XLSX, convert.EXCEL_CSV])
        self._fmt.currentTextChanged.connect(self._sync)
        layout.addRow("格式", self._fmt)

        self._sheet = QComboBox()
        for key, label in (
            (convert.SHEET_PER_TABLE, "每个表格一个工作表"),
            (convert.SHEET_PER_PAGE, "每页一个工作表"),
            (convert.SHEET_SINGLE, "全部放入一个工作表"),
        ):
            self._sheet.addItem(label, key)
        layout.addRow("工作表", self._sheet)

        self._numbers = QCheckBox("把可解析的单元格转成数值")
        self._numbers.setChecked(True)
        layout.addRow("", self._numbers)

        self._widths = QCheckBox("自动列宽")
        self._widths.setChecked(True)
        layout.addRow("", self._widths)
        self.add(group)

        self._out = OutputPathField("选择输出位置")
        self.add(self._out)

        self.detect()

    # ---------------------------------------------------------------- 检测

    def detect(self) -> None:
        self._detect_label.setText(i18n.translate("正在检测表格…"))
        self._detect_btn.setEnabled(False)

        def _done(tables) -> None:
            self._tables = tables
            self._detect_btn.setEnabled(True)
            self._combo.blockSignals(True)
            self._combo.clear()
            for t in tables:
                self._combo.addItem(
                    f"表格 {t.index}　第 {t.page + 1} 页　{t.row_count}×{t.col_count}　{t.method}",
                    t,
                )
            self._combo.blockSignals(False)
            aligned = sum(1 for t in tables if t.method == "aligned")
            note = "（含无边框对齐表格，精度可能较低）" if aligned else ""
            self._detect_label.setText(i18n.translate(f"检测到 {len(tables)} 个表格{note}"))
            self._show_table()

        self.run("检测表格", convert.detect_tables, self.doc.path, on_done=_done)

    def _current(self) -> convert.TableData | None:
        return self._combo.currentData()

    def _show_table(self, *_args) -> None:
        table = self._current()
        self._grid.clear()
        if table is None:
            self._grid.setRowCount(0)
            self._grid.setColumnCount(0)
            return
        rows, cols = table.rows, table.col_count
        self._grid.setRowCount(len(rows))
        self._grid.setColumnCount(cols)
        self._grid.setHorizontalHeaderLabels([f"列 {c + 1}" for c in range(cols)])
        for r, row in enumerate(rows):
            for c in range(cols):
                value = row[c] if c < len(row) else ""
                self._grid.setItem(r, c, QTableWidgetItem(value))
        self._grid.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)

    def _commit_grid(self) -> None:
        table = self._current()
        if table is None:
            return
        rows = []
        for r in range(self._grid.rowCount()):
            row = []
            for c in range(self._grid.columnCount()):
                item = self._grid.item(r, c)
                row.append(item.text() if item else "")
            rows.append(row)
        table.rows = rows

    # ---------------------------------------------------------------- 编辑

    def add_row(self) -> None:
        self._commit_grid()
        self._grid.insertRow(self._grid.rowCount())

    def del_row(self) -> None:
        rows = sorted({i.row() for i in self._grid.selectedItems()}, reverse=True)
        for r in rows:
            self._grid.removeRow(r)
        self._commit_grid()

    def add_col(self) -> None:
        self._commit_grid()
        self._grid.insertColumn(self._grid.columnCount())

    def del_col(self) -> None:
        cols = sorted({i.column() for i in self._grid.selectedItems()}, reverse=True)
        for c in cols:
            self._grid.removeColumn(c)
        self._commit_grid()

    def toggle_selected(self) -> None:
        table = self._current()
        if table is None:
            return
        table.selected = not table.selected
        idx = self._combo.currentIndex()
        label = self._combo.itemText(idx)
        prefix = "✓ " if table.selected else "✗ "
        base = label.lstrip("✓✗ ").strip()
        self._combo.setItemText(idx, prefix + base)

    def _sync(self, *_args) -> None:
        self._sheet.setVisible(self._fmt.currentText() == convert.EXCEL_XLSX)

    # ---------------------------------------------------------------- 导出

    def on_run(self) -> None:
        self._commit_grid()
        selected = [t for t in self._tables if t.selected and t.rows]
        if not selected:
            warn(self, "没有可导出的表格", "请先检测或包含至少一个表格。")
            return

        out = self._out.text()
        if not out:
            out = os.path.splitext(self.doc.path or "output")[0]
        suffix = self._fmt.currentText()
        if not out.lower().endswith(f".{suffix}"):
            out += f".{suffix}"

        def _done(path: str) -> None:
            info(self, "导出完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run(
            "导出表格", convert.export_tables,
            selected, out,
            fmt=suffix,
            sheet_mode=self._sheet.currentData(),
            numbers=self._numbers.isChecked(),
            auto_width=self._widths.isChecked(),
            on_done=_done,
        )


def create(parent, doc: PdfDoc) -> ExcelDialog:
    return ExcelDialog(parent, doc)
