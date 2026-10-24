"""页面级操作：合并、拆分、旋转、裁剪、页面整理、PDF 转图片、图片转 PDF。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pymupdf

from .. import pagerange
from ..worker import Progress

Progress_ = Optional[Progress]


def _noop() -> Progress:
    return Progress()


def _pg(progress: Progress_) -> Progress:
    return progress if progress is not None else _noop()


# ====================================================================== 合并


@dataclass
class MergeInput:
    """一个待合并的输入文件。pages 为空表示全部页。"""

    path: str
    password: Optional[str] = None
    pages: List[int] = field(default_factory=list)
    label: str = ""

    @property
    def name(self) -> str:
        return self.label or os.path.basename(self.path)


def merge_pdfs(
    inputs: Sequence[MergeInput],
    output: str,
    progress: Progress_ = None,
) -> str:
    """按顺序把多个 PDF（或其中选中的页面）合并成 output。"""
    pr = _pg(progress)
    if not inputs:
        raise ValueError("没有要合并的文件")

    out = pymupdf.open()
    total = len(inputs)
    opened: List[pymupdf.Document] = []
    try:
        for i, item in enumerate(inputs):
            pr.step(i, total, f"合并 {item.name}")
            src = pymupdf.open(item.path)
            if src.needs_pass:
                if not item.password or not src.authenticate(item.password):
                    src.close()
                    raise ValueError(f"《{item.name}》需要密码或密码不正确")
            opened.append(src)

            if item.pages:
                for p in item.pages:
                    if 0 <= p < src.page_count:
                        out.insert_pdf(src, from_page=p, to_page=p)
            else:
                out.insert_pdf(src)
        pr.report(95, "正在写出文件")
        _safe_dir(output)
        out.save(output, garbage=4, deflate=1, use_objstms=1)
    finally:
        for d in opened:
            try:
                d.close()
            except Exception:
                pass
        out.close()

    pr.report(100, "完成")
    return output


# ====================================================================== 拆分

SPLIT_RANGES = "ranges"       # 按自定义范围，每段一个文件
SPLIT_FIXED = "fixed"         # 每 n 页一个文件
SPLIT_SINGLE = "single"       # 每页一个文件
SPLIT_PARTS = "parts"         # 平均切成 n 份
SPLIT_EVEN_ODD = "even_odd"   # 奇偶页分开


@dataclass
class SplitResult:
    files: List[str]
    skipped: int = 0


def split_pdf(
    src_path: str,
    out_dir: str,
    mode: str = SPLIT_RANGES,
    ranges: str = "",
    pages_per_file: int = 1,
    parts: int = 2,
    password: Optional[str] = None,
    name_template: Optional[str] = None,
    progress: Progress_ = None,
) -> SplitResult:
    """按多种模式拆分 PDF，返回生成的文件列表。"""
    pr = _pg(progress)
    src = _open(src_path, password)
    try:
        n = src.page_count
        if n == 0:
            raise ValueError("文档没有页面")

        groups: List[List[int]]
        if mode == SPLIT_RANGES:
            text = (ranges or "").strip()
            if not text:
                raise ValueError("请填写要拆分的页码范围，例如 1-3;4-6")
            # 分号分隔不同输出文件；组内可用逗号表示不连续页
            tokens = text.split(";") if ";" in text else [text]
            tokens = [t.strip() for t in tokens if t.strip()]
            if not tokens:
                raise ValueError("请填写要拆分的页码范围，例如 1-3;4-6")
            groups = [pagerange.parse(t, n) for t in tokens]
        elif mode == SPLIT_FIXED:
            size = max(1, int(pages_per_file))
            groups = [list(range(i, min(i + size, n))) for i in range(0, n, size)]
        elif mode == SPLIT_SINGLE:
            groups = [[i] for i in range(n)]
        elif mode == SPLIT_PARTS:
            groups = [list(r) for r in pagerange.chunk_even(n, max(1, int(parts)))]
        elif mode == SPLIT_EVEN_ODD:
            odd = list(range(0, n, 2))
            even = list(range(1, n, 2))
            groups = [g for g in (odd, even) if g]
        else:
            raise ValueError(f"未知的拆分模式：{mode}")

        _ensure_dir(out_dir)
        base = os.path.splitext(os.path.basename(src_path))[0]
        if name_template is None:
            name_template = (
                "{name}_p{start}-{end}.pdf"
                if mode == SPLIT_RANGES
                else "{name}_part{index}.pdf"
            )
        written: List[str] = []
        total = len(groups)
        for idx, group in enumerate(groups):
            pr.step(idx, total, f"写出第 {idx + 1}/{total} 个文件")
            if not group:
                continue
            out = pymupdf.open()
            try:
                for p in group:
                    out.insert_pdf(src, from_page=p, to_page=p)
                fname = name_template.format(
                    name=base,
                    index=idx + 1,
                    start=group[0] + 1,
                    end=group[-1] + 1,
                )
                if not fname.lower().endswith(".pdf"):
                    fname += ".pdf"
                target = _unique(os.path.join(out_dir, fname))
                out.save(target, garbage=4, deflate=1, use_objstms=1)
                written.append(target)
            finally:
                out.close()

        pr.report(100, "完成")
        return SplitResult(files=written, skipped=sum(1 for g in groups if not g))
    finally:
        src.close()


def extract_pages(
    src_path: str,
    pages: Sequence[int],
    output: str,
    password: Optional[str] = None,
    progress: Progress_ = None,
) -> str:
    """把选中页面抽取成一个新的 PDF 文件。"""
    pr = _pg(progress)
    src = _open(src_path, password)
    try:
        out = pymupdf.open()
        try:
            for i, p in enumerate(pages):
                pr.step(i, len(pages), f"抽取第 {p + 1} 页")
                if 0 <= p < src.page_count:
                    out.insert_pdf(src, from_page=p, to_page=p)
            if out.page_count == 0:
                raise ValueError("选中的页面都不存在")
            _safe_dir(output)
            out.save(output, garbage=4, deflate=1, use_objstms=1)
        finally:
            out.close()
    finally:
        src.close()
    pr.report(100, "完成")
    return output


# ====================================================================== 页面整理


def reorder_pages(doc: pymupdf.Document, new_order: Sequence[int]) -> None:
    """按给定顺序重排页面；未出现在 new_order 中的页面会被删除。"""
    order = [int(p) for p in new_order if 0 <= int(p) < doc.page_count]
    if not order:
        raise ValueError("新的页面顺序为空")
    doc.select(order)


def delete_pages(doc: pymupdf.Document, indices: Sequence[int]) -> int:
    """删除指定页面，返回删除数量。"""
    keep = [i for i in range(doc.page_count) if i not in set(indices)]
    if not keep:
        raise ValueError("不能删除所有页面")
    removed = doc.page_count - len(keep)
    doc.select(keep)
    return removed


def insert_blank_pages(
    doc: pymupdf.Document,
    positions: Sequence[Tuple[int, float, float]],
) -> None:
    """在指定位置插入空白页，positions 为 (index, width, height)。"""
    for index, width, height in sorted(positions, key=lambda t: -t[0]):
        doc.insert_page(index, width=max(20.0, width), height=max(20.0, height))


def duplicate_pages(doc: pymupdf.Document, indices: Sequence[int]) -> None:
    """复制指定页面，副本紧跟在原页面之后。"""
    for i in sorted({int(x) for x in indices}, reverse=True):
        if 0 <= i < doc.page_count:
            doc.copy_page(i)
            doc.move_page(doc.page_count - 1, i + 1)


# ====================================================================== 旋转


def rotate_pages(
    doc: pymupdf.Document,
    indices: Sequence[int],
    angle: int,
) -> int:
    """把选中页面旋转 angle 度（累加到现有 /Rotate 上）。"""
    if angle % 90 != 0:
        raise ValueError("旋转角度必须是 90 的倍数")
    delta = int(angle) % 360
    if delta == 0:
        return 0
    count = 0
    for i in indices:
        if 0 <= i < doc.page_count:
            page = doc.load_page(i)
            page.set_rotation((page.rotation + delta) % 360)
            count += 1
    return count


def rotate_file(
    src_path: str,
    output: str,
    indices: Sequence[int],
    angle: int,
    password: Optional[str] = None,
    progress: Progress_ = None,
) -> str:
    pr = _pg(progress)
    doc = _open(src_path, password)
    try:
        rotate_pages(doc, indices, angle)
        _safe_dir(output)
        pr.report(90, "正在写出文件")
        doc.save(output, garbage=4, deflate=1, use_objstms=1)
    finally:
        doc.close()
    pr.report(100, "完成")
    return output


# ====================================================================== 裁剪
# 裁剪实现见 crop.py（背景色估计 + 投影扫描 + 置信度），此处保留旧名导出。

from .crop import (  # noqa: E402,F401
    CropMargins,
    CropReport,
    auto_crop_pages,
    detect_content_bbox,
    detect_white_margins,
    from_points,
    has_custom_crop,
    manual_crop_pages,
    mm_to_pt,
    page_size_label,
    pt_to_mm,
    reset_crop,
    to_points,
)

# ====================================================================== PDF -> 图片

IMAGE_FORMATS = ("png", "jpg", "webp")


def pdf_to_images(
    src_path: str,
    out_dir: str,
    fmt: str = "png",
    dpi: int = 150,
    quality: int = 90,
    pages: Optional[Sequence[int]] = None,
    prefix: Optional[str] = None,
    password: Optional[str] = None,
    grayscale: bool = False,
    transparent: bool = False,
    background: Optional[Tuple[int, int, int]] = None,
    max_width: Optional[int] = None,
    progress: Progress_ = None,
) -> List[str]:
    """把 PDF 页面导出为图片文件，返回文件路径列表。"""
    pr = _pg(progress)
    fmt = fmt.lower().lstrip(".")
    if fmt in ("jpeg", "jpe"):
        fmt = "jpg"
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"不支持的图片格式：{fmt}")

    doc = _open(src_path, password)
    try:
        targets = list(pages) if pages else list(range(doc.page_count))
        targets = [t for t in targets if 0 <= t < doc.page_count]
        if not targets:
            raise ValueError("没有可导出的页面")

        _ensure_dir(out_dir)
        base = prefix or os.path.splitext(os.path.basename(src_path))[0]
        zoom = max(0.1, dpi / 72.0)
        if max_width:
            widest = max(doc.load_page(t).rect.width for t in targets)
            if widest * zoom > max_width:
                zoom = max_width / widest
        colorspace = pymupdf.csGRAY if grayscale else pymupdf.csRGB
        written: List[str] = []

        for k, i in enumerate(targets):
            pr.step(k, len(targets), f"导出第 {i + 1} 页")
            page = doc.load_page(i)
            use_alpha = (transparent or background is not None) and fmt == "png"
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom),
                alpha=use_alpha,
                colorspace=colorspace,
            )
            fname = f"{base}_page{i + 1:0{max(3, len(str(len(targets))))}d}.{fmt}"
            target = os.path.join(out_dir, fname)

            if background is not None:
                _save_with_background(pix, target, fmt, quality, background)
            elif fmt == "jpg":
                pix.save(target, jpg_quality=max(1, min(100, quality)))
            else:
                pix.save(target)
            written.append(target)

        pr.report(100, "完成")
        return written
    finally:
        doc.close()


def _save_with_background(
    pix: pymupdf.Pixmap,
    target: str,
    fmt: str,
    quality: int,
    rgb: Tuple[int, int, int],
) -> None:
    """把带 alpha 的渲染结果合成到指定底色后保存。"""
    from PIL import Image

    if pix.alpha:
        img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    else:
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    canvas = Image.new("RGB", img.size, rgb)
    canvas.paste(img, (0, 0), img if img.mode == "RGBA" else None)
    if fmt == "jpg":
        canvas.save(target, quality=max(1, min(100, quality)))
    else:
        canvas.save(target)


# ====================================================================== 图片 -> PDF

PAGE_SIZE_FIT = "fit"          # 页面尺寸贴合图片
PAGE_SIZE_A4 = "a4"
PAGE_SIZE_A4_LANDSCAPE = "a4l"
PAGE_SIZE_LETTER = "letter"

_PAGE_DIMS: Dict[str, Tuple[float, float]] = {
    PAGE_SIZE_A4: (595.0, 842.0),
    PAGE_SIZE_A4_LANDSCAPE: (842.0, 595.0),
    PAGE_SIZE_LETTER: (612.0, 792.0),
}

_ONE_IMAGE_PER_PAGE = "one_per_page"
_FIT_ALL_ON_PAGE = "fit_all"


@dataclass
class ImageToPdfOptions:
    page_size: str = PAGE_SIZE_FIT
    margin: float = 0.0
    orientation: str = "auto"          # auto / portrait / landscape
    layout: str = _ONE_IMAGE_PER_PAGE
    columns: int = 1                   # layout=fit_all 时每页几列
    background: Tuple[int, int, int] = (255, 255, 255)
    dpi_for_fit: float = 96.0          # 页面贴合模式下图片像素->点的换算基准


def images_to_pdf(
    image_paths: Sequence[str],
    output: str,
    options: Optional[ImageToPdfOptions] = None,
    rotations: Optional[Sequence[int]] = None,
    progress: Progress_ = None,
) -> str:
    """把一组图片合成一个 PDF。rotations 为每张图片的旋转角度。"""
    pr = _pg(progress)
    opts = options or ImageToPdfOptions()
    paths = [p for p in image_paths if p]
    if not paths:
        raise ValueError("没有选择任何图片")
    rots = list(rotations) if rotations else [0] * len(paths)
    while len(rots) < len(paths):
        rots.append(0)

    doc = pymupdf.open()
    try:
        if opts.layout == _FIT_ALL_ON_PAGE:
            _images_to_pdf_grid(doc, paths, rots, opts, pr)
        else:
            total = len(paths)
            for k, path in enumerate(paths):
                pr.step(k, total, f"添加 {os.path.basename(path)}")
                rect, _ = _page_rect_for_image(path, opts, rots[k])
                page = doc.new_page(width=rect.width, height=rect.height)
                if opts.background != (255, 255, 255):
                    page.draw_rect(
                        page.rect,
                        color=None,
                        fill=tuple(c / 255 for c in opts.background),
                    )
                inner = _inset(page.rect, opts.margin)
                _place_image(page, path, inner, keep_aspect=True, rotate=rots[k])

        if doc.page_count == 0:
            raise ValueError("没有生成任何页面")
        _safe_dir(output)
        pr.report(95, "正在写出 PDF")
        doc.save(output, garbage=4, deflate=1)
    finally:
        doc.close()

    pr.report(100, "完成")
    return output


def _images_to_pdf_grid(
    doc: pymupdf.Document,
    paths: Sequence[str],
    rots: Sequence[int],
    opts: ImageToPdfOptions,
    pr: Progress,
) -> None:
    cols = max(1, int(opts.columns))
    dims = _PAGE_DIMS.get(opts.page_size, _PAGE_DIMS[PAGE_SIZE_A4])
    total = len(paths)
    for k in range(0, total, cols):
        pr.step(k, total, "排版图片")
        page = doc.new_page(width=dims[0], height=dims[1])
        area = _inset(page.rect, opts.margin)
        cell_w = area.width / cols
        rows = 1
        cell_h = area.height / rows
        batch = list(enumerate(paths[k : k + cols], start=k))
        for c, (idx, path) in enumerate(batch):
            cell = pymupdf.Rect(
                area.x0 + c * cell_w, area.y0,
                area.x0 + (c + 1) * cell_w, area.y0 + cell_h,
            )
            _place_image(page, path, _inset(cell, 4), keep_aspect=True, rotate=rots[idx])


def _page_rect_for_image(
    path: str, opts: ImageToPdfOptions, rotate: int = 0
) -> Tuple[pymupdf.Rect, int]:
    from PIL import Image

    with Image.open(path) as im:
        px_w, px_h = im.size
    if rotate in (90, 270):
        px_w, px_h = px_h, px_w

    if opts.page_size != PAGE_SIZE_FIT:
        w, h = _PAGE_DIMS.get(opts.page_size, _PAGE_DIMS[PAGE_SIZE_A4])
        if opts.orientation == "landscape" and w < h:
            w, h = h, w
        elif opts.orientation == "portrait" and w > h:
            w, h = h, w
        return pymupdf.Rect(0, 0, w, h), 0

    scale = 72.0 / max(1.0, opts.dpi_for_fit)
    w = max(20.0, px_w * scale)
    h = max(20.0, px_h * scale)
    if opts.orientation == "landscape" and w < h:
        w, h = h, w
    elif opts.orientation == "portrait" and w > h:
        w, h = h, w
    return pymupdf.Rect(0, 0, w + opts.margin * 2, h + opts.margin * 2), 0


def _place_image(
    page: pymupdf.Page,
    path: str,
    rect: pymupdf.Rect,
    keep_aspect: bool = True,
    rotate: int = 0,
) -> None:
    if rect.width <= 0 or rect.height <= 0:
        return
    rotate = int(rotate) % 360
    if not keep_aspect:
        page.insert_image(rect, filename=path, keep_proportion=False, rotate=rotate)
        return
    from PIL import Image

    with Image.open(path) as im:
        pw, ph = im.size
    if rotate in (90, 270):
        pw, ph = ph, pw
    if pw <= 0 or ph <= 0:
        page.insert_image(rect, filename=path, rotate=rotate)
        return
    scale = min(rect.width / pw, rect.height / ph)
    w, h = pw * scale, ph * scale
    x0 = rect.x0 + (rect.width - w) / 2
    y0 = rect.y0 + (rect.height - h) / 2
    page.insert_image(
        pymupdf.Rect(x0, y0, x0 + w, y0 + h), filename=path, rotate=rotate
    )


def _inset(rect: pymupdf.Rect, margin: float) -> pymupdf.Rect:
    m = max(0.0, float(margin))
    r = pymupdf.Rect(rect.x0 + m, rect.y0 + m, rect.x1 - m, rect.y1 - m)
    return r if r.width > 0 and r.height > 0 else rect


# ====================================================================== 工具函数


def _open(path: str, password: Optional[str] = None) -> pymupdf.Document:
    doc = pymupdf.open(path)
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            doc.close()
            raise ValueError(f"《{os.path.basename(path)}》需要密码或密码不正确")
    return doc


def _safe_dir(path: str) -> None:
    """确保某个文件路径的所在目录存在。"""
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)


def _ensure_dir(dirpath: str) -> str:
    """确保目录本身存在（_safe_dir 只建父目录，不能用于目录参数）。"""
    d = os.path.abspath(dirpath)
    os.makedirs(d, exist_ok=True)
    return d


def _unique(path: str) -> str:
    """目标已存在时自动追加 (1)、(2) …"""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{root}({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


_INVALID_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "output") -> str:
    cleaned = _INVALID_FS.sub("_", (name or "").strip()).strip(". ")
    return cleaned or fallback
