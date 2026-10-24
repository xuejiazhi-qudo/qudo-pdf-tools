"""文档会话模型：封装 pymupdf.Document，提供渲染缓存、撤销/重做与脏标记。

所有对 PyMuPDF 的访问都走同一把可重入锁 —— Document 不是线程安全的，
而页面渲染必须放到后台线程执行。
"""

from __future__ import annotations

import os
import threading
from typing import Any, Dict, List, Optional, Tuple

import pymupdf
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage

MAX_UNDO_STEPS = 12
# 超过这个体积就不再做内存快照，避免撤销栈把内存吃满
MAX_SNAPSHOT_BYTES = 80 * 1024 * 1024
_CACHE_BUDGET = 384 * 1024 * 1024

# 无损保存参数：清理未引用对象 + 压缩流 + 对象流
SAVE_OPTS: Dict[str, Any] = dict(garbage=4, deflate=1, use_objstms=1)


class PasswordRequiredError(Exception):
    """文档被加密且尚未通过密码验证。"""


class WrongPasswordError(Exception):
    pass


def _to_qimage(pix: pymupdf.Pixmap) -> QImage:
    """Pixmap -> QImage。必须 copy()，否则 samples 内存随 Pixmap 释放而失效。"""
    if pix.alpha:
        fmt = QImage.Format_RGBA8888
    elif pix.colorspace and pix.colorspace.n == 4:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        fmt = QImage.Format_RGB888
    else:
        fmt = QImage.Format_RGB888
    return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()


