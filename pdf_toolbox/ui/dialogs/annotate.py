"""PDF 标注与批注：真实 PDF Annotation + 可选压平。"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from .. import i18n
from ...core.ops import annotate as ann
from ..viewer import PdfView
from ..widgets import ColorButton, danger, info, warn
from ..widgets.overlay import DragRectItem, InkItem

TOOL_BUTTONS = [
    ("select", "选择"),
    (ann.T_HIGHLIGHT, "高亮"),
    (ann.T_UNDERLINE, "下划线"),
    (ann.T_STRIKEOUT, "删除线"),
    (ann.T_FREEHAND, "画笔"),
    (ann.T_TEXT, "文字"),
    (ann.T_NOTE, "便签"),
    (ann.T_STAMP, "图章"),
    (ann.T_RECT, "矩形"),
    (ann.T_CIRCLE, "圆形"),
    (ann.T_LINE, "直线"),
    (ann.T_ARROW, "箭头"),
    (ann.T_IMAGE, "图片"),
]

CLICK_TOOLS = {ann.T_TEXT, ann.T_NOTE, ann.T_STAMP, ann.T_IMAGE}
DRAG_TOOLS = {ann.T_HIGHLIGHT, ann.T_UNDERLINE, ann.T_STRIKEOUT, ann.T_RECT, ann.T_CIRCLE}
LINE_TOOLS = {ann.T_LINE, ann.T_ARROW}


class AnnotateMode:
    """把鼠标事件转成标注创建/选择。"""

    def __init__(self, panel: "AnnotatePanel") -> None:
        self.panel = panel
        self.view: Optional[PdfView] = None
        self._overlay = None
        self._start_scene: Optional[QPointF] = None
        self._page: Optional[int] = None

    def attach(self, view: PdfView) -> None:
        self.view = view

    def detach(self) -> None:
        self._clear_overlay()

    def _clear_overlay(self) -> None:
        if self._overlay is not None and self.view is not None:
            self.view.scene().removeItem(self._overlay)
            self._overlay = None

    def mouse_press(self, event) -> bool:
        if event.button() != Qt.LeftButton or self.view is None:
            return False
        hit = self.view.view_to_page_point(event.position().toPoint())
        if hit is None:
            return False
        page, local = hit
        self._page = page
        self._start_scene = self.view.mapToScene(event.position().toPoint())
        tool = self.panel.tool

        if tool == "select":
            self.panel.select_at(page, local)
            return True

        if tool in CLICK_TOOLS:
            rect = QRectF(local.x(), local.y(), local.x() + 120, local.y() + 24)
            self.panel.create_from_rect(tool, page, rect)
            return True

        if tool == ann.T_FREEHAND:
            self._overlay = InkItem(self.panel.qcolor(), self.panel.line_width)
            self.view.scene().addItem(self._overlay)
            self._overlay.add_point(self._start_scene)
            return True

        self._overlay = DragRectItem(self.panel.qcolor())
        self.view.scene().addItem(self._overlay)
        self._overlay.set_rect(QRectF(self._start_scene, self._start_scene))
        return True

    def mouse_move(self, event) -> bool:
        if self._overlay is None or self.view is None:
            return False
        scene = self.view.mapToScene(event.position().toPoint())
        if isinstance(self._overlay, InkItem):
            self._overlay.add_point(scene)
        else:
            self._overlay.set_rect(QRectF(self._start_scene, scene))
        return True

    def mouse_release(self, event) -> bool:
        if self._overlay is None or self.view is None or self._page is None:
            self._clear_overlay()
            return False
        tool = self.panel.tool
        page = self._page

        if isinstance(self._overlay, InkItem):
            points = self._overlay.points()
            self._clear_overlay()
            if len(points) >= 2:
                local_points = [[tuple(self.view.scene_to_page(page, p)) for p in points]]
                self.panel.create_from_points(tool, page, local_points)
            return True

        rect_scene = self._overlay.boundingRect()
        self._clear_overlay()
        p0 = self.view.scene_to_page(page, rect_scene.topLeft())
        p1 = self.view.scene_to_page(page, rect_scene.bottomRight())
        rect = QRectF(p0, p1).normalized()
        if rect.width() < 2 or rect.height() < 2:
            return True

        if tool in LINE_TOOLS:
            self.panel.create_from_line(tool, page, (p0.x(), p0.y()), (p1.x(), p1.y()))
        else:
            self.panel.create_from_rect(tool, page, rect)
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key_Delete:
            self.panel.delete_selected()
            return True
        if event.key() == Qt.Key_Escape:
            self._clear_overlay()
            return True
        return False


class AnnotatePanel(QWidget):
    def __init__(self, mainwindow, doc: PdfDoc, view: PdfView) -> None:
        super().__init__()
        self.mainwindow = mainwindow
        self.doc = doc
        self.view = view
        self.tool = "select"
        self.selected: Optional[Tuple[int, int]] = None   # (page, xref)
        self.mode = AnnotateMode(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 工具条
        tools = QGroupBox("工具")
        tl = QHBoxLayout(tools)
        tl.setSpacing(2)
        self._tool_buttons = {}
        for key, label in TOOL_BUTTONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.tool)
            btn.clicked.connect(lambda _=False, k=key, b=btn: self._set_tool(k, b))
            self._tool_buttons[key] = btn
            tl.addWidget(btn)
        layout.addWidget(tools)

        # 属性
        props = QGroupBox("属性")
        pl = QFormLayout(props)
        pl.setLabelAlignment(Qt.AlignRight)
        self._color = ColorButton("#FFFF00")
        pl.addRow("颜色", self._color)
        self._fill = ColorButton("#0000FF")
        self._no_fill = QCheckBox("无填充")
        self._no_fill.setChecked(True)
        fill_row = QHBoxLayout()
        fill_row.addWidget(self._fill)
        fill_row.addWidget(self._no_fill)
        pl.addRow("填充", fill_row)
        self._opacity = QSlider(Qt.Horizontal)
        self._opacity.setRange(5, 100)
        self._opacity.setValue(100)
        pl.addRow("不透明度", self._opacity)
        self._width = QDoubleSpinBox()
        self._width.setRange(0.5, 10)
        self._width.setSingleStep(0.5)
        self._width.setValue(2)
        pl.addRow("线宽", self._width)
        self._fontsize = QSpinBox()
        self._fontsize.setRange(8, 72)
        self._fontsize.setValue(14)
        pl.addRow("字号", self._fontsize)
        self._lock = QCheckBox("锁定（不可再编辑）")
        pl.addRow("", self._lock)
        layout.addWidget(props)

        for ctrl in (self._color, self._fill):
            ctrl.colorChanged.connect(self.apply_props)
        self._opacity.valueChanged.connect(self.apply_props)
        self._width.valueChanged.connect(self.apply_props)
        self._lock.toggled.connect(self.apply_props)

        # 操作
        acts = QHBoxLayout()
        for text, slot in (
            ("删除", self.delete_selected),
            ("复制", self.duplicate_selected),
            ("压平全部", self.flatten),
        ):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            acts.addWidget(btn)
        acts.addStretch(1)
        layout.addLayout(acts)

        # 列表
        list_group = QGroupBox("标注列表")
        ll = QVBoxLayout(list_group)
        filters = QHBoxLayout()
        self._type_filter = QComboBox()
        self._type_filter.addItem("全部类型", None)
        for key, label in ann.TYPE_LABELS.items():
            self._type_filter.addItem(label, key)
        self._type_filter.currentIndexChanged.connect(self.refresh_list)
        filters.addWidget(self._type_filter)
        self._page_filter = QComboBox()
        self._page_filter.addItem("全部页", -1)
        self._page_filter.currentIndexChanged.connect(self.refresh_list)
        filters.addWidget(self._page_filter)
        ll.addLayout(filters)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_list_select)
        ll.addWidget(self._list, 1)
        layout.addWidget(list_group, 1)

        self._status = QLabel("")
        layout.addWidget(self._status)

    # ---------------------------------------------------------------- 生命周期

    def activate(self) -> None:
        self.view.set_mode(self.mode)
        self.refresh_list()

    def deactivate(self) -> None:
        self.mode.detach()
        self.view.set_mode(None)

    # ---------------------------------------------------------------- 工具

    def _set_tool(self, key: str, button: QPushButton) -> None:
        self.tool = key
        for other in self._tool_buttons.values():
            other.setChecked(other is button)

    def qcolor(self) -> QColor:
        return QColor(self._color.hex())

    @property
    def line_width(self) -> float:
        return self._width.value()

    # ---------------------------------------------------------------- 创建

    def _spec_kwargs(self) -> dict:
        return dict(
            color=self._color.hex(),
            fill_color=None if self._no_fill.isChecked() else self._fill.hex(),
            line_width=self._width.value(),
            opacity=self._opacity.value() / 100.0,
            font_size=float(self._fontsize.value()),
            locked=self._lock.isChecked(),
        )

    def create_from_rect(self, tool: str, page: int, rect: QRectF) -> None:
        if tool == ann.T_TEXT:
            text, ok = QInputDialog.getMultiLineText(self, i18n.translate("文字标注"), i18n.translate("输入文字："))
            if not ok or not text.strip():
                return
            spec = ann.AnnotationSpec(type=tool, page=page, rect=_t(rect), text=text,
                                      **self._spec_kwargs())
        elif tool == ann.T_NOTE:
            author, ok1 = QInputDialog.getText(self, i18n.translate("便签"), i18n.translate("作者："))
            if not ok1:
                return
            content, ok2 = QInputDialog.getMultiLineText(self, i18n.translate("便签"), i18n.translate("内容："))
            if not ok2:
                return
            spec = ann.AnnotationSpec(type=tool, page=page, rect=_t(rect),
                                      note_author=author, note_content=content,
                                      **self._spec_kwargs())
        elif tool == ann.T_STAMP:
            text, ok = QInputDialog.getItem(
                self, i18n.translate("图章"), i18n.translate("选择图章："),
                ann.STAMP_PRESETS, 0, False,
            )
            if not ok:
                return
            spec = ann.AnnotationSpec(type=tool, page=page, rect=_t(rect),
                                      stamp_text=text, **self._spec_kwargs())
        elif tool == ann.T_IMAGE:
            path = QFileDialog.getOpenFileName(self, i18n.translate("选择图片"), "", i18n.translate("图片 (*.png *.jpg *.jpeg)"))[0]
            if not path:
                return
            with open(path, "rb") as fh:
                data = fh.read()
            spec = ann.AnnotationSpec(type=tool, page=page, rect=_t(rect),
                                      image_bytes=data, **self._spec_kwargs())
        else:
            spec = ann.AnnotationSpec(type=tool, page=page, rect=_t(rect), **self._spec_kwargs())

        self._add(spec)

    def create_from_points(self, tool: str, page: int, points) -> None:
        spec = ann.AnnotationSpec(type=tool, page=page, points=points, **self._spec_kwargs())
        self._add(spec)

    def create_from_line(self, tool: str, page: int, p1, p2) -> None:
        spec = ann.AnnotationSpec(type=tool, page=page, p1=p1, p2=p2, **self._spec_kwargs())
        self._add(spec)

    def _add(self, spec: ann.AnnotationSpec) -> None:
        self.doc.snapshot()
        try:
            ann.add_annotation(self.doc.fitz_doc, spec)
        except ValueError as exc:
            warn(self, "无法添加标注", str(exc))
            return
        self.doc.mark_dirty()
        self.refresh_list()

    # ---------------------------------------------------------------- 选择/属性

    def select_at(self, page: int, local: QPointF) -> None:
        items = ann.list_annotations(self.doc.fitz_doc, page=page)
        best = None
        for item in items:
            r = QRectF(*item["rect"])
            if r.contains(local):
                best = item
        self.selected = (page, best["xref"]) if best else None
        self._status.setText(i18n.translate(
            f"已选中：{best['type_label']}　第 {page + 1} 页" if best else "未选中任何标注"
        ))
        self.refresh_list(select=self.selected)

    def _on_list_select(self, current: QListWidgetItem, _prev) -> None:
        if current is None:
            return
        data = current.data(Qt.UserRole)
        if data:
            self.selected = (data["page"], data["xref"])

    def apply_props(self, *_args) -> None:
        if self.selected is None:
            return
        page, xref = self.selected
        self.doc.snapshot()
        ann.update_annotation(
            self.doc.fitz_doc, page, xref,
            color=self._color.hex(),
            fill_color=None if self._no_fill.isChecked() else self._fill.hex(),
            opacity=self._opacity.value() / 100.0,
            line_width=self._width.value(),
            locked=self._lock.isChecked(),
        )
        self.doc.mark_dirty()

    # ---------------------------------------------------------------- 操作

    def delete_selected(self) -> None:
        if self.selected is None:
            return
        page, xref = self.selected
        self.doc.snapshot()
        ann.delete_annotation(self.doc.fitz_doc, page, xref)
        self.selected = None
        self.doc.mark_dirty()
        self.refresh_list()

    def duplicate_selected(self) -> None:
        if self.selected is None:
            return
        page, xref = self.selected
        self.doc.snapshot()
        ann.duplicate_annotation(self.doc.fitz_doc, page, xref)
        self.doc.mark_dirty()
        self.refresh_list()

    def flatten(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        ret = QMessageBox.question(
            self, i18n.translate("压平标注"),
            i18n.translate("压平后标注会变成页面内容，无法再编辑或单独删除。确定继续？"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.doc.snapshot()
        count = ann.flatten_annotations(self.doc.fitz_doc)
        self.doc.mark_dirty()
        self.selected = None
        self.refresh_list()
        info(self, "已压平", f"共压平 {count} 条标注。记得保存。")

    # ---------------------------------------------------------------- 列表

    def refresh_list(self, *_args, select=None) -> None:
        if self._page_filter.count() <= 1 and self.doc.page_count:
            self._page_filter.blockSignals(True)
            self._page_filter.clear()
            self._page_filter.addItem("全部页", -1)
            for i in range(self.doc.page_count):
                self._page_filter.addItem(f"第 {i + 1} 页", i)
            self._page_filter.blockSignals(False)

        type_filter = self._type_filter.currentData()
        page_filter = self._page_filter.currentData()
        items = ann.list_annotations(
            self.doc.fitz_doc,
            page=None if page_filter is None or page_filter < 0 else page_filter,
            type_filter=type_filter,
        )
        self._list.clear()
        for item in items:
            label = f"P{item['page'] + 1}　{item['type_label']}　{ann.annotation_summary(item)}"
            li = QListWidgetItem(label)
            li.setData(Qt.UserRole, item)
            self._list.addItem(li)
        self._status.setText(i18n.translate(f"共 {len(items)} 条标注"))


def _t(rect: QRectF) -> Tuple[float, float, float, float]:
    return (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())


def create_panel(mainwindow, doc: PdfDoc, view: PdfView) -> AnnotatePanel:
    return AnnotatePanel(mainwindow, doc, view)
