"""工具对话框基类：统一布局、按钮与后台执行。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.doc import PdfDoc
from ..runner import run_task


class ToolDialog(QDialog):
    """带标题、内容区与「执行/关闭」按钮的工具对话框。"""

    def __init__(self, parent, doc: PdfDoc, title: str, width: int = 620, height: int = 560) -> None:
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle(title)
        self.resize(width, height)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(10)

        self._content = QVBoxLayout()
        self._content.setSpacing(8)
        self._layout.addLayout(self._content, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._layout.addWidget(self._status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self._close_btn = QPushButton("关闭")
        self._close_btn.clicked.connect(self.reject)
        self._run_btn = QPushButton("执行")
        self._run_btn.setProperty("primary", True)
        self._run_btn.clicked.connect(self.on_run)
        buttons.addWidget(self._close_btn)
        buttons.addWidget(self._run_btn)
        self._layout.addLayout(buttons)

    def showEvent(self, event) -> None:  # noqa: N802
        # 子类控件在 super().__init__ 之后才创建，因此显示时再统一重翻译
        super().showEvent(event)
        from .. import i18n

        i18n.retranslate_widget(self)

    # ---------------------------------------------------------------- 布局助手

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self._content.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        self._content.addLayout(layout)

    def add_stretch(self) -> None:
        self._content.addStretch(1)

    def set_status(self, text: str) -> None:
        self._status.setText(i18n.translate(text))

    def set_run_text(self, text: str) -> None:
        self._run_btn.setText(text)

    def set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running)
        self._close_btn.setEnabled(not running)

    # ---------------------------------------------------------------- 执行

    def on_run(self) -> None:
        raise NotImplementedError

    def run(self, title: str, fn: Callable[..., Any], *args: Any,
            on_done: Optional[Callable[[Any], None]] = None, **kwargs: Any) -> None:
        self.set_running(True)

        def _done(result: Any) -> None:
            # 对话框可能已被关闭删除，后台任务回调晚到会碰到野指针
            try:
                import shiboken6

                if not shiboken6.isValid(self):
                    return
            except Exception:  # noqa: BLE001
                pass
            if on_done is None:
                return
            try:
                on_done(result)
            except RuntimeError:
                # 子控件已随对话框销毁，忽略迟到的回调
                pass

        def _settled() -> None:
            try:
                import shiboken6

                if not shiboken6.isValid(self):
                    return
            except Exception:  # noqa: BLE001
                pass
            self.set_running(False)

        run_task(
            self, title, fn, *args,
            on_done=_done,
            on_settled=_settled,
            **kwargs,
        )