class PdfDoc(QObject):
    """一个打开的 PDF 文档。"""

    changed = Signal()              # 页面内容变化（需要重渲染）
    structureChanged = Signal()     # 页数变化（需要重建缩略图）
    dirtyChanged = Signal(bool)
    titleChanged = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._doc: Optional[pymupdf.Document] = None
        self._path: Optional[str] = None
        self._display_name: str = "未命名.pdf"
        self._dirty = False
        self._undo: List[bytes] = []
        self._redo: List[bytes] = []
        self._render_cache: Dict[Tuple[int, float, int], QImage] = {}
        self._cache_order: List[Tuple[int, float, int]] = []
        self._revision = 0
        self._snapshot_enabled = True
        self._password: Optional[str] = None

    # ------------------------------------------------------------------ 打开/关闭

    @property
    def is_open(self) -> bool:
        return self._doc is not None

    @property
    def path(self) -> Optional[str]:
        return self._path

    @property
    def title(self) -> str:
        return os.path.basename(self._path) if self._path else self._display_name

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def fitz_doc(self) -> pymupdf.Document:
        if self._doc is None:
            raise RuntimeError("没有打开的文档")
        return self._doc

    def open(self, path: str, password: Optional[str] = None) -> None:
        with self._lock:
            doc = pymupdf.open(path)
            if doc.needs_pass:
                if not password:
                    doc.close()
                    raise PasswordRequiredError(path)
                if not doc.authenticate(password):
                    doc.close()
                    raise WrongPasswordError(path)

            self._close_unlocked()
            self._doc = doc
            self._path = path
            self._display_name = os.path.basename(path)
            self._password = password
            self._reset_state(self._size_on_disk(path) <= MAX_SNAPSHOT_BYTES)

    def open_bytes(self, data: bytes, name: str = "未命名.pdf") -> None:
        with self._lock:
            doc = pymupdf.open(stream=data, filetype="pdf")
            self._close_unlocked()
            self._doc = doc
            self._path = None
            self._display_name = name
            self._password = None
            self._reset_state(len(data) <= MAX_SNAPSHOT_BYTES)

    def new_blank(
        self,
        page_count: int = 1,
        width: float = 595.28,
        height: float = 841.89,
        background: Tuple[int, int, int] = (255, 255, 255),
        name: str = "未命名.pdf",
    ) -> None:
        """新建空白文档（尚未落盘），之后可直接标注/填写/加水印再保存。"""
        count = max(1, int(page_count))
        with self._lock:
            doc = pymupdf.open()
            for _ in range(count):
                page = doc.new_page(width=max(20.0, width), height=max(20.0, height))
                if tuple(background) != (255, 255, 255):
                    page.draw_rect(
                        page.rect,
                        color=None,
                        fill=tuple(c / 255 for c in background),
                    )
            self._close_unlocked()
            self._doc = doc
            self._path = None
            self._display_name = name
            self._password = None
            self._reset_state(True)
        self.mark_dirty()

    def _reset_state(self, snapshot_enabled: bool) -> None:
        self._dirty = False
        self._undo.clear()
        self._redo.clear()
        self._render_cache.clear()
        self._cache_order.clear()
        self._revision += 1
        self._snapshot_enabled = snapshot_enabled
        self.dirtyChanged.emit(False)
        self.titleChanged.emit(self.title)
        self.structureChanged.emit()

    def _close_unlocked(self) -> None:
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:
                pass
        self._doc = None

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()
            self._path = None
            self._display_name = "未命名.pdf"
            self._dirty = False
            self._undo.clear()
            self._redo.clear()
            self._render_cache.clear()
            self._cache_order.clear()
            self._revision += 1

    @staticmethod
    def _size_on_disk(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def load_bytes_keep_path(self, data: bytes) -> None:
        """用新的 PDF 字节替换内容，但保留当前文件路径（页面整理用）。"""
        with self._lock:
            new = pymupdf.open(stream=data, filetype="pdf")
            old = self._doc
            self._doc = new
            if old is not None:
                try:
                    old.close()
                except Exception:
                    pass
            self._undo.clear()
            self._redo.clear()
            self._render_cache.clear()
            self._cache_order.clear()
            self._revision += 1
            self._snapshot_enabled = len(data) <= MAX_SNAPSHOT_BYTES

        self._dirty = True
        self.changed.emit()
        self.structureChanged.emit()
        self.dirtyChanged.emit(True)

    # ------------------------------------------------------------------ 加密状态

    @property
    def is_encrypted(self) -> bool:
        with self._lock:
            return bool(self._doc is not None and self._doc.is_encrypted)

    @property
    def needs_password(self) -> bool:
        with self._lock:
            return bool(self._doc is not None and self._doc.needs_pass)

    @property
    def permissions(self) -> int:
        with self._lock:
            return int(self._doc.permissions) if self._doc is not None else 0

    # ------------------------------------------------------------------ 页面

    @property
    def page_count(self) -> int:
        with self._lock:
            return self._doc.page_count if self._doc is not None else 0

    def page_rect(self, index: int) -> pymupdf.Rect:
        with self._lock:
            return self._doc.load_page(index).rect

    def page_rotation(self, index: int) -> int:
        with self._lock:
            return self._doc.load_page(index).rotation

    def page_sizes(self) -> List[Tuple[float, float]]:
        with self._lock:
            return [
                (p.rect.width, p.rect.height)
                for p in self._doc.pages()
            ]

    def metadata(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._doc.metadata or {})

    # ------------------------------------------------------------------ 渲染

    def render(self, index: int, zoom: float) -> QImage:
        """渲染第 index 页为 QImage，带缓存。可在后台线程调用。"""
        if not 0 <= index < self.page_count:
            return QImage()

        key = (index, round(zoom, 4), self._revision)
        cached = self._render_cache.get(key)
        if cached is not None:
            return cached

        with self._lock:
            if self._doc is None or not 0 <= index < self._doc.page_count:
                return QImage()
            page = self._doc.load_page(index)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = _to_qimage(pix)

        self._cache_put(key, img)
        return img

    def thumbnail(self, index: int, max_side: int = 180) -> QImage:
        with self._lock:
            if self._doc is None or not 0 <= index < self._doc.page_count:
                return QImage()
            page = self._doc.load_page(index)
            rect = page.rect
            zoom = max_side / max(rect.width, rect.height, 1.0)
            zoom = min(max(zoom, 0.05), 2.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return _to_qimage(pix)

    def _cache_put(self, key: Tuple[int, float, int], img: QImage) -> None:
        self._render_cache[key] = img
        self._cache_order.append(key)
        total = sum(im.sizeInBytes() for im in self._render_cache.values())
        while total > _CACHE_BUDGET and self._cache_order:
            old = self._cache_order.pop(0)
            removed = self._render_cache.pop(old, None)
            if removed is not None:
                total -= removed.sizeInBytes()

    def invalidate_cache(self) -> None:
        self._render_cache.clear()
        self._cache_order.clear()
        self._revision += 1

    # ------------------------------------------------------------------ 变更/撤销

    def mark_dirty(self, structural: bool = False) -> None:
        was = self._dirty
        self._dirty = True
        self.invalidate_cache()
        self.changed.emit()
        if structural:
            self.structureChanged.emit()
        if not was:
            self.dirtyChanged.emit(True)

    def snapshot(self) -> None:
        """在改动前调用，把当前状态压入撤销栈。"""
        if not self._snapshot_enabled or self._doc is None:
            return
        with self._lock:
            data = self._doc.tobytes(garbage=0, deflate=0)
        self._undo.append(data)
        if len(self._undo) > MAX_UNDO_STEPS:
            self._undo.pop(0)
        self._redo.clear()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo) and self._snapshot_enabled

    @property
    def can_redo(self) -> bool:
        return bool(self._redo) and self._snapshot_enabled

    @property
    def undo_enabled(self) -> bool:
        return self._snapshot_enabled

    def undo(self) -> bool:
        if not self._undo:
            return False
        with self._lock:
            current = self._doc.tobytes(garbage=0, deflate=0)
            self._redo.append(current)
            self._reload(self._undo.pop())
        self._after_history()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        with self._lock:
            current = self._doc.tobytes(garbage=0, deflate=0)
            self._undo.append(current)
            self._reload(self._redo.pop())
        self._after_history()
        return True

    def _after_history(self) -> None:
        self._dirty = True
        self.invalidate_cache()
        self.changed.emit()
        self.structureChanged.emit()
        self.dirtyChanged.emit(True)

    def _reload(self, data: bytes) -> None:
        new = pymupdf.open(stream=data, filetype="pdf")
        old = self._doc
        self._doc = new
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ 保存

    def save_bytes(self, **kwargs: Any) -> bytes:
        opts: Dict[str, Any] = dict(SAVE_OPTS)
        opts.update(kwargs)
        with self._lock:
            return self._doc.tobytes(**opts)

    def save(self, path: Optional[str] = None, **kwargs: Any) -> str:
        """保存到 path（默认原路径）。

        Windows 下 PyMuPDF 会一直持有已打开文件的句柄，直接 os.replace 覆盖
        自己正打开的文件会 WinError 5。因此顺序是：写 .part 临时文件 ->
        关闭当前文档释放句柄 -> 原子替换 -> 重新打开。
        """
        target = path or self._path
        if not target:
            raise RuntimeError("没有指定保存路径")

        data = self.save_bytes(**kwargs)
        tmp = target + ".part"
        with open(tmp, "wb") as fh:
            fh.write(data)

        same = bool(self._path) and os.path.abspath(target) == os.path.abspath(self._path)
        with self._lock:
            self._close_unlocked()          # 释放 Windows 文件句柄
            os.replace(tmp, target)
            self._doc = pymupdf.open(target)
            if self._doc.needs_pass and self._password:
                if not self._doc.authenticate(self._password):
                    self._doc.close()
                    raise RuntimeError("保存后重新打开失败：密码不正确")
            if not same:
                self._path = target
                self._display_name = os.path.basename(target)

        self._dirty = False
        self.invalidate_cache()
        self.dirtyChanged.emit(False)
        self.titleChanged.emit(self.title)
        self.changed.emit()
        self.structureChanged.emit()
        return target
