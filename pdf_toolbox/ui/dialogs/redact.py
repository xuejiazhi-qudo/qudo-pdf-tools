"""PDF 涂销：框选 / 吸附文本行 / 关键词 / 敏感信息检测，永久删除。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from .. import i18n
from ...core.ops import redact as redact_ops
from ..viewer import PdfView
from ..widgets import danger, info, warn
from ..widgets.overlay import DragRectItem

Rect = Tuple[float, float, float, float]


class RedactMode:
    def __init__(self, panel: "RedactPanel") -> None:
        self.panel = panel
        self.view: Optional[PdfView] = None
        self._overlay: Optional[DragRectItem] = None
        self._start: Optional[QPointF] = None
        self._page: Optional[int] = None

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
        hit = self.view.view_to_page_point(event.position().toPoint())
        if hit is None:
            return False
        self._page, _local = hit
        self._start = self.view.mapToScene(event.position().toPoint())
        self._overlay = DragRectItem(QColor(200, 30, 30), QColor(200, 30, 30, 60))
        self.view.scene().addItem(self._overlay)
        self._overlay.set_rect(QRectF(self._start, self._start))
        return True

    def mouse_move(self, event) -> bool:
        if self._overlay is None or self.view is None:
            return False
        self._overlay.set_rect(QRectF(self._start, self.view.mapToScene(event.position().toPoint())))
        return True

    def mouse_release(self, event) -> bool:
        if self._overlay is None or self.view is None or self._page is None:
            self._clear()
            return False
        rect_scene = self._overlay.boundingRect()
        page = self._page
        self._clear()
        p0 = self.view.scene_to_page(page, rect_scene.topLeft())
        p1 = self.view.scene_to_page(page, rect_scene.bottomRight())
        rect = QRectF(p0, p1).normalized()
        if rect.width() < 1 or rect.height() < 1:
            return True
        self.panel.add_rect(page, (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height()))
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key_Escape:
            self._clear()
            return True
        if event.key() == Qt.Key_Delete:
            self.panel.remove_selected_pending()
            return True
        return False


class RedactPanel(QWidget):
    def __init__(self, mainwindow, doc: PdfDoc, view: PdfView) -> None:
        super().__init__()
        self.mainwindow = mainwindow
        self.doc = doc
        self.view = view
        self.mode = RedactMode(self)
        self._rects: Dict[int, List[Rect]] = {}
        self._overlays: List[DragRectItem] = []
        self._snap = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        tool_bar = QHBoxLayout()
        self._snap_check = QCheckBox("吸附到文本行")
        self._snap_check.setChecked(True)
        self._snap_check.toggled.connect(lambda on: setattr(self, "_snap", on))
        tool_bar.addWidget(self._snap_check)
        clear = QPushButton("清空标记")
        clear.clicked.connect(self.clear_all)
        tool_bar.addWidget(clear)
        remove = QPushButton("删除选中标记")
        remove.clicked.connect(self.remove_selected_pending)
        tool_bar.addWidget(remove)
        tool_bar.addStretch(1)
        layout.addLayout(tool_bar)

        tabs = QTabWidget()

        # ---- 标记列表
        list_tab = QWidget()
        ll = QVBoxLayout(list_tab)
        self._pending = QListWidget()
        ll.addWidget(self._pending, 1)
        tabs.addTab(list_tab, "标记")

        # ---- 关键词
        kw_tab = QWidget()
        kl = QVBoxLayout(kw_tab)
        row = QHBoxLayout()
        self._kw = QLineEdit()
        self._kw.setPlaceholderText("输入关键词后回车查找")
        self._kw.returnPressed.connect(self.find_keyword)
        row.addWidget(self._kw, 1)
        btn = QPushButton("查找")
        btn.clicked.connect(self.find_keyword)
        row.addWidget(btn)
        kl.addLayout(row)
        self._kw_list = QListWidget()
        kl.addWidget(self._kw_list, 1)
        bar = QHBoxLayout()
        here = QPushButton("涂销选中项")
        here.clicked.connect(self.redact_selected_kw)
        allb = QPushButton("涂销全部")
        allb.clicked.connect(self.redact_all_kw)
        bar.addWidget(here)
        bar.addWidget(allb)
        bar.addStretch(1)
        kl.addLayout(bar)
        tabs.addTab(kw_tab, "关键词")

        # ---- 敏感信息
        sen_tab = QWidget()
        sl = QVBoxLayout(sen_tab)
        self._pattern_checks = {}
        for p in redact_ops.PATTERNS:
            cb = QCheckBox(p.label)
            cb.setChecked(p.key in ("email", "phone_cn", "id_card_cn", "bank_card"))
            self._pattern_checks[p.key] = cb
            sl.addWidget(cb)
        detect = QPushButton("扫描敏感信息")
        detect.clicked.connect(self.detect_sensitive)
        sl.addWidget(detect)
        self._sen_list = QListWidget()
        sl.addWidget(self._sen_list, 1)
        add_sel = QPushButton("把勾选项加入涂销标记")
        add_sel.clicked.connect(self.add_selected_sensitive)
        sl.addWidget(add_sel)
        tabs.addTab(sen_tab, "敏感信息")

        layout.addWidget(tabs, 1)

        # ---- 外观与执行
        app_group = QGroupBox("涂销外观与安全")
        al = QHBoxLayout(app_group)
        al.addWidget(QLabel("覆盖色"))
        self._cover = QComboBox()
        self._cover.addItems(["black", "white"])
        al.addWidget(self._cover)
        al.addWidget(QLabel("覆盖文字"))
        self._label = QComboBox()
        self._label.addItems(["(无)", "REDACTED", "CONFIDENTIAL", "REMOVED"])
        al.addWidget(self._label)
        self._flatten = QCheckBox("最高安全（整页栅格化）")
        al.addWidget(self._flatten)
        layout.addWidget(app_group)

        apply_btn = danger("应用涂销（不可撤销）")
        apply_btn.clicked.connect(self.apply)
        layout.addWidget(apply_btn)

        self._status = QLabel("在页面上拖拽框选要涂销的区域。")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

    # ---------------------------------------------------------------- 生命周期

    def activate(self) -> None:
        self.view.set_mode(self.mode)

    def deactivate(self) -> None:
        self.mode.detach()
        self._clear_overlays()
        self.view.set_mode(None)

    # ---------------------------------------------------------------- 标记

    def add_rect(self, page: int, rect: Rect, snap: Optional[bool] = None) -> None:
        use_snap = self._snap if snap is None else snap
        if use_snap:
            rect = self._snap_to_lines(page, rect)
            if rect is None:
                return
        self._rects.setdefault(page, []).append(rect)
        self._redraw()

    def _snap_to_lines(self, page: int, rect: Rect) -> Optional[Rect]:
        r = QRectF(*rect)
        with self.doc.lock:
            pg = self.doc.fitz_doc.load_page(page)
            words = pg.get_text("words") or []
        lines: Dict[Tuple[int, int], List] = {}
        for w in words:
            lines.setdefault((int(w[5]), int(w[6])), []).append(w)
        boxes = []
        for group in lines.values():
            box = QRectF(group[0][0], group[0][1], group[0][2], group[0][3])
            box = QRectF(min(w[0] for w in group), min(w[1] for w in group),
                         max(w[2] for w in group), max(w[3] for w in group))
            if box.intersects(r):
                boxes.append(box)
        if not boxes:
            return rect
        union = boxes[0]
        for b in boxes[1:]:
            union = union.united(b)
        return (union.x() - 1, union.y() - 1, union.right() + 1, union.bottom() + 1)

    def _redraw(self) -> None:
        self._clear_overlays()
        for page, rects in self._rects.items():
            for rect in rects:
                item = DragRectItem(QColor(200, 30, 30), QColor(200, 30, 30, 60))
                p0 = self.view.page_to_scene(page, QPointF(rect[0], rect[1]))
                p1 = self.view.page_to_scene(page, QPointF(rect[2], rect[3]))
                item.set_rect(QRectF(p0, p1))
                self.view.scene().addItem(item)
                self._overlays.append(item)
        total = sum(len(v) for v in self._rects.values())
        self._status.setText(i18n.translate(f"当前 {total} 个涂销标记。应用后将永久删除这些区域的内容。"))
        self._refresh_pending()

    def _clear_overlays(self) -> None:
        for item in self._overlays:
            self.view.scene().removeItem(item)
        self._overlays.clear()

    def _refresh_pending(self) -> None:
        self._pending.clear()
        for page in sorted(self._rects):
            for i, rect in enumerate(self._rects[page]):
                li = QListWidgetItem(f"第 {page + 1} 页　#{i + 1}　({rect[0]:.0f},{rect[1]:.0f})-({rect[2]:.0f},{rect[3]:.0f})")
                li.setData(Qt.UserRole, (page, i))
                self._pending.addItem(li)

    def clear_all(self) -> None:
        self._rects.clear()
        self._redraw()

    def remove_selected_pending(self) -> None:
        item = self._pending.currentItem()
        if item is None:
            return
        page, idx = item.data(Qt.UserRole)
        if page in self._rects and idx < len(self._rects[page]):
            self._rects[page].pop(idx)
            if not self._rects[page]:
                self._rects.pop(page)
        self._redraw()

    # ---------------------------------------------------------------- 关键词

    def find_keyword(self) -> None:
        query = self._kw.text().strip()
        if not query:
            return
        with self.doc.lock:
            matches = redact_ops.find_matches(
                self.doc.fitz_doc, range(self.doc.page_count), keywords=[query]
            )
        self._kw_matches = matches
        self._kw_list.clear()
        for i, m in enumerate(matches):
            li = QListWidgetItem(f"第 {m.page + 1} 页　{m.text}")
            li.setData(Qt.UserRole, i)
            self._kw_list.addItem(li)
        self._status.setText(i18n.translate(f"找到 {len(matches)} 处「{query}」"))

    def redact_selected_kw(self) -> None:
        item = self._kw_list.currentItem()
        if item is None:
            return
        m = self._kw_matches[item.data(Qt.UserRole)]
        self.add_rect(m.page, m.rect, snap=False)

    def redact_all_kw(self) -> None:
        for m in getattr(self, "_kw_matches", []):
            self.add_rect(m.page, m.rect, snap=False)

    # ---------------------------------------------------------------- 敏感信息

    def detect_sensitive(self) -> None:
        keys = [k for k, cb in self._pattern_checks.items() if cb.isChecked()]
        if not keys:
            warn(self, "未选择类型", "请先勾选要检测的敏感信息类型。")
            return
        with self.doc.lock:
            matches = redact_ops.find_matches(
                self.doc.fitz_doc, range(self.doc.page_count), pattern_keys=keys
            )
        self._sen_matches = matches
        self._sen_list.clear()
        for i, m in enumerate(matches):
            label = m.kind.replace("keyword:", "")
            li = QListWidgetItem(f"第 {m.page + 1} 页　[{label}]　{m.text}")
            li.setFlags(li.flags() | Qt.ItemIsUserCheckable)
            # 日期默认不勾选，与网页版一致
            li.setCheckState(Qt.Unchecked if m.kind == "date" else Qt.Checked)
            li.setData(Qt.UserRole, i)
            self._sen_list.addItem(li)
        self._status.setText(i18n.translate(f"检测到 {len(matches)} 处敏感信息"))

    def add_selected_sensitive(self) -> None:
        matches = getattr(self, "_sen_matches", [])
        added = 0
        for r in range(self._sen_list.count()):
            if self._sen_list.item(r).checkState() == Qt.Checked:
                m = matches[self._sen_list.item(r).data(Qt.UserRole)]
                self.add_rect(m.page, m.rect, snap=False)
                added += 1
        self._status.setText(i18n.translate(f"已加入 {added} 个涂销标记"))

    # ---------------------------------------------------------------- 应用

    def apply(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        if not self._rects:
            warn(self, "没有标记", "请先框选或添加要涂销的区域。")
            return
        total = sum(len(v) for v in self._rects.values())
        ret = QMessageBox.question(
            self, i18n.translate("确认涂销"),
            i18n.translate(f"将永久删除 {total} 个区域的内容，且不可撤销。建议先另存一份原件。\n确定继续？"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        label = self._label.currentText()
        overlay_text = "" if label == "(无)" else label
        options = redact_ops.RedactOptions(
            fill_color=(0, 0, 0) if self._cover.currentText() == "black" else (1, 1, 1),
            overlay_text=overlay_text,
        )

        self.doc.snapshot()
        with self.doc.lock:
            count = redact_ops.redact_rects(self.doc.fitz_doc, dict(self._rects), options)
            if self._flatten.isChecked():
                _rasterize(self.doc)
        self._rects.clear()
        self._redraw()
        self.doc.mark_dirty(structural=True)
        info(self, "涂销完成", f"已永久删除 {count} 个区域。记得保存。")


def _rasterize(doc: PdfDoc) -> None:
    """最高安全模式：把整份文档栅格化，确保无任何残留可提取内容。"""
    import pymupdf

    src = doc.fitz_doc
    out = pymupdf.open()
    for i in range(src.page_count):
        page = src.load_page(i)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"), keep_proportion=False)
    doc.load_bytes_keep_path(out.tobytes(garbage=4, deflate=1))
    out.close()


def create_panel(mainwindow, doc: PdfDoc, view: PdfView) -> RedactPanel:
    return RedactPanel(mainwindow, doc, view)
