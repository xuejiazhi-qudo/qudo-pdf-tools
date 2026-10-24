"""旋转 PDF 页面。"""

from __future__ import annotations

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QPushButton

from ...core.doc import PdfDoc
from ...core.ops import pages
from ..widgets import PageScopeWidget, info, vbox, warn
from .base import ToolDialog


class RotateDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "旋转 PDF 页面", 520, 420)
        self.set_run_text("应用旋转")

        group = QGroupBox("旋转角度（累加到页面现有旋转上）")
        bar = QHBoxLayout(group)
        self._angle = 90
        for text, angle in (("左转 90°", -90), ("右转 90°", 90), ("旋转 180°", 180)):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(angle == 90)
            btn.clicked.connect(lambda _=False, a=angle, b=btn: self._pick(a, b))
            bar.addWidget(btn)
        self.add(group)

        self._scope = PageScopeWidget(include_selected=True)
        self.add(self._scope)

        tip = QLabel("旋转会直接修改当前文档（可撤销），确认后请记得保存。")
        tip.setWordWrap(True)
        self.add(tip)
        self.add_stretch()

    def _pick(self, angle: int, button: QPushButton) -> None:
        self._angle = angle
        for other in button.parent().findChildren(QPushButton):
            other.setChecked(other is button)

    def on_run(self) -> None:
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
            warn(self, "未选择页面", "没有要旋转的页面。")
            return

        self.doc.snapshot()
        count = pages.rotate_pages(self.doc.fitz_doc, targets, self._angle)
        self.doc.mark_dirty(structural=True)
        info(self, "旋转完成", f"已旋转 {count} 页（{self._angle:+d}°）。记得保存。")


def create(parent, doc: PdfDoc) -> RotateDialog:
    return RotateDialog(parent, doc)
