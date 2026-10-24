"""工具对话框共用的控件。"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core import pagerange


def form(rows: Sequence[Tuple[str, QWidget]]) -> QFormLayout:
    layout = QFormLayout()
    layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    for label, widget in rows:
        layout.addRow(label, widget)
    return layout


def hbox(*widgets: QWidget, spacing: int = 6, stretch_last: bool = False) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    for w in widgets:
        layout.addWidget(w)
    if stretch_last:
        layout.addStretch(1)
    return layout


def vbox(*widgets: QWidget, spacing: int = 8, margins: int = 10) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(margins, margins, margins, margins)
    for w in widgets:
        layout.addWidget(w)
    return layout


def primary(text: str, slot=None) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("primary", True)
    if slot:
        btn.clicked.connect(slot)
    return btn


def danger(text: str, slot=None) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("danger", True)
    if slot:
        btn.clicked.connect(slot)
    return btn


class ColorButton(QPushButton):
    colorChanged = Signal(str)

    def __init__(self, initial: str = "#000000", parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(initial)
        self.setFixedWidth(64)
        self.setFixedHeight(26)
        self.clicked.connect(self._pick)
        self._refresh()

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "选择颜色")
        if c.isValid():
            self._color = c
            self._refresh()
            self.colorChanged.emit(self.hex())

    def _refresh(self) -> None:
        pix = QPixmap(20, 20)
        pix.fill(self._color)
        self.setIcon(QIcon(pix))
        self.setToolTip(self.hex())

    def hex(self) -> str:
        return self._color.name()

    def rgb01(self) -> Tuple[float, float, float]:
        return (self._color.redF(), self._color.greenF(), self._color.blueF())

    def set_hex(self, value: str) -> None:
        self._color = QColor(value)
        self._refresh()


class OutputPathField(QWidget):
    """输出路径输入 + 浏览按钮。"""

    def __init__(self, placeholder: str = "选择输出位置", is_dir: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._is_dir = is_dir
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        btn = QPushButton("浏览…")
        btn.clicked.connect(self.browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.edit, 1)
        layout.addWidget(btn)

    def browse(self) -> None:
        if self._is_dir:
            path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "保存", self.edit.text() or "")
        if path:
            self.edit.setText(path)

    def text(self) -> str:
        return self.edit.text().strip()

    def set_text(self, value: str) -> None:
        self.edit.setText(value)


class PageScopeWidget(QGroupBox):
    """页面范围选择：全部 / 当前页 / 已选页 / 奇数 / 偶数 / 自定义。"""

    SCOPE_ALL = "all"
    SCOPE_CURRENT = "current"
    SCOPE_SELECTED = "selected"
    SCOPE_ODD = "odd"
    SCOPE_EVEN = "even"
    SCOPE_CUSTOM = "custom"

    def __init__(self, title: str = "应用范围", include_selected: bool = True, parent=None) -> None:
        super().__init__(title, parent)
        self._buttons = {}
        grid = QGridLayout(self)
        options = [
            (self.SCOPE_ALL, "全部页"),
            (self.SCOPE_CURRENT, "当前页"),
        ]
        if include_selected:
            options.append((self.SCOPE_SELECTED, "缩略图已选页"))
        options += [
            (self.SCOPE_ODD, "奇数页"),
            (self.SCOPE_EVEN, "偶数页"),
            (self.SCOPE_CUSTOM, "自定义"),
        ]
        for i, (key, label) in enumerate(options):
            btn = QRadioButton(label)
            btn.setChecked(key == self.SCOPE_ALL)
            self._buttons[key] = btn
            grid.addWidget(btn, i // 3, i % 3)

        self.custom = QLineEdit()
        self.custom.setPlaceholderText("如 1-3,5,8-")
        self._buttons[self.SCOPE_CUSTOM].toggled.connect(self.custom.setEnabled)
        self.custom.setEnabled(False)
        grid.addWidget(self.custom, 2, 0, 1, 3)

    def scope(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return self.SCOPE_ALL

    def resolve(
        self,
        page_count: int,
        current: int = 0,
        selected: Optional[Sequence[int]] = None,
    ) -> List[int]:
        scope = self.scope()
        if scope == self.SCOPE_ALL:
            return list(range(page_count))
        if scope == self.SCOPE_CURRENT:
            return [current] if 0 <= current < page_count else []
        if scope == self.SCOPE_SELECTED:
            return list(selected or [])
        if scope == self.SCOPE_ODD:
            return list(range(0, page_count, 2))
        if scope == self.SCOPE_EVEN:
            return list(range(1, page_count, 2))
        return pagerange.parse(self.custom.text(), page_count)


class PagePickDialog(QDialog):
    """针对外部 PDF 文件的页面多选对话框（缩略图网格）。"""

    def __init__(self, pdf_path: str, parent=None, title: str = "选择页面") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 560)
        self._path = pdf_path
        self.selected: List[int] = []

        import pymupdf

        self._doc = pymupdf.open(pdf_path)

        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        for text, slot in (
            ("全选", lambda: self._set(list(range(self._doc.page_count)))),
            ("不选", lambda: self._set([])),
            ("反选", self._invert),
            ("奇数页", lambda: self._set(list(range(0, self._doc.page_count, 2)))),
            ("偶数页", lambda: self._set(list(range(1, self._doc.page_count, 2)))),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            bar.addWidget(btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._range = QLineEdit()
        self._range.setPlaceholderText("页码范围，如 1-3,5")
        self._range.returnPressed.connect(self._apply_range)
        layout.addWidget(self._range)

        self._list = QListWidget()
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._list.setResizeMode(QListWidget.Adjust)
        self._list.setSpacing(4)
        self._list.setUniformItemSizes(True)
        self._list.setGridSize(QSize(142, 183))
        self._list.setIconSize(QSize(130, 175))
        layout.addWidget(self._list, 1)

        for i in range(self._doc.page_count):
            page = self._doc.load_page(i)
            rect = page.rect
            zoom = 130 / max(rect.width, rect.height, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = QImage(
                pix.samples, pix.width, pix.height, pix.stride,
                QImage.Format_RGB888,
            ).copy()
            item = QListWidgetItem("")
            item.setIcon(thumb_icon(img, 130, 175, badge=str(i + 1)))
            item.setToolTip(str(i + 1))
            item.setData(Qt.UserRole, i)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._list.addItem(item)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set(self, pages: Sequence[int]) -> None:
        wanted = set(pages)
        self._list.blockSignals(True)
        for r in range(self._list.count()):
            self._list.item(r).setSelected(self._list.item(r).data(Qt.UserRole) in wanted)
        self._list.blockSignals(False)

    def _invert(self) -> None:
        cur = {self._list.row(i) for i in self._list.selectedItems()}
        self._set([r for r in range(self._list.count()) if r not in cur])

    def _apply_range(self) -> None:
        try:
            pages = pagerange.parse(self._range.text(), self._doc.page_count)
        except pagerange.PageRangeError as exc:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning(self, "页码范围无效", str(exc))
            return
        self._set(pages)

    def _accept(self) -> None:
        self.selected = sorted(
            self._list.item(self._list.row(i)).data(Qt.UserRole)
            for i in self._list.selectedItems()
        )
        self._doc.close()
        self.accept()

    def reject(self) -> None:  # noqa: D102
        self._doc.close()
        super().reject()


def ask_open_pdf(parent, caption: str = "打开 PDF") -> Optional[str]:
    from .. import i18n

    path, _ = QFileDialog.getOpenFileName(
        parent, i18n.translate(caption), "",
        i18n.translate("PDF 文件 (*.pdf);;所有文件 (*)"),
    )
    return path or None


def ask_open_images(parent) -> List[str]:
    from .. import i18n

    paths, _ = QFileDialog.getOpenFileNames(
        parent, i18n.translate("选择图片"), "",
        i18n.translate("图片 (*.png *.jpg *.jpeg *.webp *.bmp *.gif);;所有文件 (*)"),
    )
    return paths


def ask_save(parent, caption: str, suffix: str, default_name: str = "") -> Optional[str]:
    from .. import i18n

    path, _ = QFileDialog.getSaveFileName(
        parent, i18n.translate(caption), default_name,
        i18n.translate(f"{suffix} (*.{suffix});;所有文件 (*)"),
    )
    return path or None


def ask_dir(parent, caption: str = "选择输出目录") -> Optional[str]:
    from .. import i18n

    return QFileDialog.getExistingDirectory(parent, i18n.translate(caption)) or None


def thumb_icon(source, width: int = 140, height: int = 190, badge: Optional[str] = None):
    """把任意尺寸的页面图统一成固定大小图标（白底 + 等比居中 + 细边框）。

    横页/竖页混排时直接用原始 QIcon 会让网格忽宽忽窄，看起来凌乱。
    badge 非空时在底部居中画半透明页码角标（页码放进画布，
    就不会和列表项文字分离或被相邻格子遮挡）。
    """
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QFont, QPainter, QPen

    pix = QPixmap.fromImage(source) if isinstance(source, QImage) else source
    canvas = QPixmap(width, height)
    canvas.fill(QColor(255, 255, 255))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    painter.setRenderHint(QPainter.Antialiasing, True)
    target = QRectF(3, 3, width - 6, height - 6)
    sr = QRectF(pix.rect())
    scale = min(target.width() / sr.width(), target.height() / sr.height())
    w = sr.width() * scale
    h = sr.height() * scale
    dest = QRectF(
        target.x() + (target.width() - w) / 2,
        target.y() + (target.height() - h) / 2,
        w,
        h,
    )
    painter.drawPixmap(dest, pix, sr)
    painter.setPen(QPen(QColor(200, 204, 210), 1))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(dest.adjusted(-0.5, -0.5, 0.5, 0.5))

    if badge:
        font = QFont(painter.font())
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(badge)
        bw = tw + 12
        bh = 18
        bx = dest.center().x() - bw / 2
        by = dest.bottom() - bh - 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(30, 34, 40, 175))
        painter.drawRoundedRect(QRectF(bx, by, bw, bh), 4, 4)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            QRectF(bx, by, bw, bh), Qt.AlignCenter, badge
        )
    painter.end()
    return QIcon(canvas)


def info(parent, title: str, text: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    from .. import i18n

    QMessageBox.information(parent, i18n.translate(title), i18n.translate(text))


def warn(parent, title: str, text: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    from .. import i18n

    QMessageBox.warning(parent, i18n.translate(title), i18n.translate(text))


def error(parent, title: str, text: str) -> None:
    from PySide6.QtWidgets import QMessageBox

    from .. import i18n

    QMessageBox.critical(parent, i18n.translate(title), i18n.translate(text))
