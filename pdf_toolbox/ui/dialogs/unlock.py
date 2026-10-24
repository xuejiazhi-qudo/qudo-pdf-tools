"""解除 PDF 密码（批量）。"""

from __future__ import annotations

import os
import zipfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QRadioButton,
)

from ...core.doc import PdfDoc
from ...core.ops import security
from ..theme import human_size
from ..widgets import OutputPathField, error, info, warn
from .base import ToolDialog


class UnlockDialog(ToolDialog):
    def __init__(self, parent, doc: PdfDoc) -> None:
        super().__init__(parent, doc, "解除 PDF 密码", 640, 660)
        self.set_run_text("解除密码")

        bar = QHBoxLayout()
        add = QPushButton("添加文件…")
        add.clicked.connect(self.add_files)
        remove = QPushButton("移除")
        remove.clicked.connect(self.remove_selected)
        detect = QPushButton("检测")
        detect.clicked.connect(self.detect)
        bar.addWidget(add)
        bar.addWidget(remove)
        bar.addWidget(detect)
        bar.addStretch(1)
        self.add_layout(bar)

        self._list = QListWidget()
        self.add(self._list, 1)

        pw_group = QGroupBox("密码")
        pl = QFormLayout(pw_group)
        pl.setLabelAlignment(Qt.AlignRight)
        mode_box = QHBoxLayout()
        self._single = QRadioButton("所有文件用同一个密码")
        self._separate = QRadioButton("每个文件单独输入")
        self._single.setChecked(True)
        self._single.toggled.connect(self._sync)
        mode_box.addWidget(self._single)
        mode_box.addWidget(self._separate)
        pl.addRow("模式", mode_box)
        self._pw = QLineEdit()
        self._pw.setEchoMode(QLineEdit.Password)
        pl.addRow("密码", self._pw)
        self.add(pw_group)

        self._auth = QCheckBox("我确认有权解除这些文件的密码保护")
        self.add(self._auth)

        self._out = OutputPathField("选择输出目录", is_dir=True)
        self.add(self._out)
        self._zip = QCheckBox("多个文件时打包 ZIP")
        self._zip.setChecked(True)
        self.add(self._zip)
        self.add_stretch()
        self._sync()

    def _sync(self, *_args) -> None:
        self._pw.setVisible(self._single.isChecked())

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 PDF", "", "PDF (*.pdf)")
        for path in paths:
            self._add_row(path)

    def _add_row(self, path: str) -> None:
        item = QListWidgetItem(os.path.basename(path))
        item.setData(Qt.UserRole, {"path": path, "pw": "", "status": "待检测", "sig": False})
        self._list.addItem(item)
        self._refresh_row(self._list.count() - 1)

    def remove_selected(self) -> None:
        for item in reversed(self._list.selectedItems()):
            self._list.takeItem(self._list.row(item))

    def _refresh_row(self, row: int) -> None:
        item = self._list.item(row)
        data = item.data(Qt.UserRole)
        sig = "　⚠含数字签名" if data.get("sig") else ""
        item.setText(f"{os.path.basename(data['path'])}　[{data['status']}]{sig}")

    def detect(self) -> None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            data = item.data(Qt.UserRole)
            try:
                info_ = security.probe_encryption(data["path"])
                data["status"] = "已加密" if info_["encrypted"] else "未加密"
                data["sig"] = False
                try:
                    import pymupdf

                    with pymupdf.open(data["path"]) as d:
                        raw = b""
                        for xref in range(1, min(d.xref_length(), 400)):
                            obj = d.xref_object(xref, compressed=True) or ""
                            if "/Type /Sig" in obj or "/DocTimeRef" in obj:
                                data["sig"] = True
                                break
                except Exception:  # noqa: BLE001
                    pass
            except Exception as exc:  # noqa: BLE001
                data["status"] = f"检测失败：{exc}"
            item.setData(Qt.UserRole, data)
            self._refresh_row(row)

    def on_run(self) -> None:
        if not self._auth.isChecked():
            warn(self, "需要授权确认", "请先勾选授权确认复选框。")
            return
        out_dir = self._out.text()
        if not out_dir:
            error(self, "缺少输出目录", "请选择输出目录。")
            return

        rows = list(range(self._list.count()))
        if not rows:
            error(self, "没有文件", "请先添加要解密的 PDF。")
            return

        passwords = {}
        if self._single.isChecked():
            passwords = {r: self._pw.text() for r in rows}
        else:
            for r in rows:
                pw, ok = QInputDialog_getText(self, r)
                if not ok:
                    return
                passwords[r] = pw

        def _work(progress):
            results = []
            for i, r in enumerate(rows):
                data = self._list.item(r).data(Qt.UserRole)
                progress.step(i, len(rows), f"解密 {os.path.basename(data['path'])}")
                base = os.path.splitext(os.path.basename(data["path"]))[0]
                target = os.path.join(out_dir, f"{base}-unlocked.pdf")
                security.decrypt_file(data["path"], target, passwords[r])
                results.append(target)
            if self._zip.isChecked() and len(results) > 1:
                zip_path = os.path.join(out_dir, "unlocked-pdfs.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for f in results:
                        zf.write(f, os.path.basename(f))
                results.append(zip_path)
            return results

        def _done(results) -> None:
            info(self, "解密完成", "\n".join(results))

        self.run("解除密码", _work, on_done=_done)


def QInputDialog_getText(parent, row: int):
    from PySide6.QtWidgets import QInputDialog

    item = parent._list.item(row)
    return QInputDialog.getText(
        parent, "输入密码", f"《{os.path.basename(item.data(Qt.UserRole)['path'])}》的密码：",
        echo=QInputDialog.Password,
    )


def create(parent, doc: PdfDoc) -> UnlockDialog:
    return UnlockDialog(parent, doc)
