"""提取 PDF 图片：内嵌图片列表 + 区域导出。"""

from __future__ import annotations

import os
import zipfile
from typing import List, Optional

import pymupdf
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QImage, QPixmap, QMouseEvent, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from ...core.ops import extract, pages
from ..theme import human_size
from .. import i18n
from ..widgets import OutputPathField, info, warn
from .base import ToolDialog


class _RegionPreview(QLabel):
    rectChosen = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._origin: Optional[QPoint] = None
        self._current: Optional[QRect] = None
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(320, 240)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._current = QRect(self._origin, self._origin)
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None:
            self._current = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._origin is not None and event.button() == Qt.LeftButton:
            self._current = QRect(self._origin, event.position().toPoint()).normalized()
            self._origin = None
            self.rectChosen.emit(self._current)
            self.update()
            event.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._current and self._current.isValid():
            painter = QPainter(self)
            pen = QPen(QColor(47, 111, 208), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(self._current)
            painter.end()

    def chosen(self) -> Optional[QRect]:
        return self._current


class ExtractImagesDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "提取 PDF 图片", 960, 720)
        self.set_run_text("重新扫描")
        self._images: List[extract.ExtractedImage] = []
        self._page_rects: List = []
        self._region_rect: Optional[QRect] = None
        self._region_scale = 1.0

        tabs = QTabWidget()

        # ---- Tab 1 内嵌图片
        tab1 = QWidget()
        lay1 = QVBoxLayout(tab1)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("页"))
        self._f_page = QComboBox()
        self._f_page.addItem("全部", 0)
        self._f_page.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._f_page)
        filters.addWidget(QLabel("格式"))
        self._f_fmt = QComboBox()
        self._f_fmt.addItems(["all", "jpeg", "png", "other"])
        self._f_fmt.currentTextChanged.connect(self._apply_filters)
        filters.addWidget(self._f_fmt)
        filters.addWidget(QLabel("隐藏小于"))
        self._f_small = QComboBox()
        for v, label in ((0, "不隐藏"), (32, "32px"), (64, "64px")):
            self._f_small.addItem(label, v)
        self._f_small.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._f_small)
        self._f_dup = QCheckBox("合并重复图片")
        self._f_dup.setChecked(True)
        self._f_dup.toggled.connect(lambda _=False: self._apply_filters())
        filters.addWidget(self._f_dup)
        filters.addStretch(1)
        lay1.addLayout(filters)

        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(["", "页", "尺寸", "色彩空间", "透明", "估计大小"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.itemDoubleClicked.connect(self._preview)
        lay1.addWidget(self._table, 1)

        bar1 = QHBoxLayout()
        for text, slot in (
            ("全选", lambda: self._set_all(True)),
            ("不选", lambda: self._set_all(False)),
            ("导出选中…", self.export_selected),
            ("导出全部并打包 ZIP…", self.export_zip),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar1.addWidget(btn)
        bar1.addStretch(1)
        lay1.addLayout(bar1)
        tabs.addTab(tab1, "内嵌图片")

        # ---- Tab 2 区域导出
        tab2 = QWidget()
        lay2 = QVBoxLayout(tab2)
        opts = QFormLayout()
        self._r_page = QSpinBox()
        self._r_page.setMinimum(1)
        self._r_page.valueChanged.connect(self._render_region_preview)
        opts.addRow("页", self._r_page)
        self._r_scale = QComboBox()
        self._r_scale.addItems(["1x", "2x", "3x"])
        opts.addRow("导出倍率", self._r_scale)
        self._r_fmt = QComboBox()
        self._r_fmt.addItems(["png", "jpeg"])
        opts.addRow("格式", self._r_fmt)
        self._r_quality = QSpinBox()
        self._r_quality.setRange(10, 100)
        self._r_quality.setValue(92)
        opts.addRow("质量", self._r_quality)
        lay2.addLayout(opts)

        self._preview_label = _RegionPreview()
        self._preview_label.rectChosen.connect(self._on_region)
        scroll = QScrollArea()
        scroll.setWidget(self._preview_label)
        scroll.setWidgetResizable(True)
        lay2.addWidget(scroll, 1)

        self._region_info = QLabel("在预览图上拖拽框选要导出的区域。")
        lay2.addWidget(self._region_info)
        bar2 = QHBoxLayout()
        btn = QPushButton("导出选区…")
        btn.clicked.connect(self.export_region)
        bar2.addWidget(btn)
        bar2.addStretch(1)
        lay2.addLayout(bar2)
        tabs.addTab(tab2, "区域导出")

        self.add(tabs, 1)
        self.scan()

    # ---------------------------------------------------------------- 扫描

    def scan(self) -> None:
        def _done(images) -> None:
            self._images = images
            self._page_rects = self.doc.page_sizes()
            self._f_page.blockSignals(True)
            self._f_page.clear()
            self._f_page.addItem("全部", 0)
            for p in sorted({i.page for i in images}):
                self._f_page.addItem(f"第 {p + 1} 页", p + 1)
            self._f_page.blockSignals(False)
            self._r_page.setMaximum(max(1, self.doc.page_count))
            self._apply_filters()
            self._render_region_preview()

        self.run("扫描图片", extract.list_images, self.doc.path, on_done=_done)

    def on_run(self) -> None:
        self.scan()

    def _visible(self) -> List[extract.ExtractedImage]:
        page = self._f_page.currentData() or 0
        fmt = self._f_fmt.currentText()
        small = self._f_small.currentData() or 0
        seen_hashes = set()
        out = []
        for img in self._images:
            if page and img.page + 1 != page:
                continue
            if max(img.width, img.height) < small:
                continue
            if fmt == "jpeg" and img.ext not in ("jpg", "jpeg"):
                continue
            if fmt == "png" and img.ext != "png":
                continue
            if fmt == "other" and img.ext in ("jpg", "jpeg", "png"):
                continue
            key = (img.width, img.height, img.page)
            if self._f_dup.isChecked():
                if key in seen_hashes:
                    continue
                seen_hashes.add(key)
            out.append(img)
        return out

    def _apply_filters(self, *_args) -> None:
        visible = self._visible()
        self._table.setRowCount(len(visible))
        for r, img in enumerate(visible):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check.setCheckState(Qt.Checked)
            check.setData(Qt.UserRole, img.xref)
            self._table.setItem(r, 0, check)
            for c, value in enumerate(
                (str(img.page + 1), f"{img.width}×{img.height}",
                 img.colorspace, "是" if img.has_alpha else "否",
                 human_size(img.size_bytes or (img.width * img.height / 4))),
                start=1,
            ):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(r, c, item)
        self.set_status(f"显示 {len(visible)} / {len(self._images)} 张")

    def _set_all(self, checked: bool) -> None:
        for r in range(self._table.rowCount()):
            self._table.item(r, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _selected_xrefs(self) -> List[int]:
        out = []
        for r in range(self._table.rowCount()):
            if self._table.item(r, 0).checkState() == Qt.Checked:
                out.append(self._table.item(r, 0).data(Qt.UserRole))
        return out

    def _preview(self, item: QTableWidgetItem) -> None:
        row = item.row()
        xref = self._table.item(row, 0).data(Qt.UserRole)
        try:
            with pymupdf.open(self.doc.path) as d:
                data = d.extract_image(xref)
            img = QImage.fromData(data["image"])
        except Exception as exc:  # noqa: BLE001
            warn(self, "无法预览", str(exc))
            return
        dlg = QLabel(self)
        dlg.setPixmap(QPixmap.fromImage(img).scaledToWidth(480, Qt.SmoothTransformation))
        dlg.setWindowTitle(f"图片 {xref}")
        dlg.show()

    # ---------------------------------------------------------------- 导出

    def export_selected(self) -> None:
        xrefs = self._selected_xrefs()
        if not xrefs:
            warn(self, "未选择图片", "请先勾选要导出的图片。")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not out_dir:
            return

        def _done(results) -> None:
            info(self, "导出完成", f"共 {len(results)} 张到：\n{out_dir}")

        self.run(
            "导出图片", extract.extract_images,
            self.doc.path, out_dir, xrefs=xrefs, on_done=_done,
        )

    def export_zip(self) -> None:
        xrefs = self._selected_xrefs()
        if not xrefs:
            warn(self, "未选择图片", "请先勾选要导出的图片。")
            return
        path = QFileDialog.getSaveFileName(
            self, "保存 ZIP", f"{os.path.splitext(self.doc.title)[0]}-images.zip", "*.zip"
        )[0]
        if not path:
            return

        def _done(results) -> None:
            info(self, "导出完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run(
            "打包图片", extract.extract_images_zip,
            self.doc.path, path, xrefs=xrefs, on_done=_done,
        )

    # ---------------------------------------------------------------- 区域

    def _render_region_preview(self, *_args) -> None:
        index = self._r_page.value() - 1
        if not 0 <= index < self.doc.page_count:
            return
        self._region_scale = 1.0
        img = self.doc.render(index, 1.0)
        self._preview_label.setPixmap(QPixmap.fromImage(img))
        self._region_rect = None
        self._region_info.setText(i18n.translate("在预览图上拖拽框选要导出的区域。"))

    def _on_region(self, rect: QRect) -> None:
        self._region_rect = rect
        self._region_info.setText(i18n.translate(
            f"选区：{rect.width()}×{rect.height()} px（预览 1x）"
        ))

    def export_region(self) -> None:
        if not self._region_rect or not self._region_rect.isValid():
            warn(self, "未框选区域", "请先在预览图上拖拽选择区域。")
            return
        path = QFileDialog.getSaveFileName(
            self, "保存选区", f"{os.path.splitext(self.doc.title)[0]}-region.png",
            "PNG (*.png);;JPEG (*.jpg)",
        )[0]
        if not path:
            return

        index = self._r_page.value() - 1
        scale = float(self._r_scale.currentText().rstrip("x"))
        rect = self._region_rect

        def _work(progress) -> str:
            progress.report(30, "渲染选区")
            doc = pymupdf.open(self.doc.path)
            try:
                page = doc.load_page(index)
                clip = pymupdf.Rect(
                    rect.x() / self._region_scale,
                    rect.y() / self._region_scale,
                    rect.right() / self._region_scale,
                    rect.bottom() / self._region_scale,
                )
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip)
                progress.report(80, "保存")
                if path.lower().endswith((".jpg", ".jpeg")):
                    pix.save(path, jpg_quality=self._r_quality.value())
                else:
                    pix.save(path)
            finally:
                doc.close()
            return path

        def _done(_p) -> None:
            info(self, "导出完成", f"{path}\n{human_size(os.path.getsize(path))}")

        self.run("导出选区", _work, on_done=_done)


def create(parent, doc: PdfDoc) -> ExtractImagesDialog:
    return ExtractImagesDialog(parent, doc)
