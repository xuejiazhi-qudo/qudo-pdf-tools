"""PDF 裁剪与去白边。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QTabWidget,
)

from ...core.doc import PdfDoc
from ...core.ops import crop as crop_ops
from .. import i18n
from ..widgets import PageScopeWidget, info, warn
from .base import ToolDialog


class CropDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 裁剪与去白边", 560, 620)
        self.set_run_text("应用裁剪")

        tabs = QTabWidget()

        # ---- 自动去白边
        auto = QGroupBox("自动去白边")
        auto_layout = QFormLayout(auto)
        self._sensitivity = QComboBox()
        for key, label in (
            (crop_ops.SENSITIVITY_LOW, "低（只认深色内容）"),
            (crop_ops.SENSITIVITY_STANDARD, "标准（推荐）"),
            (crop_ops.SENSITIVITY_HIGH, "高（浅色水印也算内容）"),
        ):
            self._sensitivity.addItem(label, key)
        self._sensitivity.setCurrentIndex(1)
        auto_layout.addRow("灵敏度", self._sensitivity)

        self._safety = QDoubleSpinBox()
        self._safety.setRange(0, 50)
        self._safety.setValue(5)
        self._safety.setSuffix(" mm")
        auto_layout.addRow("安全边距", self._safety)

        self._unify = QCheckBox("所有页面裁成相同尺寸")
        auto_layout.addRow("", self._unify)
        tabs.addTab(auto, "自动去白边")

        # ---- 手动裁切
        manual = QGroupBox("手动裁切（按显示方向的四边裁切量）")
        manual_layout = QFormLayout(manual)
        self._unit = QComboBox()
        self._unit.addItems(["mm", "cm", "in", "pt"])
        manual_layout.addRow("单位", self._unit)

        self._linked = QCheckBox("四边联动")
        manual_layout.addRow("", self._linked)

        self._top = QDoubleSpinBox()
        self._right = QDoubleSpinBox()
        self._bottom = QDoubleSpinBox()
        self._left = QDoubleSpinBox()
        for spin in (self._top, self._right, self._bottom, self._left):
            spin.setRange(0, 1000)
            spin.setDecimals(2)
            spin.valueChanged.connect(self._on_linked)
        manual_layout.addRow("上", self._top)
        manual_layout.addRow("右", self._right)
        manual_layout.addRow("下", self._bottom)
        manual_layout.addRow("左", self._left)

        self._reset_btn = QPushButton("恢复原始尺寸")
        self._reset_btn.clicked.connect(self.reset_crop)
        manual_layout.addRow("", self._reset_btn)
        tabs.addTab(manual, "手动裁切")

        self.add(tabs)
        self._tabs = tabs

        self._scope = PageScopeWidget(include_selected=True)
        self.add(self._scope)

        self._result = QLabel("")
        self._result.setWordWrap(True)
        self.add(self._result)
        self.add_stretch()

    def _on_linked(self, value: float) -> None:
        if not self._linked.isChecked():
            return
        sender = self.sender()
        for spin in (self._top, self._right, self._bottom, self._left):
            if spin is not sender:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)

    def _targets(self):
        return self._scope.resolve(
            self.doc.page_count,
            self.parent().view.current_page,
            self.parent().thumbs.selected_pages(),
        )

    def on_run(self) -> None:
        try:
            targets = self._targets()
        except Exception as exc:  # noqa: BLE001
            warn(self, "范围无效", str(exc))
            return
        if not targets:
            warn(self, "未选择页面", "没有要裁剪的页面。")
            return

        self.doc.snapshot()
        if self._tabs.currentIndex() == 0:
            report = crop_ops.auto_crop_pages(
                self.doc.fitz_doc,
                targets,
                sensitivity=self._sensitivity.currentData(),
                safety_mm=self._safety.value(),
                unify=self._unify.isChecked(),
            )
            same = "，裁完尺寸一致" if report.all_same_size else ""
            self._result.setText(i18n.translate(
                f"已裁剪 {len(report.processed)} 页，跳过 {len(report.skipped)} 页（空白或无法检测）{same}。"
            ))
        else:
            unit = self._unit.currentText()
            margins = crop_ops.CropMargins(
                top=crop_ops.to_points(self._top.value(), unit),
                right=crop_ops.to_points(self._right.value(), unit),
                bottom=crop_ops.to_points(self._bottom.value(), unit),
                left=crop_ops.to_points(self._left.value(), unit),
            )
            report = crop_ops.manual_crop_pages(self.doc.fitz_doc, targets, margins)
            self._result.setText(i18n.translate(f"已裁剪 {len(report.processed)} 页，跳过 {len(report.skipped)} 页。"))

        self.doc.mark_dirty(structural=True)
        info(self, "裁剪完成", self._result.text() + "\n记得保存。")

    def reset_crop(self) -> None:
        targets = self._targets()
        self.doc.snapshot()
        n = crop_ops.reset_crop(self.doc.fitz_doc, targets)
        self.doc.mark_dirty(structural=True)
        info(self, "已恢复", f"已恢复 {n} 页的原始尺寸。")


def create(parent, doc: PdfDoc) -> CropDialog:
    return CropDialog(parent, doc)
