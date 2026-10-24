"""PDF 内容编辑：插入文字/图片（可拖动浮层，确认后写入）、改文字、删除区域、替换/删除图片。"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
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
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from ...core.ops import edit as edit_ops
from .. import icons
from ..viewer import PdfView
from .. import i18n
from ..widgets import ColorButton, info, warn
from ..widgets.overlay import DragRectItem, ElementItem

TOOL_SELECT = "select"
TOOL_INSERT_TEXT = "insert_text"
TOOL_INSERT_IMAGE = "insert_image"
TOOL_TEXT = "text"
TOOL_DELETE = "delete"
TOOL_REPLACE_IMAGE = "replace_image"
TOOL_DELETE_IMAGE = "delete_image"

TOOLS = [
    (TOOL_SELECT, "选择/移动"),
    (TOOL_INSERT_TEXT, "插入文字"),
    (TOOL_INSERT_IMAGE, "插入图片"),
    (TOOL_TEXT, "改文字"),
    (TOOL_DELETE, "删除区域"),
    (TOOL_REPLACE_IMAGE, "替换图片"),
    (TOOL_DELETE_IMAGE, "删除图片"),
]

TOOL_ICONS = {
    TOOL_SELECT: "cursor",
    TOOL_INSERT_TEXT: "ins_text",
    TOOL_INSERT_IMAGE: "ins_img",
    TOOL_TEXT: "edit_content",
    TOOL_DELETE: "redact",
    TOOL_REPLACE_IMAGE: "img_swap",
    TOOL_DELETE_IMAGE: "img_del",
}

DRAG_TOOLS = {TOOL_DELETE, TOOL_INSERT_TEXT, TOOL_INSERT_IMAGE}


class _InsertTextDialog(QDialog):
    def __init__(self, parent=None, initial: Optional[Dict] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("插入文字" if not initial else "编辑文字")
        self.resize(420, 320)
        layout = QFormLayout(self)

        self.text = QTextEdit()
        self.text.setPlaceholderText("输入要插入的文字（支持多行）")
        if initial:
            self.text.setPlainText(initial.get("text", ""))
        layout.addRow("内容", self.text)

        self.size = QSpinBox()
        self.size.setRange(6, 200)
        self.size.setValue(int(initial.get("size", 14)) if initial else 14)
        layout.addRow("字号", self.size)

        self.font = QComboBox()
        self.font.addItem("自动（按内容选择）", "auto")
        for key, label, _fn, _ff, _fam in edit_ops.FONT_CHOICES:
            self.font.addItem(label, key)
        if initial:
            idx = self.font.findData(initial.get("font", "auto"))
            self.font.setCurrentIndex(max(0, idx))
        layout.addRow("字体", self.font)

        self.color = ColorButton("#000000")
        if initial:
            c = initial.get("color")
            if c:
                self.color.set_hex(
                    "#%02x%02x%02x" % (round(c[0] * 255), round(c[1] * 255), round(c[2] * 255))
                )
        layout.addRow("颜色", self.color)

        self.align = QComboBox()
        self.align.addItem("左对齐", 0)
        self.align.addItem("居中", 1)
        self.align.addItem("右对齐", 2)
        if initial:
            idx = self.align.findData(initial.get("align", 0))
            self.align.setCurrentIndex(max(0, idx))
        layout.addRow("对齐", self.align)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return (
            self.text.toPlainText(),
            float(self.size.value()),
            self.color.rgb01(),
            int(self.align.currentData()),
            self.font.currentData(),
        )


class EditContentMode:
    def __init__(self, panel: "EditContentPanel") -> None:
        self.panel = panel
        self.view: Optional[PdfView] = None
        self._overlay: Optional[DragRectItem] = None
        self._start: Optional[QPointF] = None
        self._page: Optional[int] = None
        self._tool: str = TOOL_DELETE
        self._text_page: Optional[int] = None
        self._text_start: Optional[QPointF] = None
        self._move: Optional[Dict] = None
        self._press_scene: Optional[QPointF] = None
        self._press_page: Optional[QPointF] = None
        self._dragged = False
        self._drag_item = None
        self._drag_offset: Optional[QPointF] = None
        self._resize = None

    def attach(self, view: PdfView) -> None:
        self.view = view

    def detach(self) -> None:
        self._clear()

    def _clear(self) -> None:
        if self._overlay is not None and self.view is not None:
            self.view.scene().removeItem(self._overlay)
            self._overlay = None

    def mouse_press(self, event) -> bool:
        if event.button() != Qt.LeftButton or self.view is None:
            return False
        tool = self.panel.tool

        # 正在页上编辑文字时，点别处=提交
        if self.panel.editing:
            self.panel.commit_inline()
            return True

        # 选择/移动：命中浮层元素则拖元素，否则点/框文字进入页上编辑
        if tool == TOOL_SELECT:
            from ..widgets.overlay import ElementItem

            scene_pos = self.view.mapToScene(event.position().toPoint())
            for it in self.view.scene().items(scene_pos):
                if isinstance(it, ElementItem):
                    for other in self.view.scene().items():
                        if isinstance(other, ElementItem):
                            other.setSelected(other is it)
                    tol = 4.0 / max(0.2, self.view.zoom)
                    handle = it.handle_at(scene_pos, tol)
                    if handle:
                        self._resize = (it, handle, QRectF(it.scene_rect()))
                        return True
                    self._drag_item = it
                    self._drag_offset = QPointF(scene_pos) - it.pos()
                    return True
            hit = self.view.view_to_page_point(event.position().toPoint())
            if hit is None:
                return False
            self._text_page = hit[0]
            self._text_start = QPointF(hit[1])
            self._press_scene = QPointF(scene_pos)
            self._press_page = QPointF(hit[1])
            self._move = self._detect_content(hit[0], hit[1])
            self._dragged = False
            return True

        hit = self.view.view_to_page_point(event.position().toPoint())
        if hit is None:
            return False
        page, local = hit

        if tool == TOOL_TEXT:
            self._text_page = page
            self._text_start = QPointF(local)
            return True

        if tool in DRAG_TOOLS:
            self._page = page
            self._tool = tool
            color = QColor(200, 30, 30) if tool == TOOL_DELETE else QColor(47, 111, 208)
            fill = QColor(200, 30, 30, 50) if tool == TOOL_DELETE else QColor(47, 111, 208, 45)
            self._start = self.view.mapToScene(event.position().toPoint())
            self._overlay = DragRectItem(color, fill)
            self.view.scene().addItem(self._overlay)
            self._overlay.set_rect(QRectF(self._start, self._start))
            return True

        point = pymupdf_point(local)
        if tool == TOOL_REPLACE_IMAGE:
            self.panel.replace_image_at(page, point)
        elif tool == TOOL_DELETE_IMAGE:
            self.panel.delete_image_at(page, point)
        return True

    def mouse_move(self, event) -> bool:
        if self.view is None:
            return False
        if self._resize is not None:
            item, handle, orig = self._resize
            scene_pos = self.view.mapToScene(event.position().toPoint())
            item.set_scene_rect(
                _adjusted_rect(orig, handle, scene_pos, keep_aspect=item.kind == "image")
            )
            return True
        if self._drag_item is not None:
            scene_pos = self.view.mapToScene(event.position().toPoint())
            self._drag_item.setPos(scene_pos - self._drag_offset)
            return True
        if self._move is not None and self._press_scene is not None:
            cur = self.view.mapToScene(event.position().toPoint())
            delta = cur - self._press_scene
            if not self._dragged and (abs(delta.x()) > 6 or abs(delta.y()) > 6):
                self._dragged = True
                self._overlay = DragRectItem(QColor(47, 111, 208), QColor(47, 111, 208, 40))
                self.view.scene().addItem(self._overlay)
            if self._dragged:
                base = self._move_scene_rect()
                self._overlay.set_rect(base.translated(delta.x(), delta.y()))
                return True
        if self._overlay is None:
            return False
        self._overlay.set_rect(QRectF(self._start, self.view.mapToScene(event.position().toPoint())))
        return True

    def mouse_release(self, event) -> bool:
        if self.view is None:
            return False
        if self._resize is not None:
            item = self._resize[0]
            self._resize = None
            if item.element is not None:
                self.panel._element_moved(item.element, item)
            return True
        if self._drag_item is not None:
            item = self._drag_item
            self._drag_item = None
            self._drag_offset = None
            if item.element is not None:
                self.panel._element_moved(item.element, item)
            return True
        if self._move is not None and self._dragged:
            ctx = self._move
            press = self._press_page or QPointF()
            self._move = None
            self._press_scene = None
            self._press_page = None
            self._dragged = False
            self._text_page = None
            self._text_start = None
            self._clear()
            hit = self.view.view_to_page_point(event.position().toPoint())
            end = hit[1] if hit and hit[0] == ctx["page"] else press
            self.panel.move_content(ctx, end.x() - press.x(), end.y() - press.y())
            return True
        if self._move is not None:
            self._move = None
            self._press_scene = None
            self._press_page = None
            self._dragged = False
        if self._text_page is not None and self.panel.tool in (TOOL_TEXT, TOOL_SELECT):
            page = self._text_page
            start = self._text_start or QPointF()
            self._text_page = None
            self._text_start = None
            hit = self.view.view_to_page_point(event.position().toPoint())
            end = hit[1] if hit and hit[0] == page else start
            span = QRectF(
                min(start.x(), end.x()), min(start.y(), end.y()),
                max(start.x(), end.x()) + 1, max(start.y(), end.y()) + 1,
            )
            self.panel.begin_inline_edit(page, span)
            return True

        if self._overlay is None or self._page is None:
            self._clear()
            return False
        rect_scene = self._overlay.boundingRect()
        page = self._page
        tool = self._tool
        self._clear()
        p0 = self.view.scene_to_page(page, rect_scene.topLeft())
        p1 = self.view.scene_to_page(page, rect_scene.bottomRight())
        rect = QRectF(p0, p1).normalized()

        if rect.width() <= 2 or rect.height() <= 2:
            if tool == TOOL_INSERT_TEXT:
                rect = QRectF(p0.x(), p0.y(), p0.x() + 220, p0.y() + 60)
            elif tool == TOOL_INSERT_IMAGE:
                rect = QRectF(p0.x(), p0.y(), p0.x() + 200, p0.y() + 150)
            else:
                return True
        elif tool == TOOL_INSERT_TEXT and (rect.width() < 60 or rect.height() < 24):
            rect = QRectF(p0.x(), p0.y(), p0.x() + 220, p0.y() + 60)
        elif tool == TOOL_INSERT_IMAGE and (rect.width() < 60 or rect.height() < 45):
            rect = QRectF(p0.x(), p0.y(), p0.x() + 200, p0.y() + 150)

        if tool == TOOL_DELETE:
            self.panel.remove_region(page, rect)
        elif tool == TOOL_INSERT_TEXT:
            self.panel.insert_text_at(page, rect)
        elif tool == TOOL_INSERT_IMAGE:
            self.panel.insert_image_at(page, rect)
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key_Escape:
            self._clear()
            return True
        if event.key() == Qt.Key_Delete:
            self.panel.delete_selected_element()
            return True
        return False

    def _detect_content(self, page: int, local: QPointF) -> Optional[Dict]:
        """探测按下点上的已有内容：图片优先，其次文字行。"""
        import pymupdf

        point = pymupdf.Point(local.x(), local.y())
        with self.panel.doc.lock:
            pg = self.panel.doc.fitz_doc.load_page(page)
            img = edit_ops.find_image_at(pg, point)
            if img is not None:
                return {"kind": "image", "page": page, "rect": img.rect, "xref": img.xref}
            probe = pymupdf.Rect(local.x() - 1, local.y() - 1, local.x() + 1, local.y() + 1)
            lines = edit_ops.find_text_lines_in(pg, probe)
        if not lines:
            return None
        union = pymupdf.Rect(*lines[0].rect)
        for ln in lines[1:]:
            union |= pymupdf.Rect(*ln.rect)
        return {
            "kind": "text",
            "page": page,
            "rect": (union.x0, union.y0, union.x1, union.y1),
        }

    def _move_scene_rect(self) -> QRectF:
        ctx = self._move or {}
        rect = ctx.get("rect")
        page = ctx.get("page", 0)
        if not rect or self.view is None:
            return QRectF()
        tl = self.view.page_to_scene(page, QPointF(rect[0], rect[1]))
        br = self.view.page_to_scene(page, QPointF(rect[2], rect[3]))
        return QRectF(tl, br).normalized()


def pymupdf_point(local: QPointF):
    import pymupdf

    return pymupdf.Point(local.x(), local.y())


def _adjusted_rect(r: QRectF, handle: str, p: QPointF, keep_aspect: bool) -> QRectF:
    """按手柄方向用当前点 p 调整矩形；四角手柄且 keep_aspect 时等比缩放。"""
    x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()
    if "l" in handle:
        x0 = min(p.x(), x1 - 10)
    if "r" in handle:
        x1 = max(p.x(), x0 + 10)
    if "t" in handle:
        y0 = min(p.y(), y1 - 10)
    if "b" in handle:
        y1 = max(p.y(), y0 + 10)
    out = QRectF(x0, y0, x1 - x0, y1 - y0)
    if keep_aspect and handle in ("tl", "tr", "bl", "br") and r.width() > 0:
        scale = out.width() / r.width()
        nh = max(10.0, r.height() * scale)
        if "t" in handle:
            out = QRectF(out.x(), out.y() + (out.height() - nh), out.width(), nh)
        else:
            out = QRectF(out.x(), out.y(), out.width(), nh)
    return out


class EditContentPanel(QWidget):
    def __init__(self, mainwindow, doc: PdfDoc, view: PdfView) -> None:
        super().__init__()
        self.mainwindow = mainwindow
        self.doc = doc
        self.view = view
        self.tool = TOOL_SELECT
        self.mode = EditContentMode(self)
        self._elements: List[Dict] = []
        self._applying = False
        self._edit_proxy = None
        self._edit_box = None
        self._edit_ctx = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        tip = QLabel(
            "插入文字/插入图片：拖拽框出区域（或单击用默认尺寸），插入后可用「选择/移动」拖动，满意后点「应用到页面」写入 PDF；关闭面板或保存时会自动应用。\n"
            "选择/移动：拖动浮层元素或页面已有文字/图片；双击浮层可改内容；选中后拖手柄可缩放。\n"
            "改文字：点击或框选文字后直接在页面上输入（Esc 取消，Ctrl+Enter 或点击别处提交）。\n"
            "删除区域：拖拽删除；替换/删除图片：点击图片。\n"
            "所有修改都可按 Ctrl+Z 撤销，记得保存。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        tools = QGroupBox("编辑工具")
        tl = QHBoxLayout(tools)
        tl.setSpacing(2)
        self._buttons = {}
        for key, label in TOOLS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == self.tool)
            btn.setIcon(icons.icon(TOOL_ICONS[key], 16))
            btn.clicked.connect(lambda _=False, k=key, b=btn: self._set_tool(k, b))
            self._buttons[key] = btn
            tl.addWidget(btn)
        tl.addStretch(1)
        layout.addWidget(tools)

        bar = QHBoxLayout()
        self._apply_btn = QPushButton("应用到页面")
        self._apply_btn.setProperty("primary", True)
        self._apply_btn.clicked.connect(lambda: self.apply_pending())
        bar.addWidget(self._apply_btn)
        self._del_btn = QPushButton("删除选中元素")
        self._del_btn.clicked.connect(self.delete_selected_element)
        bar.addWidget(self._del_btn)
        self._edit_btn = QPushButton("编辑选中元素")
        self._edit_btn.clicked.connect(self.edit_selected_element)
        bar.addWidget(self._edit_btn)
        bar.addStretch(1)
        layout.addLayout(bar)

        self._status = QLabel("当前工具：选择/移动　待应用元素 0 个")
        layout.addWidget(self._status)
        layout.addStretch(1)

        doc.changed.connect(self._on_doc_changed)

    # ---------------------------------------------------------------- 生命周期

    def activate(self) -> None:
        self.view.set_mode(self.mode)
        self._dc_conn = self.view.pageDoubleClicked.connect(self._on_double_click)

    def deactivate(self) -> None:
        if self.editing:
            self.commit_inline()
        if self._elements:
            self.apply_pending()
        conn = getattr(self, "_dc_conn", None)
        if conn is not None:
            try:
                self.view.pageDoubleClicked.disconnect(conn)
            except RuntimeError:
                pass
            self._dc_conn = None
        self.mode.detach()
        self.view.set_mode(None)

    def _on_double_click(self, page: int, point: QPointF) -> None:
        scene = self.view.page_to_scene(page, point)
        for element in self._elements:
            if element["page"] != page:
                continue
            if element["item"].scene_rect().contains(scene):
                for other in self._elements:
                    other["item"].setSelected(other is element)
                self.edit_selected_element()
                return

    def _on_doc_changed(self) -> None:
        # 撤销/重做/应用后，浮层与页面内容不再对应，清空浮层
        if not self._applying:
            self.clear_elements()

    def _set_tool(self, key: str, button: QPushButton) -> None:
        self.tool = key
        for other in self._buttons.values():
            other.setChecked(other is button)
        names = dict(TOOLS)
        self._status.setText(i18n.translate(f"当前工具：{names[key]}　待应用元素 {len(self._elements)} 个"))

    # ---------------------------------------------------------------- 浮层元素

    def _refresh_status(self) -> None:
        names = dict(TOOLS)
        self._status.setText(i18n.translate(f"当前工具：{names[self.tool]}　待应用元素 {len(self._elements)} 个"))

    def _element_moved(self, element: Dict, item: ElementItem) -> None:
        scene_rect = item.scene_rect()
        p0 = self.view.scene_to_page(element["page"], scene_rect.topLeft())
        p1 = self.view.scene_to_page(element["page"], scene_rect.bottomRight())
        element["rect"] = QRectF(p0, p1).normalized()

    def add_text_element(self, page: int, rect: QRectF, text: str, size: float,
                         color, align: int, font_key: str = "auto") -> None:
        scene_tl = self.view.page_to_scene(page, rect.topLeft())
        scene_br = self.view.page_to_scene(page, rect.bottomRight())
        scene_rect = QRectF(scene_tl, scene_br).normalized()
        _fontname, _fontfile, family = edit_ops.resolve_font(
            "cjk" if font_key == "auto" else font_key
        )
        element = {
            "kind": "text", "page": page, "rect": QRectF(rect),
            "text": text, "fontsize": size, "color": color, "align": align,
            "font_key": font_key,
        }
        item = ElementItem(
            scene_rect, "text",
            on_changed=lambda it, e=element: self._element_moved(e, it),
            text=text, fontsize=size,
            color=QColor.fromRgbF(color[0], color[1], color[2]),
            align=align,
            family=family,
        )
        element["item"] = item
        item.element = element
        self.view.scene().addItem(item)
        self._elements.append(element)
        self._refresh_status()

    def add_image_element(self, page: int, rect: QRectF, data: bytes) -> None:
        scene_tl = self.view.page_to_scene(page, rect.topLeft())
        scene_br = self.view.page_to_scene(page, rect.bottomRight())
        scene_rect = QRectF(scene_tl, scene_br).normalized()
        pixmap = QPixmap.fromImage(QImage.fromData(data))
        element = {"kind": "image", "page": page, "rect": QRectF(rect), "data": data}
        item = ElementItem(
            scene_rect, "image",
            on_changed=lambda it, e=element: self._element_moved(e, it),
            pixmap=pixmap,
        )
        element["item"] = item
        item.element = element
        self.view.scene().addItem(item)
        self._elements.append(element)
        self._refresh_status()

    def delete_selected_element(self) -> None:
        removed = [e for e in self._elements if e["item"].isSelected()]
        if not removed:
            return
        for e in removed:
            self.view.scene().removeItem(e["item"])
            self._elements.remove(e)
        self._refresh_status()

    def edit_selected_element(self) -> None:
        selected = [e for e in self._elements if e["item"].isSelected()]
        if not selected:
            warn(self, "未选中元素", "先用「选择/移动」点选一个浮层元素，或双击它。")
            return
        element = selected[-1]

        if element["kind"] == "text":
            dlg = _InsertTextDialog(
                self,
                initial={
                    "text": element["text"],
                    "size": element["fontsize"],
                    "color": element["color"],
                    "align": element["align"],
                    "font": element.get("font_key", "auto"),
                },
            )
            if dlg.exec() != QDialog.Accepted:
                return
            text, size, color, align, font_key = dlg.values()
            if not text.strip():
                return
            import pymupdf

            old = element["rect"]
            with self.doc.lock:
                fitted = edit_ops.fit_text_rect(
                    self.doc.fitz_doc.load_page(element["page"]),
                    pymupdf.Rect(old.x(), old.y(), old.x() + 400, old.y() + 400),
                    text,
                    size,
                    font_key=font_key,
                )
            new_rect = QRectF(fitted.x0, fitted.y0, fitted.x1, fitted.y1)
            element.update(
                text=text, fontsize=size, color=color, align=align,
                font_key=font_key, rect=new_rect,
            )
            item = element["item"]
            item.text = text
            item.fontsize = size
            item.color = QColor.fromRgbF(color[0], color[1], color[2])
            item.align = align
            item.family = edit_ops.resolve_font(
                "cjk" if font_key == "auto" else font_key
            )[2]
            tl = self.view.page_to_scene(element["page"], new_rect.topLeft())
            br = self.view.page_to_scene(element["page"], new_rect.bottomRight())
            item.set_scene_rect(QRectF(tl, br).normalized())
            self._refresh_status()
            return

        path = QFileDialog.getOpenFileName(
            self, "选择新图片", "", "图片 (*.png *.jpg *.jpeg *.webp *.bmp)"
        )[0]
        if not path:
            return
        with open(path, "rb") as fh:
            element["data"] = fh.read()
        element["item"].pixmap = QPixmap.fromImage(QImage.fromData(element["data"]))
        element["item"].update()
        self._refresh_status()

    def move_content(self, ctx: Dict, dx: float, dy: float) -> None:
        """平移页面已有内容（文字行或图片）。"""
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return
        import pymupdf

        self.doc.snapshot()
        with self.doc.lock:
            doc = self.doc.fitz_doc
            page = doc.load_page(ctx["page"])
            if ctx["kind"] == "image":
                ok = edit_ops.move_image(doc, page, ctx["xref"], dx, dy)
            else:
                ok = edit_ops.move_text_lines(page, pymupdf.Rect(*ctx["rect"]), dx, dy) > 0
        if ok:
            self.doc.mark_dirty()
        kind_label = "图片" if ctx["kind"] == "image" else "文字"
        self._status.setText(i18n.translate(
            f"已移动{kind_label}（{dx:+.0f}, {dy:+.0f}）。记得保存。"
            if ok
            else f"该{kind_label}无法移动。"
        ))

    def clear_elements(self) -> None:
        for e in self._elements:
            self.view.scene().removeItem(e["item"])
        self._elements.clear()
        self._refresh_status()

    def apply_pending(self) -> bool:
        """把浮层元素真正写入 PDF。返回是否写入了内容。"""
        if not self._elements:
            return False
        import pymupdf

        self._applying = True
        try:
            self.doc.snapshot()
            with self.doc.lock:
                for element in sorted(self._elements, key=lambda e: e["page"]):
                    page = self.doc.fitz_doc.load_page(element["page"])
                    r = element["rect"]
                    rect = pymupdf.Rect(r.x(), r.y(), r.right(), r.bottom())
                    if element["kind"] == "text":
                        edit_ops.insert_text_box(
                            page, rect, element["text"],
                            fontsize=element["fontsize"],
                            color=element["color"],
                            align=element["align"],
                            font_key=element.get("font_key", "auto"),
                        )
                    else:
                        edit_ops.insert_image_rect(page, rect, stream=element["data"])
            for e in self._elements:
                self.view.scene().removeItem(e["item"])
            self._elements.clear()
            self.doc.mark_dirty()
        finally:
            self._applying = False
        self._set_tool(TOOL_SELECT, self._buttons[TOOL_SELECT])
        self._status.setText(i18n.translate("已应用到页面。用「选择/移动」点击文字可继续编辑。记得保存。"))
        return True

    # ---------------------------------------------------------------- 直接编辑

    def insert_text_at(self, page: int, rect: QRectF) -> None:
        dlg = _InsertTextDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        text, size, color, align, font_key = dlg.values()
        if not text.strip():
            return
        import pymupdf

        with self.doc.lock:
            fitted = edit_ops.fit_text_rect(
                self.doc.fitz_doc.load_page(page),
                pymupdf.Rect(rect.x(), rect.y(), rect.right(), rect.bottom()),
                text,
                size,
                font_key=font_key,
            )
        rect = QRectF(fitted.x0, fitted.y0, fitted.x1, fitted.y1)
        self.add_text_element(page, rect, text, size, color, align, font_key)
        self._status.setText(i18n.translate("已加入浮层，可拖动调整位置，完成后点「应用到页面」。"))

    def insert_image_at(self, page: int, rect: QRectF) -> None:
        path = QFileDialog.getOpenFileName(
            self, "选择要插入的图片", "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)",
        )[0]
        if not path:
            return
        with open(path, "rb") as fh:
            data = fh.read()
        self.add_image_element(page, rect, data)
        self._status.setText(i18n.translate("已加入浮层，可拖动调整位置，完成后点「应用到页面」。"))

    # ------------------------------------------------------------ 页上内联编辑

    @property
    def editing(self) -> bool:
        return self._edit_ctx is not None

    def begin_inline_edit(self, page: int, span: QRectF) -> None:
        if self.editing:
            self.commit_inline()
        import pymupdf
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QGraphicsProxyWidget, QPlainTextEdit

        target = pymupdf.Rect(span.x(), span.y(), span.right(), span.bottom())
        with self.doc.lock:
            lines = edit_ops.find_text_lines_in(self.doc.fitz_doc.load_page(page), target)
        if not lines:
            self._status.setText(i18n.translate("该位置没有可编辑的文字。"))
            return

        union = pymupdf.Rect(*lines[0].rect)
        for ln in lines[1:]:
            union |= pymupdf.Rect(*ln.rect)
        original = "\n".join(ln.text for ln in lines)
        size = max(ln.size for ln in lines)
        color = lines[0].color

        box = QPlainTextEdit()
        box.setPlainText(original)
        font = QFont(edit_ops.resolve_font("cjk" if not original.isascii() else "helv")[2])
        font.setPixelSize(max(8, int(round(size))))
        box.setFont(font)
        box.setStyleSheet(
            "QPlainTextEdit { background: rgba(255,255,255,0.92);"
            " border: 1px solid #2f6fd0; padding: 2px; }"
        )
        box.installEventFilter(self)

        proxy = QGraphicsProxyWidget()
        proxy.setWidget(box)
        proxy.setZValue(1200)
        self.view.scene().addItem(proxy)
        tl = self.view.page_to_scene(page, QPointF(union.x0, union.y0))
        proxy.setPos(tl)
        proxy.resize(max(80.0, union.width + 10), max(28.0, union.height + 10))

        self._edit_proxy = proxy
        self._edit_box = box
        self._edit_ctx = {
            "page": page,
            "rect": (union.x0, union.y0, union.x1, union.y1),
            "original": original,
            "size": size,
            "color": color,
        }
        box.setFocus()
        box.selectAll()
        self._status.setText(i18n.translate("页上编辑中：Esc 取消，Ctrl+Enter 或点击别处提交。"))

    def eventFilter(self, obj, event):  # noqa: N802
        from PySide6.QtCore import QEvent

        if obj is self._edit_box and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.cancel_inline()
                return True
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and event.modifiers() & Qt.ControlModifier:
                self.commit_inline()
                return True
        if obj is self._edit_box and event.type() == QEvent.FocusOut:
            self.commit_inline()
            return True
        return super().eventFilter(obj, event)

    def _teardown_inline(self) -> None:
        proxy, box = self._edit_proxy, self._edit_box
        self._edit_proxy = None
        self._edit_box = None
        self._edit_ctx = None
        if box is not None:
            box.removeEventFilter(self)
        if proxy is not None:
            self.view.scene().removeItem(proxy)
            proxy.deleteLater()

    def cancel_inline(self) -> None:
        if not self.editing:
            return
        self._teardown_inline()
        self._refresh_status()

    def commit_inline(self) -> None:
        if not self.editing:
            return
        import pymupdf

        ctx = self._edit_ctx
        new_text = self._edit_box.toPlainText()
        self._teardown_inline()

        if new_text == ctx["original"]:
            self._refresh_status()
            return

        self.doc.snapshot()
        with self.doc.lock:
            page = self.doc.fitz_doc.load_page(ctx["page"])
            if not new_text.strip():
                edit_ops.remove_region(page, pymupdf.Rect(*ctx["rect"]))
            else:
                line = edit_ops.TextLine(
                    rect=ctx["rect"],
                    text=ctx["original"],
                    size=ctx["size"],
                    color=ctx["color"],
                    font="",
                    spans=[],
                )
                edit_ops.replace_text(page, line, new_text)
        self.doc.mark_dirty()
        self._status.setText(i18n.translate(f"已把「{ctx['original'][:12]}」改为「{new_text[:12]}」。记得保存。"))

    def remove_region(self, page: int, rect: QRectF) -> None:
        self.doc.snapshot()
        with self.doc.lock:
            import pymupdf

            edit_ops.remove_region(
                self.doc.fitz_doc.load_page(page),
                pymupdf.Rect(rect.x(), rect.y(), rect.right(), rect.bottom()),
            )
        self.doc.mark_dirty()
        self._status.setText(i18n.translate("已删除框选区域的内容。记得保存。"))

    def replace_image_at(self, page: int, point) -> None:
        with self.doc.lock:
            hit = edit_ops.find_image_at(self.doc.fitz_doc.load_page(page), point)
        if hit is None:
            warn(self, "未命中图片", "该位置没有可替换的内嵌图片。")
            return
        path = QFileDialog.getOpenFileName(self, "选择新图片", "", "图片 (*.png *.jpg *.jpeg *.webp)")[0]
        if not path:
            return
        self.doc.snapshot()
        with self.doc.lock:
            edit_ops.replace_image(self.doc.fitz_doc.load_page(page), hit.xref, path)
        self.doc.mark_dirty()
        self._status.setText(i18n.translate(f"已替换图片 xref={hit.xref}。记得保存。"))

    def delete_image_at(self, page: int, point) -> None:
        with self.doc.lock:
            hit = edit_ops.find_image_at(self.doc.fitz_doc.load_page(page), point)
        if hit is None:
            warn(self, "未命中图片", "该位置没有可删除的内嵌图片。")
            return
        self.doc.snapshot()
        with self.doc.lock:
            edit_ops.delete_image(self.doc.fitz_doc.load_page(page), hit.xref)
        self.doc.mark_dirty()
        self._status.setText(i18n.translate(f"已删除图片 xref={hit.xref}。记得保存。"))


def create_panel(mainwindow, doc: PdfDoc, view: PdfView) -> EditContentPanel:
    return EditContentPanel(mainwindow, doc, view)
