"""创建和放置 PDF 印章。"""

from __future__ import annotations

import datetime as dt
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from ...core.doc import PdfDoc
from ...core.ops import seal as seal_ops
from .. import i18n
from ..widgets import PageScopeWidget, info, warn
from .base import ToolDialog


class SealDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 印章", 620, 780)
        self.set_run_text("盖章")
        self._image_path = ""
        self._image_aspect = 1.0
        self._preview_bytes = b""

        source = QGroupBox("印章来源")
        source_form = QFormLayout(source)
        source_form.setLabelAlignment(Qt.AlignRight)
        self._source = QComboBox()
        self._source.addItem("直接制作印章", "create")
        self._source.addItem("上传印章图片", "image")
        self._source.currentIndexChanged.connect(self._sync_source)
        source_form.addRow("来源", self._source)
        self._image_row = QHBoxLayout()
        self._image_field = QLineEdit()
        self._image_field.setReadOnly(True)
        browse = QPushButton("选择图片…")
        browse.clicked.connect(self._choose_image)
        self._image_row.addWidget(self._image_field, 1)
        self._image_row.addWidget(browse)
        source_form.addRow("图片", self._image_row)
        self.add(source)

        self._design_group = QGroupBox("制作印章")
        design = QFormLayout(self._design_group)
        design.setLabelAlignment(Qt.AlignRight)
        self._shape = QComboBox()
        for key, label in (("circle", "圆形"), ("oval", "椭圆"), ("square", "方形"), ("rectangle", "长方形")):
            self._shape.addItem(label, key)
        self._shape.currentIndexChanged.connect(self._shape_changed)
        design.addRow("形状", self._shape)
        default_main_text = "Company Name" if i18n.get_lang() == i18n.LANG_EN else "公司名称"
        self._main_text = QLineEdit(default_main_text)
        self._main_text.textChanged.connect(self._refresh_preview)
        design.addRow("主文字", self._main_text)
        self._second_text = QLineEdit()
        self._second_text.setPlaceholderText("可选，例如：合同专用章")
        self._second_text.textChanged.connect(self._refresh_preview)
        design.addRow("第二行文字", self._second_text)
        self._star = QCheckBox("添加五角星")
        self._star.setChecked(True)
        self._star.toggled.connect(self._refresh_preview)
        design.addRow("图案", self._star)
        self._date_enabled = QCheckBox("添加日期")
        self._date_enabled.toggled.connect(self._date_changed)
        design.addRow("日期", self._date_enabled)
        self._date_text = QLineEdit(dt.date.today().strftime("%Y.%m.%d"))
        self._date_text.setEnabled(False)
        self._date_text.textChanged.connect(self._refresh_preview)
        design.addRow("日期内容", self._date_text)
        self._style = QComboBox()
        self._style.addItem("朱文（红字透明底）", "zhuwen")
        self._style.addItem("白文（白字红底）", "baiwen")
        self._style.currentIndexChanged.connect(self._refresh_preview)
        design.addRow("印文", self._style)
        self.add(self._design_group)

        self._preview = QLabel("印章预览")
        self._preview.setAlignment(Qt.AlignCenter)
        self._preview.setMinimumSize(170, 150)
        self._preview.setMaximumHeight(190)
        self._preview.setStyleSheet("QLabel { background: #ffffff; border: 1px solid #d5d9df; border-radius: 5px; }")
        self.add(self._preview)

        size_group = QGroupBox("印章尺寸")
        size_form = QFormLayout(size_group)
        size_form.setLabelAlignment(Qt.AlignRight)
        self._width = QDoubleSpinBox()
        self._width.setRange(3, 300)
        self._width.setDecimals(1)
        self._width.setSuffix(" mm")
        self._width.setValue(30)
        self._width.valueChanged.connect(self._width_changed)
        self._height = QDoubleSpinBox()
        self._height.setRange(3, 300)
        self._height.setDecimals(1)
        self._height.setSuffix(" mm")
        self._height.setValue(30)
        self._height.valueChanged.connect(self._height_changed)
        self._keep_ratio = QCheckBox("锁定图片比例")
        self._keep_ratio.setChecked(True)
        self._keep_ratio.toggled.connect(self._sync_shape_size)
        size_form.addRow("宽度", self._width)
        size_form.addRow("高度", self._height)
        size_form.addRow("图片", self._keep_ratio)
        self.add(size_group)

        placement = QGroupBox("盖章方式与位置")
        place = QFormLayout(placement)
        place.setLabelAlignment(Qt.AlignRight)
        self._mode = QComboBox()
        self._mode.addItem("普通盖章", "normal")
        self._mode.addItem("骑缝章", "seam")
        self._mode.currentIndexChanged.connect(self._sync_mode)
        place.addRow("方式", self._mode)
        self._position = QComboBox()
        for key, label in (
            ("tl", "左上"), ("tc", "上中"), ("tr", "右上"),
            ("ml", "左中"), ("mc", "正中"), ("mr", "右中"),
            ("bl", "左下"), ("bc", "下中"), ("br", "右下"),
        ):
            self._position.addItem(label, key)
        self._position.setCurrentIndex(8)
        place.addRow("普通位置 / 垂直位置", self._position)
        self._margin = QDoubleSpinBox()
        self._margin.setRange(0, 100)
        self._margin.setDecimals(1)
        self._margin.setSuffix(" mm")
        self._margin.setValue(12)
        place.addRow("距页边", self._margin)
        self._edge = QComboBox()
        self._edge.addItem("右侧页缘", "right")
        self._edge.addItem("左侧页缘", "left")
        place.addRow("骑缝方向", self._edge)
        self._seam_depth = QDoubleSpinBox()
        self._seam_depth.setRange(1, 100)
        self._seam_depth.setDecimals(1)
        self._seam_depth.setSuffix(" mm（所选页合计）")
        self._seam_depth.setValue(10)
        place.addRow("骑缝总宽度", self._seam_depth)
        self._hint = QLabel("普通盖章按设置的毫米尺寸放置。")
        self._hint.setWordWrap(True)
        place.addRow("说明", self._hint)
        self.add(placement)

        self._scope = PageScopeWidget(include_selected=False)
        self.add(self._scope)
        self.add_stretch()
        self._sync_source()
        self._sync_mode()
        self._refresh_preview()

    def _design(self) -> seal_ops.SealDesign:
        return seal_ops.SealDesign(
            shape=self._shape.currentData(),
            main_text=self._main_text.text(),
            secondary_text=self._second_text.text(),
            add_star=self._star.isChecked(),
            date_text=self._date_text.text(),
            add_date=self._date_enabled.isChecked(),
            style=self._style.currentData(),
        )

    def _sync_source(self, *_args) -> None:
        is_image = self._source.currentData() == "image"
        self._image_field.setVisible(is_image)
        self._design_group.setVisible(not is_image)
        self._keep_ratio.setVisible(is_image)
        self._sync_shape_size()
        self._refresh_preview()

    def _sync_mode(self, *_args) -> None:
        is_seam = self._mode.currentData() == "seam"
        self._position.setVisible(not is_seam)
        self._edge.setVisible(is_seam)
        self._seam_depth.setVisible(is_seam)
        hint = (
            "将图片按所选页数切成竖向条带，依页序盖在同一侧页缘；骑缝范围应为连续页。"
            if is_seam else "普通盖章按设置的毫米尺寸放置。"
        )
        self._hint.setText(i18n.translate(hint))

    def _shape_changed(self, *_args) -> None:
        self._sync_shape_size()
        self._refresh_preview()

    def _sync_shape_size(self) -> None:
        fixed = self._source.currentData() == "create" and self._shape.currentData() in ("circle", "square")
        self._height.setEnabled(not fixed and not (self._source.currentData() == "image" and self._keep_ratio.isChecked()))
        if fixed:
            self._height.blockSignals(True)
            self._height.setValue(self._width.value())
            self._height.blockSignals(False)
        elif self._source.currentData() == "image" and self._keep_ratio.isChecked():
            self._height.blockSignals(True)
            self._height.setValue(self._width.value() / max(0.01, self._image_aspect))
            self._height.blockSignals(False)

    def _width_changed(self, *_args) -> None:
        if self._source.currentData() == "image" and self._keep_ratio.isChecked():
            self._height.blockSignals(True)
            self._height.setValue(self._width.value() / max(0.01, self._image_aspect))
            self._height.blockSignals(False)
        elif self._source.currentData() == "create" and self._shape.currentData() in ("circle", "square"):
            self._height.blockSignals(True)
            self._height.setValue(self._width.value())
            self._height.blockSignals(False)

    def _height_changed(self, *_args) -> None:
        if self._source.currentData() == "image" and self._keep_ratio.isChecked():
            self._width.blockSignals(True)
            self._width.setValue(self._height.value() * self._image_aspect)
            self._width.blockSignals(False)
        elif self._source.currentData() == "create" and self._shape.currentData() in ("circle", "square"):
            self._width.blockSignals(True)
            self._width.setValue(self._height.value())
            self._width.blockSignals(False)

    def _date_changed(self, checked: bool) -> None:
        self._date_text.setEnabled(checked)
        self._refresh_preview()

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, i18n.translate("选择印章图片"), "",
            i18n.translate("图片 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)")
        )
        if not path:
            return
        try:
            _data, self._image_aspect = seal_ops.load_image_bytes(path)
        except Exception as exc:  # noqa: BLE001
            warn(self, "图片读取失败", str(exc))
            return
        self._image_path = path
        self._image_field.setText(os.path.basename(path))
        self._image_field.setToolTip(path)
        self._sync_shape_size()
        self._refresh_preview()

    def _refresh_preview(self, *_args) -> None:
        if self._source.currentData() == "image":
            if not self._image_path:
                self._preview.setPixmap(QPixmap())
                self._preview.setText("选择图片后预览")
                return
            try:
                data, _aspect = seal_ops.load_image_bytes(self._image_path)
            except Exception:
                return
        else:
            try:
                data = seal_ops.render_seal_png(self._design(), self._width.value(), self._height.value(), dpi=180)
            except Exception:
                self._preview.setPixmap(QPixmap())
                self._preview.setText("请输入印章主文字")
                return
        self._preview_bytes = data
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        self._preview.setText("")
        self._preview.setPixmap(pixmap.scaled(
            self._preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        preview_bytes = getattr(self, "_preview_bytes", b"")
        preview = getattr(self, "_preview", None)
        if preview_bytes and preview is not None:
            pixmap = QPixmap()
            pixmap.loadFromData(preview_bytes, "PNG")
            preview.setPixmap(pixmap.scaled(
                preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            ))

    def _image_bytes(self) -> bytes:
        if self._source.currentData() == "image":
            data, self._image_aspect = seal_ops.load_image_bytes(self._image_path)
            return data
        return seal_ops.render_seal_png(self._design(), self._width.value(), self._height.value())

    def on_run(self) -> None:
        try:
            image_bytes = self._image_bytes()
            targets = self._scope.resolve(
                self.doc.page_count, self.parent().view.current_page
            )
        except Exception as exc:  # noqa: BLE001
            warn(self, "印章设置无效", str(exc))
            return
        if not targets:
            warn(self, "印章设置无效", "没有可盖章的页面")
            return

        seam = self._mode.currentData() == "seam"
        self.doc.snapshot()

        def _done(count: int) -> None:
            self.doc.mark_dirty()
            info(self, "印章已添加", f"已在 {count} 页盖章。记得保存。")

        self.run_locked(
            "添加印章", seal_ops.apply_seal,
            self.doc.fitz_doc,
            image_bytes,
            self._width.value(),
            self._height.value(),
            pages=targets,
            position=self._position.currentData(),
            margin_mm=self._margin.value(),
            seam=seam,
            seam_edge=self._edge.currentData(),
            seam_depth_mm=self._seam_depth.value(),
            on_done=_done,
        )


def create(parent, doc: PdfDoc) -> SealDialog:
    return SealDialog(parent, doc)
