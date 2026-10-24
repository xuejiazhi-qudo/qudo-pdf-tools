"""签名对话框：手写板 / 打字 / 上传图片。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.ops import stamp
from ..widgets import ColorButton


class SignaturePad(QWidget):
    """手写签名板，记录带压感的笔画。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 200)
        self.setStyleSheet("background:#ffffff; border:1px solid #c9ced6; border-radius:6px;")
        self._strokes: List[List[Tuple[float, float, float]]] = []
        self._current: List[Tuple[float, float, float]] = []
        self._redo: List[List[Tuple[float, float, float]]] = []
        self.pen_color = QColor(0, 0, 0)
        self.pen_width = 2.0

    def strokes(self):
        return [s for s in self._strokes if s]

    def clear(self) -> None:
        self._strokes.clear()
        self._current = []
        self._redo.clear()
        self.update()

    def undo(self) -> None:
        if self._strokes:
            self._redo.append(self._strokes.pop())
            self.update()

    def redo(self) -> None:
        if self._redo:
            self._strokes.append(self._redo.pop())
            self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._current = [(event.position().x(), event.position().y(), 1.0)]
            self._redo.clear()
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._current:
            self._current.append((event.position().x(), event.position().y(), 1.0))
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._current:
            self._strokes.append(self._current)
            self._current = []
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(self.pen_color)
        pen.setWidthF(self.pen_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        for stroke in self._strokes + ([self._current] if self._current else []):
            if len(stroke) >= 2:
                for a, b in zip(stroke, stroke[1:]):
                    painter.drawLine(QPoint(int(a[0]), int(a[1])), QPoint(int(b[0]), int(b[1])))
        painter.end()


class SignatureDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("插入签名")
        self.resize(560, 460)
        self.result_bytes: Optional[bytes] = None

        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # ---- 手写
        draw = QWidget()
        dl = QVBoxLayout(draw)
        self._pad = SignaturePad()
        dl.addWidget(self._pad, 1)
        bar = QHBoxLayout()
        self._pen_color = ColorButton("#000000")
        self._pen_color.colorChanged.connect(self._sync_pen)
        bar.addWidget(QLabel("笔色"))
        bar.addWidget(self._pen_color)
        self._pen_width = QSlider(Qt.Horizontal)
        self._pen_width.setRange(1, 6)
        self._pen_width.setValue(2)
        self._pen_width.valueChanged.connect(self._sync_pen)
        bar.addWidget(QLabel("笔宽"))
        bar.addWidget(self._pen_width, 1)
        for text, slot in (("撤销", self._pad.undo), ("重做", self._pad.redo), ("清空", self._pad.clear)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        dl.addLayout(bar)
        tabs.addTab(draw, "手写")

        # ---- 打字
        typed = QWidget()
        tl = QFormLayout(typed)
        self._name = QLineEdit()
        self._name.setPlaceholderText("输入姓名")
        tl.addRow("姓名", self._name)
        self._font = QComboBox()
        self._font.addItems(["系统手写体", "黑体", "宋体", "楷体"])
        tl.addRow("字体", self._font)
        self._tsize = QSpinBox()
        self._tsize.setRange(16, 96)
        self._tsize.setValue(48)
        tl.addRow("字号", self._tsize)
        self._tcolor = ColorButton("#000000")
        tl.addRow("颜色", self._tcolor)
        self._slant = QSpinBox()
        self._slant.setRange(-30, 30)
        tl.addRow("倾斜", self._slant)
        tabs.addTab(typed, "打字")

        # ---- 上传
        upload = QWidget()
        ul = QFormLayout(upload)
        pick = QPushButton("选择签名图片…")
        pick.clicked.connect(self._pick)
        self._file_label = QLabel("未选择")
        ur = QHBoxLayout()
        ur.addWidget(pick)
        ur.addWidget(self._file_label, 1)
        ul.addRow("图片", ur)
        self._remove_white = QCheckBox("抠除白底")
        self._remove_white.setChecked(True)
        ul.addRow("", self._remove_white)
        self._tolerance = QSpinBox()
        self._tolerance.setRange(0, 120)
        self._tolerance.setValue(30)
        ul.addRow("白底容差", self._tolerance)
        self._crop = QCheckBox("裁掉四周空白")
        self._crop.setChecked(True)
        ul.addRow("", self._crop)
        tabs.addTab(upload, "上传")

        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._image_path: Optional[str] = None
        self._tabs = tabs

    def _sync_pen(self, *_args) -> None:
        self._pad.pen_color = QColor(self._pen_color.hex())
        self._pad.pen_width = float(self._pen_width.value())

    def _pick(self) -> None:
        path = QFileDialog.getOpenFileName(self, "选择签名图片", "", "图片 (*.png *.jpg *.jpeg *.webp)")[0]
        if path:
            self._image_path = path
            import os

            self._file_label.setText(os.path.basename(path))

    def _font_path(self) -> Optional[str]:
        mapping = {
            "系统手写体": None,
            "黑体": "C:/Windows/Fonts/msyh.ttc",
            "宋体": "C:/Windows/Fonts/simsun.ttc",
            "楷体": "C:/Windows/Fonts/simkai.ttf",
        }
        return mapping.get(self._font.currentText())

    def _accept(self) -> None:
        idx = self._tabs.currentIndex()
        try:
            if idx == 0:
                strokes = self._pad.strokes()
                if not strokes:
                    return
                data = stamp.render_signature_image(
                    strokes, self._pad.width(), self._pad.height(),
                    pen_color=(self._pad.pen_color.red(), self._pad.pen_color.green(), self._pad.pen_color.blue()),
                    pen_width=self._pad.pen_width,
                    crop_whitespace=True,
                )
            elif idx == 1:
                name = self._name.text().strip()
                if not name:
                    return
                s = self._tcolor.hex().lstrip("#")
                data = stamp.render_typed_signature(
                    name,
                    font_path=self._font_path(),
                    font_size=self._tsize.value(),
                    color=(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)),
                    slant=float(self._slant.value()),
                )
            else:
                if not self._image_path:
                    return
                with open(self._image_path, "rb") as fh:
                    data = fh.read()
                if self._remove_white.isChecked():
                    data = stamp.remove_white_background(
                        data, tolerance=self._tolerance.value(),
                        crop_whitespace=self._crop.isChecked(),
                    )
        except Exception as exc:  # noqa: BLE001
            from ..widgets import error as show_error

            show_error(self, "生成签名失败", str(exc))
            return

        self.result_bytes = data
        self.accept()


def get_signature(parent) -> Optional[bytes]:
    dlg = SignatureDialog(parent)
    if dlg.exec() == QDialog.Accepted and dlg.result_bytes:
        return dlg.result_bytes
    return None
