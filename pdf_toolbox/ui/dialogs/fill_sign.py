"""PDF 填写与签名：文字/日期/符号/首字母/签名，压平绘制。"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from .. import i18n
from ...core.ops import stamp
from ..viewer import PdfView
from ..widgets import info, warn
from ..widgets.signature import get_signature

TOOLS = [
    (stamp.KIND_TEXT, "文字"),
    (stamp.KIND_DATE, "日期"),
    (stamp.KIND_CHECK, "✓"),
    (stamp.KIND_CROSS, "✗"),
    (stamp.KIND_DOT, "●"),
    (stamp.KIND_HOLLOW_DOT, "○"),
    (stamp.KIND_SQUARE, "■"),
    (stamp.KIND_LINE, "—"),
    (stamp.KIND_INITIALS, "首字母"),
    ("signature", "签名"),
]

DEFAULT_SIZES = {
    stamp.KIND_TEXT: (100, 20, 12),
    stamp.KIND_DATE: (120, 20, 12),
    stamp.KIND_INITIALS: (60, 20, 12),
}
SYMBOL_SIZE = (16, 16, 16)


class FillMode:
    def __init__(self, panel: "FillSignPanel") -> None:
        self.panel = panel
        self.view: Optional[PdfView] = None

    def attach(self, view: PdfView) -> None:
        self.view = view

    def detach(self) -> None:
        pass

    def mouse_press(self, event) -> bool:
        if event.button() != Qt.LeftButton or self.view is None:
            return False
        hit = self.view.view_to_page_point(event.position().toPoint())
        if hit is None:
            return False
        page, local = hit
        self.panel.place_at(page, local)
        return True

    def mouse_move(self, event) -> bool:
        return False

    def mouse_release(self, event) -> bool:
        return False

    def key_press(self, event) -> bool:
        return False


class FillSignPanel(QWidget):
    def __init__(self, mainwindow, doc: PdfDoc, view: PdfView) -> None:
        super().__init__()
        self.mainwindow = mainwindow
        self.doc = doc
        self.view = view
        self.tool = stamp.KIND_TEXT
        self.mode = FillMode(self)
        self._placed = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        info_bar = QLabel("")
        try:
            fi = stamp.detect_form_info(doc.fitz_doc)
            parts = []
            if fi["has_form_fields"]:
                parts.append(f"检测到 {fi['form_field_count']} 个表单字段（可在下方直接填写）")
            if fi["has_digital_signature"]:
                parts.append("⚠ 文档含数字签名，填写/签名会使其失效")
            info_bar.setText("　".join(parts) if parts else "未检测到表单字段，可直接点击页面添加内容。")
        except Exception:  # noqa: BLE001
            info_bar.setText("点击页面任意位置放置所选元素。")
        info_bar.setWordWrap(True)
        layout.addWidget(info_bar)

        tools = QGroupBox("放置工具（点击页面落位）")
        tl = QHBoxLayout(tools)
        tl.setSpacing(2)
        self._buttons: Dict[str, QPushButton] = {}
        for key, label in TOOLS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.tool)
            btn.clicked.connect(lambda _=False, k=key, b=btn: self._set_tool(k, b))
            self._buttons[key] = btn
            tl.addWidget(btn)
        layout.addWidget(tools)

        form_group = QGroupBox("表单字段填写")
        fl = QFormLayout(form_group)
        fl.setLabelAlignment(Qt.AlignRight)
        self._field_combo = QComboBox()
        self._fields: List[Dict] = []
        try:
            self._fields = stamp.list_form_fields(doc.fitz_doc)
        except Exception:  # noqa: BLE001
            self._fields = []
        for f in self._fields:
            self._field_combo.addItem(f"P{f['page'] + 1} {f['name'] or f['label'] or '(未命名)'}", f)
        if not self._fields:
            self._field_combo.addItem("(无表单字段)", None)
        fl.addRow("字段", self._field_combo)
        self._field_value = QLineEdit()
        fl.addRow("值", self._field_value)
        fill_btn = QPushButton("填写选中字段")
        fill_btn.clicked.connect(self.fill_field)
        fl.addRow("", fill_btn)
        layout.addWidget(form_group)

        self._status = QLabel("已放置 0 个元素")
        layout.addWidget(self._status)
        layout.addStretch(1)

    # ---------------------------------------------------------------- 生命周期

    def activate(self) -> None:
        self.view.set_mode(self.mode)

    def deactivate(self) -> None:
        self.view.set_mode(None)

    def _set_tool(self, key: str, button: QPushButton) -> None:
        self.tool = key
        for other in self._buttons.values():
            other.setChecked(other is button)

    # ---------------------------------------------------------------- 放置

    def place_at(self, page: int, point: QPointF) -> None:
        tool = self.tool
        element: Optional[stamp.FillElement] = None

        if tool == stamp.KIND_TEXT:
            text, ok = QInputDialog.getText(self, i18n.translate("添加文字"), i18n.translate("输入文字："))
            if not ok or not text:
                return
            w, h, fs = DEFAULT_SIZES[stamp.KIND_TEXT]
            element = stamp.FillElement(kind=tool, page=page, x=point.x(), y=point.y(),
                                        width=w, height=h, text=text, font_size=fs)
        elif tool == stamp.KIND_DATE:
            text, ok = QInputDialog.getItem(
                self, i18n.translate("日期格式"), i18n.translate("选择格式："),
                list(stamp.DATE_FORMATS.keys()), 0, False,
            )
            if not ok:
                return
            w, h, fs = DEFAULT_SIZES[stamp.KIND_DATE]
            element = stamp.FillElement(kind=tool, page=page, x=point.x(), y=point.y(),
                                        width=w, height=h,
                                        text=stamp.format_date(None, text), font_size=fs)
        elif tool == stamp.KIND_INITIALS:
            text, ok = QInputDialog.getText(self, i18n.translate("首字母缩写"), i18n.translate("输入缩写："))
            if not ok or not text:
                return
            w, h, fs = DEFAULT_SIZES[stamp.KIND_INITIALS]
            element = stamp.FillElement(kind=tool, page=page, x=point.x(), y=point.y(),
                                        width=w, height=h, text=text, font_size=fs)
        elif tool == "signature":
            data = get_signature(self)
            if not data:
                return
            element = stamp.FillElement(kind=stamp.KIND_DRAWN_SIG, page=page,
                                        x=point.x(), y=point.y(), width=150, height=60,
                                        image_bytes=data)
        else:
            w, h, fs = SYMBOL_SIZE
            element = stamp.FillElement(kind=tool, page=page, x=point.x(), y=point.y(),
                                        width=w, height=h, font_size=fs)

        self.doc.snapshot()
        stamp.apply_fill_elements(self.doc.fitz_doc, [element])
        self._placed += 1
        self.doc.mark_dirty()
        self._status.setText(i18n.translate(f"已放置 {self._placed} 个元素。记得保存。"))

    def fill_field(self) -> None:
        field = self._field_combo.currentData()
        if field is None:
            warn(self, "没有表单字段", "该文档不含可填写的表单字段。")
            return
        self.doc.snapshot()
        ok = stamp.set_form_field_value(
            self.doc.fitz_doc, field["page"], field["name"], self._field_value.text()
        )
        if ok:
            self.doc.mark_dirty()
            info(self, "已填写", f"字段 {field['name']} 已更新。记得保存。")
        else:
            warn(self, "填写失败", "找不到该字段。")


def create_panel(mainwindow, doc: PdfDoc, view: PdfView) -> FillSignPanel:
    return FillSignPanel(mainwindow, doc, view)
