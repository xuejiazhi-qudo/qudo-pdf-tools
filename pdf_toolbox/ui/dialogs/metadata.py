"""PDF 元数据：查看、编辑、清除隐藏信息。"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Dict

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from ...core.doc import PdfDoc
from ...core.ops import extract
from ..theme import human_size
from ..widgets import info, warn
from .. import i18n
from .base import ToolDialog

RECOMMENDED = [
    ("metadata", "标准元数据（标题/作者/主题/关键词/创建与修改时间/Creator/Producer）"),
    ("xmp", "XMP 扩展元数据"),
    ("hidden_text", "隐藏文字（不可见文本层）"),
    ("javascript", "内嵌 JavaScript"),
    ("attachments", "附件 / 内嵌文件"),
    ("thumbnails", "页面缩略图"),
]
ADVANCED = [
    ("links", "链接（会破坏目录跳转）"),
    ("annotations", "所有批注（会丢失标注）"),
    ("reset_fields", "表单填写内容"),
    ("redactions", "未应用的涂销标记"),
    ("clean_pages", "清理页面内容流"),
]


class MetadataDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 元数据清除", 980, 720)
        self.set_run_text("应用清理")
        self._report: extract.MetadataInfo | None = None

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._view = QTextEdit()
        self._view.setReadOnly(True)
        left_layout.addWidget(self._view, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        edit_group = QGroupBox("编辑元数据（留空=清除）")
        edit_layout = QFormLayout(edit_group)
        self._fields: Dict[str, QLineEdit] = {}
        for key, label in (
            ("title", "标题"), ("author", "作者"), ("subject", "主题"),
            ("keywords", "关键词"), ("creator", "创建程序"), ("producer", "生产者"),
        ):
            edit = QLineEdit()
            self._fields[key] = edit
            edit_layout.addRow(label, edit)
        apply_edit = QPushButton("写入这些元数据")
        apply_edit.clicked.connect(self.apply_edits)
        edit_layout.addRow("", apply_edit)
        right_layout.addWidget(edit_group)

        rec_group = QGroupBox("推荐清理（默认开启）")
        rec_layout = QVBoxLayout(rec_group)
        self._checks: Dict[str, QCheckBox] = {}
        for key, label in RECOMMENDED:
            cb = QCheckBox(label)
            cb.setChecked(True)
            self._checks[key] = cb
            rec_layout.addWidget(cb)
        right_layout.addWidget(rec_group)

        adv_group = QGroupBox("高级清理（默认关闭，可能破坏内容）")
        adv_layout = QVBoxLayout(adv_group)
        for key, label in ADVANCED:
            cb = QCheckBox(label)
            cb.setChecked(False)
            self._checks[key] = cb
            adv_layout.addWidget(cb)
        right_layout.addWidget(adv_group)

        bar = QHBoxLayout()
        reset = QPushButton("恢复默认")
        reset.clicked.connect(self._reset_defaults)
        bar.addWidget(reset)
        report_btn = QPushButton("导出清理报告…")
        report_btn.clicked.connect(self.export_report)
        bar.addWidget(report_btn)
        bar.addStretch(1)
        right_layout.addLayout(bar)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setSizes([560, 400])
        self.add(splitter, 1)

        self.scan()

    # ---------------------------------------------------------------- 读取

    def scan(self) -> None:
        def _done(report: extract.MetadataInfo) -> None:
            self._report = report
            for key, edit in self._fields.items():
                edit.setText(report.standard.get(key, "") or "")
            self._render(report)

        self.run("读取元数据", extract.read_metadata, self.doc.path, on_done=_done)

    def on_run(self) -> None:
        self.apply_clean()

    def _render(self, r: extract.MetadataInfo) -> None:
        lines = []
        lines.append("=== 基本信息 ===")
        lines.append(f"文件：{self.doc.path}")
        try:
            lines.append(f"大小：{human_size(os.path.getsize(self.doc.path))}")
        except OSError:
            pass
        lines.append(f"页数：{self.doc.page_count}")
        lines.append(f"格式：{r.standard.get('format', '')}")
        lines.append(f"加密：{'是' if self.doc.is_encrypted else '否'}")
        lines.append("")
        lines.append("=== 标准元数据 ===")
        for key in ("title", "author", "subject", "keywords", "creator", "producer",
                    "creationDate", "modDate"):
            value = r.standard.get(key, "")
            lines.append(f"{key}: {value or '(空)'}")
        lines.append("")
        lines.append("=== 隐藏信息 ===")
        lines.append(f"XMP 元数据：{'有' if r.xmp else '无'}")
        if r.xmp:
            snippet = r.xmp[:200].replace("\n", " ")
            lines.append(f"  预览：{snippet}…")
        lines.append(f"附件/内嵌文件：{len(r.embedded_files)} 个")
        for name in r.embedded_files:
            lines.append(f"  - {name}")
        lines.append(f"批注：{r.annotations} 个")
        lines.append(f"链接：{r.links} 个")
        lines.append(f"表单字段：{r.form_fields} 个")
        lines.append(f"内嵌 JavaScript：{'有' if r.javascript else '无'}")
        lines.append(f"书签/目录条目：{r.outline_entries} 个")
        lines.append("")
        lines.append("=== 字体 ===")
        lines.append(", ".join(r.fonts) or "(无)")
        lines.append("")
        lines.append(f"内嵌图片对象：{r.image_count} 个")
        self._view.setPlainText("\n".join(lines))

    def _reset_defaults(self) -> None:
        for key, _label in RECOMMENDED:
            self._checks[key].setChecked(True)
        for key, _label in ADVANCED:
            self._checks[key].setChecked(False)

    # ---------------------------------------------------------------- 操作

    def apply_edits(self) -> None:
        values = {key: edit.text() for key, edit in self._fields.items()}
        self.doc.snapshot()
        extract.set_metadata_values(self.doc.fitz_doc, values)
        self.doc.mark_dirty()
        info(self, "已写入", "元数据已更新，记得保存。")
        self.scan()

    def apply_clean(self) -> None:
        options = extract.CleanOptions(
            metadata=self._checks["metadata"].isChecked(),
            xmp=self._checks["xmp"].isChecked(),
            hidden_text=self._checks["hidden_text"].isChecked(),
            javascript=self._checks["javascript"].isChecked(),
            embedded_files=self._checks["attachments"].isChecked(),
            attachments=self._checks["attachments"].isChecked(),
            links=self._checks["links"].isChecked(),
            thumbnails=self._checks["thumbnails"].isChecked(),
            annotations=self._checks["annotations"].isChecked(),
            reset_fields=self._checks["reset_fields"].isChecked(),
            redactions=self._checks["redactions"].isChecked(),
            clean_pages=self._checks["clean_pages"].isChecked(),
        )
        risky = [k for k in ("links", "annotations", "reset_fields") if self._checks[k].isChecked()]
        if risky:
            from PySide6.QtWidgets import QMessageBox

            ret = QMessageBox.question(
                self, i18n.translate("确认高级清理"),
                i18n.translate("勾选的高级清理项可能破坏链接、批注或表单内容，确定继续？"),
                QMessageBox.Yes | QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return

        self.doc.snapshot()
        removed = extract.clean_metadata(self.doc.fitz_doc, options)
        self.doc.mark_dirty()
        cleared = removed.get("metadata", {})
        info(
            self, "清理完成",
            "已清除：\n" + "\n".join(f"- {k}: {v}" for k, v in cleared.items() if v) or "无标准元数据",
        )
        self.scan()

    def export_report(self) -> None:
        if self._report is None:
            warn(self, "尚未读取", "请先等待元数据读取完成。")
            return
        from PySide6.QtWidgets import QFileDialog

        path = QFileDialog.getSaveFileName(
            self, "保存报告", f"{os.path.splitext(self.doc.title)[0]}-metadata-report.txt", "*.txt"
        )[0]
        if not path:
            return
        r = self._report
        lines = [
            f"PDF 元数据报告",
            f"生成时间：{_dt.datetime.now():%Y-%m-%d %H:%M:%S}",
            f"文件：{self.doc.path}",
            f"页数：{self.doc.page_count}",
            "",
            "[标准元数据]",
        ]
        lines += [f"{k} = {v}" for k, v in r.standard.items() if v]
        lines += ["", "[隐藏信息]",
                  f"xmp = {'yes' if r.xmp else 'no'}",
                  f"attachments = {len(r.embedded_files)}",
                  f"annotations = {r.annotations}",
                  f"links = {r.links}",
                  f"form_fields = {r.form_fields}",
                  f"javascript = {'yes' if r.javascript else 'no'}",
                  "", "[字体]", ", ".join(r.fonts)]
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        info(self, "已导出", path)


def create(parent, doc: PdfDoc) -> MetadataDialog:
    return MetadataDialog(parent, doc)
