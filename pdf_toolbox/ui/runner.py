"""后台任务运行器：带进度条与取消按钮的模态对话框。"""

from __future__ import annotations

from typing import Any, Callable, Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..core.worker import TaskPool, Worker


class ProgressDialog(QDialog):
    def __init__(self, parent, title: str, cancellable: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(430)
        self.on_cancel: Optional[Callable[[], None]] = None

        layout = QVBoxLayout(self)
        self._label = QLabel("准备中…")
        self._label.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)

        layout.addWidget(self._label)
        layout.addWidget(self._bar)

        if cancellable:
            row = QHBoxLayout()
            row.addStretch(1)
            btn = QPushButton("取消")
            btn.clicked.connect(self._cancel_clicked)
            row.addWidget(btn)
            layout.addLayout(row)

    def _cancel_clicked(self) -> None:
        self._label.setText("正在取消…")
        if self.on_cancel is not None:
            self.on_cancel()

    def update(self, percent: int, message: str) -> None:
        self._bar.setValue(max(0, min(100, percent)))
        if message:
            self._label.setText(message)


def run_task(
    parent,
    title: str,
    fn: Callable[..., Any],
    *args: Any,
    on_done: Optional[Callable[[Any], None]] = None,
    on_settled: Optional[Callable[[], None]] = None,
    cancellable: bool = True,
    **kwargs: Any,
) -> Worker:
    """在后台线程执行 fn，期间显示模态进度对话框。

    fn 若声明了 progress 参数会自动注入；完成调用 on_done(result)；
    失败弹出错误框；取消则静默关闭；三种结局之后都会调用 on_settled。
    """
    dialog = ProgressDialog(parent, title, cancellable)
    from . import i18n

    i18n.retranslate_widget(dialog)
    worker = TaskPool.instance().submit(fn, *args, **kwargs)
    dialog.on_cancel = worker.cancel

    def _safe(call) -> None:
        # 进度对话框可能已被 deleteLater，信号晚到会抛 RuntimeError
        try:
            call()
        except RuntimeError:
            pass

    def _progress(percent: int, message: str) -> None:
        _safe(lambda: dialog.update(percent, message))

    def _finished(result: Any) -> None:
        _safe(lambda: dialog.accept())
        _safe(lambda: dialog.deleteLater())
        if on_done is not None:
            on_done(result)
        if on_settled is not None:
            on_settled()

    def _failed(detail: str) -> None:
        _safe(lambda: dialog.reject())
        _safe(lambda: dialog.deleteLater())
        lines = [l for l in detail.strip().splitlines() if l.strip()]
        first = lines[0] if lines else "未知错误"
        QMessageBox.critical(parent, f"{title}：失败", f"{first}\n\n{detail}")
        if on_settled is not None:
            on_settled()

    def _cancelled() -> None:
        _safe(lambda: dialog.reject())
        _safe(lambda: dialog.deleteLater())
        if on_settled is not None:
            on_settled()

    worker.signals.progress.connect(_progress)
    worker.signals.finished.connect(_finished)
    worker.signals.failed.connect(_failed)
    worker.signals.cancelled.connect(_cancelled)

    dialog.show()
    return worker
