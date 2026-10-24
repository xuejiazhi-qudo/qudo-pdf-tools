"""PDF 加密与密码保护（批量）。"""

from __future__ import annotations

import os
import zipfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from ...core.doc import PdfDoc
from ...core.ops import security
from .. import i18n
from ..theme import human_size
from ..widgets import OutputPathField, error, info, warn
from .base import ToolDialog


def password_strength(pw: str) -> tuple:
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    if len(pw) >= 16:
        score += 1
    if any(c.islower() for c in pw):
        score += 1
    if any(c.isupper() for c in pw):
        score += 1
    if any(c.isdigit() for c in pw):
        score += 1
    if any(not c.isalnum() for c in pw):
        score += 1
    if score <= 2:
        return "weak", "弱"
    if score <= 4:
        return "medium", "中"
    return "strong", "强"


class ProtectDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "PDF 加密与密码保护", 640, 700)
        self.set_run_text("加密")

        bar = QHBoxLayout()
        add = QPushButton("添加文件…")
        add.clicked.connect(self.add_files)
        remove = QPushButton("移除")
        remove.clicked.connect(self.remove_selected)
        use_current = QPushButton("使用当前文档")
        use_current.clicked.connect(self.use_current)
        bar.addWidget(add)
        bar.addWidget(remove)
        bar.addWidget(use_current)
        bar.addStretch(1)
        self.add_layout(bar)

        self._list = QListWidget()
        self.add(self._list, 1)

        pw_group = QGroupBox("密码")
        pl = QFormLayout(pw_group)
        pl.setLabelAlignment(Qt.AlignRight)
        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.Password)
        self._pw.textChanged.connect(self._strength)
        pl.addRow("打开密码", self._pw)
        self._pw2 = QLineEdit()
        self._pw2.setEchoMode(QLineEdit.Password)
        pl.addRow("确认密码", self._pw2)
        self._show = QCheckBox("显示密码")
        self._show.toggled.connect(
            lambda on: (
                self._pw.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
                self._pw2.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password),
            )
        )
        pl.addRow("", self._show)
        self._strength_label = QLabel("")
        pl.addRow("强度", self._strength_label)
        self.add(pw_group)

        opt_group = QGroupBox("加密选项（网页版没有暴露权限位，这里补齐）")
        ol = QFormLayout(opt_group)
        ol.setLabelAlignment(Qt.AlignRight)
        self._algo = QComboBox()
        for key, label in security.ALGO_LABELS.items():
            self._algo.addItem(label, key)
        ol.addRow("算法", self._algo)
        self._perm_checks = {}
        perm_box = QVBoxLayout()
        for p in security.PERMISSION_DEFS:
            cb = QCheckBox(p.label)
            cb.setChecked(p.default)
            self._perm_checks[p.key] = cb
            perm_box.addWidget(cb)
        ol.addRow("允许的操作", perm_box)
        self.add(opt_group)

        self._out = OutputPathField("选择输出目录", is_dir=True)
        self.add(self._out)
        self._zip = QCheckBox("多个文件时打包 ZIP")
        self._zip.setChecked(True)
        self.add(self._zip)
        self.add_stretch()

    def _strength(self, text: str) -> None:
        if not text:
            self._strength_label.setText("")
            return
        key, label = password_strength(text)
        color = {"weak": "#b3372f", "medium": "#b07a1e", "strong": "#2e7d32"}[key]
        self._strength_label.setText(
            f"<span style='color:{color}'>{i18n.translate(label)}</span>"
        )

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", "", "PDF (*.pdf)")
        for path in paths:
            self._list.addItem(QListWidgetItem(f"{os.path.basename(path)}　{human_size(os.path.getsize(path))}"))
            self._list.item(self._list.count() - 1).setData(Qt.UserRole, path)

    def remove_selected(self) -> None:
        for item in reversed(self._list.selectedItems()):
            self._list.takeItem(self._list.row(item))

    def use_current(self) -> None:
        if not self.doc.path:
            warn(self, "没有打开的文档", "请先打开一个 PDF。")
            return
        path = self.doc.path
        self._list.addItem(QListWidgetItem(f"{os.path.basename(path)}　(当前文档)"))
        self._list.item(self._list.count() - 1).setData(Qt.UserRole, path)

    def _paths(self):
        return [self._list.item(r).data(Qt.UserRole) for r in range(self._list.count())]

    def on_run(self) -> None:
        paths = self._paths()
        if not paths:
            error(self, "没有文件", "请先添加要加密的 PDF。")
            return
        pw = self._pw.text()
        if pw != self._pw2.text():
            error(self, "密码不一致", "两次输入的密码不相同。")
            return
        if not pw:
            error(self, "缺少密码", "请设置打开密码。")
            return
        out_dir = self._out.text()
        if not out_dir:
            error(self, "缺少输出目录", "请选择输出目录。")
            return

        options = security.EncryptOptions(
            user_password=pw,
            owner_password="",
            algorithm=self._algo.currentData(),
            permission_keys=[k for k, cb in self._perm_checks.items() if cb.isChecked()],
        )

        def _work(progress):
            results = []
            for i, path in enumerate(paths):
                progress.step(i, len(paths), f"加密 {os.path.basename(path)}")
                base = os.path.splitext(os.path.basename(path))[0]
                target = os.path.join(out_dir, f"{base}-protected.pdf")
                security.encrypt_file(path, target, options, progress=None)
                results.append(target)
            if self._zip.isChecked() and len(results) > 1:
                zip_path = os.path.join(out_dir, "protected-pdfs.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in results:
                        zf.write(f, os.path.basename(f))
                results.append(zip_path)
            return results

        def _done(results) -> None:
            info(self, "加密完成", "\n".join(results))

        self.run("加密 PDF", _work, on_done=_done)


def create(parent, doc: PdfDoc) -> ProtectDialog:
    return ProtectDialog(parent, doc)
