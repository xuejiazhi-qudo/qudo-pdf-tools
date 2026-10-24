"""PDF 加水印。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
)

from ...core.doc import PdfDoc
from ...core.ops import stamp
from .. import i18n
from ..widgets import ColorButton, OutputPathField, PageScopeWidget, info, warn
from .base import ToolDialog

GRID = [
    (stamp.POS_TL, "左上"), (stamp.POS_TC, "上中"), (stamp.POS_TR, "右上"),
    (stamp.POS_ML, "左中"), (stamp.POS_MC, "正中"), (stamp.POS_MR, "右中"),
    (stamp.POS_BL, "左下"), (stamp.POS_BC, "下中"), (stamp.POS_BR, "右下"),
]


class WatermarkDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 加水印", 620, 760)
        self.set_run_text("添加水印")

        type_group = QGroupBox("水印类型")
        tl = QHBoxLayout(type_group)
        self._type_text = QRadioButton("文字水印")
        self._type_image = QRadioButton("图片水印")
        self._type_text.setChecked(True)
        self._type_text.toggled.connect(self._sync)
        tl.addWidget(self._type_text)
        tl.addWidget(self._type_image)
        self.add(type_group)

        text_group = QGroupBox("文字")
        tgl = QFormLayout(text_group)
        tgl.setLabelAlignment(Qt.AlignRight)
        self._text = QLineEdit("CONFIDENTIAL")
        tgl.addRow("内容", self._text)
        self._size = QSlider(Qt.Horizontal)
        self._size.setRange(8, 200)
        self._size.setValue(48)
        self._size.valueChanged.connect(lambda v: self._size_label.setText(f"{v} pt"))
        self._size_label = QLabel("48 pt")
        srow = QHBoxLayout()
        srow.addWidget(self._size, 1)
        srow.addWidget(self._size_label)
        tgl.addRow("字号", srow)
        self._color = ColorButton("#999999")
        tgl.addRow("颜色", self._color)
        self._bold = QCheckBox("粗体")
        tgl.addRow("", self._bold)
        self.add(text_group)

        img_group = QGroupBox("图片")
        igl = QFormLayout(img_group)
        igl.setLabelAlignment(Qt.AlignRight)
        self._image = OutputPathField("选择水印图片（PNG 支持透明）")
        igl.addRow("图片", self._image)
        self._img_width = QSlider(Qt.Horizontal)
        self._img_width.setRange(5, 80)
        self._img_width.setValue(25)
        self._img_width.valueChanged.connect(lambda v: self._iw_label.setText(i18n.translate(f"{v}% 页宽")))
        self._iw_label = QLabel("25% 页宽")
        irow = QHBoxLayout()
        irow.addWidget(self._img_width, 1)
        irow.addWidget(self._iw_label)
        igl.addRow("宽度", irow)
        self.add(img_group)

        common = QGroupBox("外观与位置")
        cgl = QFormLayout(common)
        cgl.setLabelAlignment(Qt.AlignRight)
        self._opacity = QSlider(Qt.Horizontal)
        self._opacity.setRange(5, 100)
        self._opacity.setValue(25)
        self._opacity.valueChanged.connect(lambda v: self._op_label.setText(f"{v}%"))
        self._op_label = QLabel("25%")
        orow = QHBoxLayout()
        orow.addWidget(self._opacity, 1)
        orow.addWidget(self._op_label)
        cgl.addRow("不透明度", orow)
        self._rotation = QSlider(Qt.Horizontal)
        self._rotation.setRange(-180, 180)
        self._rotation.setValue(-45)
        self._rotation.valueChanged.connect(lambda v: self._rot_label.setText(f"{v}°"))
        self._rot_label = QLabel("-45°")
        rrow = QHBoxLayout()
        rrow.addWidget(self._rotation, 1)
        rrow.addWidget(self._rot_label)
        for deg in (-45, 0, 45, 90):
            btn = QPushButton(f"{deg}°")
            btn.setFixedWidth(44)
            btn.clicked.connect(lambda _=False, d=deg: self._rotation.setValue(d))
            rrow.addWidget(btn)
        cgl.addRow("旋转", rrow)

        grid = QGridLayout()
        self._pos_buttons = {}
        for i, (key, label) in enumerate(GRID):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == stamp.POS_MC)
            btn.clicked.connect(lambda _=False, b=btn, k=key: self._pick_pos(k, b))
            self._pos_buttons[key] = btn
            grid.addWidget(btn, i // 3, i % 3)
        cgl.addRow("位置", grid)

        self._hm = QDoubleSpinBox()
        self._hm.setRange(0, 400)
        self._hm.setValue(20)
        cgl.addRow("水平边距", self._hm)
        self._vm = QDoubleSpinBox()
        self._vm.setRange(0, 400)
        self._vm.setValue(20)
        cgl.addRow("垂直边距", self._vm)
        self._ox = QDoubleSpinBox()
        self._ox.setRange(-400, 400)
        cgl.addRow("X 偏移", self._ox)
        self._oy = QDoubleSpinBox()
        self._oy.setRange(-400, 400)
        cgl.addRow("Y 偏移", self._oy)

        self._mode = QComboBox()
        self._mode.addItems(["single", "tiled"])
        self._mode.currentTextChanged.connect(self._sync)
        cgl.addRow("排布", self._mode)
        self._sx = QSlider(Qt.Horizontal)
        self._sx.setRange(50, 300)
        self._sx.setValue(100)
        self._sy = QSlider(Qt.Horizontal)
        self._sy.setRange(50, 300)
        self._sy.setValue(100)
        cgl.addRow("平铺间距 X", self._sx)
        cgl.addRow("平铺间距 Y", self._sy)
        self._stagger = QCheckBox("错位平铺")
        cgl.addRow("", self._stagger)
        self._above = QCheckBox("置于内容上方（取消则垫在内容下）")
        self._above.setChecked(True)
        cgl.addRow("", self._above)
        self.add(common)

        self._scope = PageScopeWidget(include_selected=False)
        self.add(self._scope)
        self.add_stretch()
        self._sync()

    def _pick_pos(self, key: str, button: QPushButton) -> None:
        for other in self._pos_buttons.values():
            other.setChecked(other is button)

    def _current_pos(self) -> str:
        for key, btn in self._pos_buttons.items():
            if btn.isChecked():
                return key
        return stamp.POS_MC

    def _sync(self, *_args) -> None:
        is_text = self._type_text.isChecked()
        self._text.setVisible(is_text)
        self._size.setVisible(is_text)
        self._size_label.setVisible(is_text)
        self._color.setVisible(is_text)
        self._bold.setVisible(is_text)
        self._image.setVisible(not is_text)
        self._img_width.setVisible(not is_text)
        self._iw_label.setVisible(not is_text)
        tiled = self._mode.currentText() == "tiled"
        self._sx.setVisible(tiled)
        self._sy.setVisible(tiled)
        self._stagger.setVisible(tiled)

    def _settings(self) -> stamp.WatermarkSettings:
        image_bytes = None
        if self._type_image.isChecked():
            path = self._image.text()
            if not path:
                raise ValueError("请先选择水印图片")
            with open(path, "rb") as fh:
                image_bytes = fh.read()

        return stamp.WatermarkSettings(
            type="text" if self._type_text.isChecked() else "image",
            text=self._text.text(),
            font_size=float(self._size.value()),
            color=self._color.rgb01(),
            opacity=self._opacity.value() / 100.0,
            rotation=float(self._rotation.value()),
            bold=self._bold.isChecked(),
            image_bytes=image_bytes,
            image_width_pct=float(self._img_width.value()),
            position=self._current_pos(),
            h_margin=self._hm.value(),
            v_margin=self._vm.value(),
            offset_x=self._ox.value(),
            offset_y=self._oy.value(),
            mode=self._mode.currentText(),
            tile_spacing_x=float(self._sx.value()),
            tile_spacing_y=float(self._sy.value()),
            staggered=self._stagger.isChecked(),
            above_content=self._above.isChecked(),
        )

    def on_run(self) -> None:
        try:
            settings = self._settings()
            targets = self._scope.resolve(
                self.doc.page_count, self.parent().view.current_page
            )
        except Exception as exc:  # noqa: BLE001
            warn(self, "设置无效", str(exc))
            return
        settings.pages = targets

        self.doc.snapshot()

        def _done(count: int) -> None:
            self.doc.mark_dirty()
            info(self, "水印已添加", f"已处理 {count} 页。记得保存。")

        self.run("添加水印", stamp.apply_watermark, self.doc.fitz_doc, settings, on_done=_done)


def create(parent, doc: PdfDoc) -> WatermarkDialog:
    return WatermarkDialog(parent, doc)
