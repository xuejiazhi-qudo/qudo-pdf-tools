"""PDF 添加页码与页眉页脚。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSlider,
    QSpinBox,
)

from ...core.doc import PdfDoc
from ...core.ops import stamp
from ..widgets import ColorButton, info, warn
from .base import ToolDialog

POSITIONS = [
    ("top-left", "左上"), ("top-center", "上中"), ("top-right", "右上"),
    ("bottom-left", "左下"), ("bottom-center", "下中"), ("bottom-right", "右下"),
]


class PageNumbersDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 添加页码", 640, 760)
        self.set_run_text("添加页码")

        pos_group = QGroupBox("位置")
        pl = QFormLayout(pos_group)
        pl.setLabelAlignment(Qt.AlignRight)
        self._position = QComboBox()
        for key, label in POSITIONS:
            self._position.addItem(label, key)
        self._position.setCurrentIndex(4)
        pl.addRow("页码位置", self._position)
        self._pos_mode = QComboBox()
        self._pos_mode.addItems(["same", "mirror"])
        self._pos_mode.currentTextChanged.connect(self._sync)
        pl.addRow("奇偶排版", self._pos_mode)
        self._mirror_odd = QComboBox()
        for key, label in POSITIONS:
            self._mirror_odd.addItem(label, key)
        self._mirror_odd.setCurrentIndex(5)
        pl.addRow("奇数页", self._mirror_odd)
        self._mirror_even = QComboBox()
        for key, label in POSITIONS:
            self._mirror_even.addItem(label, key)
        self._mirror_even.setCurrentIndex(3)
        pl.addRow("偶数页", self._mirror_even)
        self.add(pos_group)

        num_group = QGroupBox("编号")
        nl = QFormLayout(num_group)
        nl.setLabelAlignment(Qt.AlignRight)
        self._fmt = QComboBox()
        for key, label in stamp.FORMAT_LABELS.items():
            self._fmt.addItem(label, key)
        self._fmt.currentIndexChanged.connect(self._sync)
        nl.addRow("格式", self._fmt)
        self._template = QLineEdit("{page} / {pages}")
        self._template.setPlaceholderText("支持 {page} {pages} {documentPage} {documentPages} {filename}")
        nl.addRow("自定义模板", self._template)
        self._start = QSpinBox()
        self._start.setRange(1, 99999)
        nl.addRow("起始编号", self._start)
        self._skip = QSpinBox()
        self._skip.setRange(0, 9999)
        nl.addRow("跳过前 N 页", self._skip)
        self._range_mode = QComboBox()
        for key, label in (
            ("all", "全部页"), ("except-cover", "跳过封面"),
            ("odd", "奇数页"), ("even", "偶数页"), ("custom", "自定义范围"),
        ):
            self._range_mode.addItem(label, key)
        self._range_mode.currentIndexChanged.connect(self._sync)
        nl.addRow("应用范围", self._range_mode)
        self._custom_range = QLineEdit()
        self._custom_range.setPlaceholderText("如 2-10,15")
        nl.addRow("自定义范围", self._custom_range)
        self._numbering = QComboBox()
        self._numbering.addItems(["continuous", "original"])
        nl.addRow("编号方式", self._numbering)
        self._use_total = QCheckBox("「共 N 页」使用文档总页数")
        nl.addRow("", self._use_total)
        self.add(num_group)

        style_group = QGroupBox("样式")
        sl = QFormLayout(style_group)
        sl.setLabelAlignment(Qt.AlignRight)
        self._font = QComboBox()
        self._font.addItems(list(stamp.FONT_MAP.keys()))
        sl.addRow("字体", self._font)
        self._size = QSlider(Qt.Horizontal)
        self._size.setRange(6, 72)
        self._size.setValue(10)
        self._size.valueChanged.connect(lambda v: self._size_label.setText(f"{v} pt"))
        self._size_label = QLabel("10 pt")
        srow = QHBoxLayout()
        srow.addWidget(self._size, 1)
        srow.addWidget(self._size_label)
        sl.addRow("字号", srow)
        self._color = ColorButton("#444444")
        sl.addRow("颜色", self._color)
        self._opacity = QSlider(Qt.Horizontal)
        self._opacity.setRange(10, 100)
        self._opacity.setValue(100)
        self._opacity.valueChanged.connect(lambda v: self._op_label.setText(f"{v}%"))
        self._op_label = QLabel("100%")
        orow = QHBoxLayout()
        orow.addWidget(self._opacity, 1)
        orow.addWidget(self._op_label)
        sl.addRow("不透明度", orow)
        self._bold = QCheckBox("粗体")
        sl.addRow("", self._bold)
        self.add(style_group)

        hf_group = QGroupBox("页眉页脚（支持同样的占位符）")
        hl = QFormLayout(hf_group)
        hl.setLabelAlignment(Qt.AlignRight)
        self._header_left = QLineEdit()
        self._header_center = QLineEdit()
        self._header_right = QLineEdit()
        self._footer_left = QLineEdit()
        self._footer_center = QLineEdit()
        self._footer_right = QLineEdit()
        hl.addRow("页眉 左/中/右", self._header_left)
        hl.addRow("", self._header_center)
        hl.addRow("", self._header_right)
        hl.addRow("页脚 左/中/右", self._footer_left)
        hl.addRow("", self._footer_center)
        hl.addRow("", self._footer_right)
        self.add(hf_group)

        adv_group = QGroupBox("边距与偏移（pt）")
        al = QFormLayout(adv_group)
        al.setLabelAlignment(Qt.AlignRight)
        self._mt = QDoubleSpinBox()
        self._mt.setRange(0, 200)
        self._mt.setValue(24)
        al.addRow("上边距", self._mt)
        self._mb = QDoubleSpinBox()
        self._mb.setRange(0, 200)
        self._mb.setValue(24)
        al.addRow("下边距", self._mb)
        self._mlr = QDoubleSpinBox()
        self._mlr.setRange(0, 200)
        self._mlr.setValue(32)
        al.addRow("左右边距", self._mlr)
        self._ox = QDoubleSpinBox()
        self._ox.setRange(-200, 200)
        al.addRow("X 偏移", self._ox)
        self._oy = QDoubleSpinBox()
        self._oy.setRange(-200, 200)
        al.addRow("Y 偏移", self._oy)
        self.add(adv_group)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        mirror = self._pos_mode.currentText() == "mirror"
        self._mirror_odd.setVisible(mirror)
        self._mirror_even.setVisible(mirror)
        self._position.setVisible(not mirror)
        self._template.setVisible(self._fmt.currentData() == stamp.FMT_CUSTOM)
        self._custom_range.setVisible(self._range_mode.currentData() == "custom")

    def _settings(self) -> stamp.PageNumberSettings:
        range_mode = self._range_mode.currentData()
        if range_mode == "custom":
            from ...core import pagerange

            pagerange.parse(self._custom_range.text(), self.doc.page_count)

        return stamp.PageNumberSettings(
            position=self._position.currentData(),
            position_mode=self._pos_mode.currentText(),
            mirror_odd=self._mirror_odd.currentData(),
            mirror_even=self._mirror_even.currentData(),
            fmt=self._fmt.currentData(),
            custom_template=self._template.text(),
            start_number=self._start.value(),
            skip_pages=self._skip.value(),
            page_range_mode=range_mode,
            custom_range=self._custom_range.text(),
            numbering_mode=self._numbering.currentText(),
            use_document_total=self._use_total.isChecked(),
            font=self._font.currentText(),
            font_size=float(self._size.value()),
            color=self._color.rgb01(),
            opacity=self._opacity.value() / 100.0,
            bold=self._bold.isChecked(),
            header_left=self._header_left.text(),
            header_center=self._header_center.text(),
            header_right=self._header_right.text(),
            footer_left=self._footer_left.text(),
            footer_center=self._footer_center.text(),
            footer_right=self._footer_right.text(),
            margin_top=self._mt.value(),
            margin_bottom=self._mb.value(),
            margin_lr=self._mlr.value(),
            offset_x=self._ox.value(),
            offset_y=self._oy.value(),
        )

    def on_run(self) -> None:
        try:
            settings = self._settings()
        except Exception as exc:  # noqa: BLE001
            warn(self, "设置无效", str(exc))
            return

        self.doc.snapshot()

        def _done(report) -> None:
            self.doc.mark_dirty()
            info(self, "页码已添加", f"处理 {report['processed']} 页，跳过 {report['skipped']} 页。记得保存。")

        self.run("添加页码", stamp.apply_page_numbers, self.doc.fitz_doc, settings, on_done=_done)


def create(parent, doc: PdfDoc) -> PageNumbersDialog:
    return PageNumbersDialog(parent, doc)
