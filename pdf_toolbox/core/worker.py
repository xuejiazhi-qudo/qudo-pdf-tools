"""后台任务基础设施：QThreadPool + QRunnable，带进度、取消与错误上报。"""

from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class CancelledError(Exception):
    """任务被用户取消。"""


class Progress:
    """传给任务函数的进度上报器。任务里定期检查 .cancelled。"""

    def __init__(self) -> None:
        self._cancelled = False
        self._signal: Optional[WorkerSignals] = None

    def bind(self, signals: "WorkerSignals") -> None:
        self._signal = signals

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def report(self, percent: int, message: str = "") -> None:
        if self._cancelled:
            raise CancelledError()
        if self._signal is not None:
            self._signal.progress.emit(max(0, min(100, int(percent))), message)

    def step(self, current: int, total: int, message: str = "") -> None:
        if total <= 0:
            self.report(0, message)
        else:
            self.report(int(current * 100 / total), message)


class WorkerSignals(QObject):
    progress = Signal(int, str)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()


class Worker(QRunnable):
    """把一个普通函数丢到线程池执行。

    fn 若声明了名为 `progress` 的参数，会自动注入 Progress 实例。
    """

    def __init__(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.progress = Progress()
        self.progress.bind(self.signals)
        self.setAutoDelete(True)

    def cancel(self) -> None:
        self.progress.cancel()

    def run(self) -> None:  # noqa: D102 - QRunnable 接口
        try:
            kwargs = dict(self.kwargs)
            try:
                import inspect

                if "progress" in inspect.signature(self.fn).parameters:
                    kwargs["progress"] = self.progress
            except (TypeError, ValueError):
                pass

            result = self.fn(*self.args, **kwargs)
        except CancelledError:
            self.signals.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - 统一上报给 UI
            detail = traceback.format_exc(limit=6)
            self.signals.failed.emit(f"{exc}\n\n{detail}")
        else:
            self.signals.finished.emit(result)


class TaskPool:
    """全局线程池包装，保留 worker 引用避免被提前回收。"""

    _instance: Optional["TaskPool"] = None

    def __init__(self) -> None:
        self._pool = QThreadPool.globalInstance()
        self._active: set[Worker] = set()

    @classmethod
    def instance(cls) -> "TaskPool":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def submit(
        self,
        fn: Callable[..., Any],
        *args: Any,
        on_done: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, str], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
        **kwargs: Any,
    ) -> Worker:
        worker = Worker(fn, *args, **kwargs)
        self._active.add(worker)

        def _cleanup() -> None:
            self._active.discard(worker)

        if on_done is not None:
            worker.signals.finished.connect(on_done)
        if on_error is not None:
            worker.signals.failed.connect(on_error)
        if on_progress is not None:
            worker.signals.progress.connect(on_progress)
        if on_cancel is not None:
            worker.signals.cancelled.connect(on_cancel)
        worker.signals.finished.connect(_cleanup)
        worker.signals.failed.connect(_cleanup)
        worker.signals.cancelled.connect(_cleanup)

        self._pool.start(worker)
        return worker

    def cancel_all(self) -> None:
        for w in list(self._active):
            w.cancel()

    def wait(self, msecs: int = -1) -> bool:
        return self._pool.waitForDone(msecs)
