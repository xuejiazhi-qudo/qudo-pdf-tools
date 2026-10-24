"""裁剪与去白边：背景色估计 + 投影扫描 + 置信度，与网页版算法对齐。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np
import pymupdf

from ..worker import Progress

Progress_ = Optional[Progress]

SENSITIVITY_LOW = "low"          # 阈值 40：只有明显深色才算内容
SENSITIVITY_STANDARD = "standard"  # 阈值 25
SENSITIVITY_HIGH = "high"        # 阈值 15：浅色水印/淡灰也算内容

SENSITIVITY_THRESHOLD = {
    SENSITIVITY_LOW: 40,
    SENSITIVITY_STANDARD: 25,
    SENSITIVITY_HIGH: 15,
}

DETECT_RENDER_SCALE = 0.5
CONTENT_RATIO_MIN = 0.01     # 内容像素占比低于 1% 视为空白页
PROJECTION_THRESHOLD = 0.02  # 行/列投影阈值 2%
DEFAULT_SAFETY_MM = 5.0

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"


@dataclass
class CropDetection:
    rect: Optional[pymupdf.Rect]
    confidence: str = CONFIDENCE_LOW
    content_ratio: float = 0.0
    background: Tuple[float, float, float] = (255.0, 255.0, 255.0)
    blank: bool = False

    @property
    def found(self) -> bool:
        return self.rect is not None


def detect_white_margins(
    page: pymupdf.Page,
    sensitivity: str = SENSITIVITY_STANDARD,
    safety_mm: float = DEFAULT_SAFETY_MM,
    scale: float = DETECT_RENDER_SCALE,
) -> CropDetection:
    """检测页面四周白边，返回显示坐标系下的内容包围盒。"""
    threshold = SENSITIVITY_THRESHOLD.get(sensitivity, SENSITIVITY_THRESHOLD[SENSITIVITY_STANDARD])

    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )[:, :, :3].astype(np.float32)

    h, w, _ = arr.shape
    if h < 4 or w < 4:
        return CropDetection(rect=None, blank=True)

    # 背景色：四角采样取均值
    side = max(2, min(10, min(w, h) // 4))
    corners = [
        arr[:side, :side],
        arr[:side, -side:],
        arr[-side:, :side],
        arr[-side:, -side:],
    ]
    bg = np.mean([c.reshape(-1, 3).mean(axis=0) for c in corners], axis=0)

    dist = np.sqrt(((arr - bg) ** 2).sum(axis=2))
    content = dist > threshold
    ratio = float(content.mean())
    if ratio < CONTENT_RATIO_MIN:
        return CropDetection(rect=None, blank=True, background=tuple(float(v) for v in bg))

    rows = content.mean(axis=1)
    cols = content.mean(axis=0)

    def _first_edge(profile: np.ndarray) -> Tuple[int, int]:
        idx = np.where(profile > PROJECTION_THRESHOLD)[0]
        if idx.size == 0:
            return 0, len(profile) - 1
        return int(idx[0]), int(idx[-1])

    y0, y1 = _first_edge(rows)
    x0, x1 = _first_edge(cols)

    # 像素 -> 页面坐标
    inv = 1.0 / scale
    rect = pymupdf.Rect(x0 * inv, y0 * inv, (x1 + 1) * inv, (y1 + 1) * inv)
    rect = rect & page.rect

    # 置信度：背景方差 + 边缘噪声
    bg_var = float(np.mean([c.reshape(-1, 3).var(axis=0).mean() for c in corners]))
    edge = np.concatenate(
        [
            content[: max(1, h // 20), :].ravel(),
            content[-max(1, h // 20):, :].ravel(),
            content[:, : max(1, w // 20)].ravel(),
            content[:, -max(1, w // 20):].ravel(),
        ]
    )
    edge_noise = float(edge.mean()) if edge.size else 0.0

    if bg_var < 15 and edge_noise < 0.1:
        confidence = CONFIDENCE_HIGH
    elif bg_var < 40 and edge_noise < 0.25:
        confidence = CONFIDENCE_MEDIUM
    else:
        confidence = CONFIDENCE_LOW

    # 安全边距（mm -> pt，向外扩）
    if safety_mm:
        pad = safety_mm * 72.0 / 25.4
        rect = pymupdf.Rect(
            rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad
        ) & page.rect

    return CropDetection(
        rect=rect,
        confidence=confidence,
        content_ratio=ratio,
        background=tuple(float(v) for v in bg),
    )


def detect_content_bbox(
    page: pymupdf.Page,
    threshold: int = 245,
    zoom: float = 1.0,
) -> Optional[pymupdf.Rect]:
    """旧接口兼容：简单灰度阈值检测。新代码请用 detect_white_margins。"""
    pix = page.get_pixmap(
        matrix=pymupdf.Matrix(zoom, zoom), alpha=False, colorspace=pymupdf.csGRAY
    )
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    mask = arr < threshold
    if not mask.any():
        return None
    rows = np.where(mask.any(axis=1))[0]
    cols = np.where(mask.any(axis=0))[0]
    m = ~pymupdf.Matrix(zoom, zoom)
    p0 = pymupdf.Point(float(cols[0]), float(rows[0])) * m
    p1 = pymupdf.Point(float(cols[-1]) + 1, float(rows[-1]) + 1) * m
    return pymupdf.Rect(p0.x, p0.y, p1.x, p1.y) & page.rect


# ====================================================================== 应用裁剪


def _apply_cropbox(page: pymupdf.Page, rect: pymupdf.Rect) -> bool:
    """把显示坐标系的矩形写入 CropBox（处理页面 /Rotate）。"""
    mb = page.mediabox
    display = rect & page.rect
    if display.is_empty or display.width < 8 or display.height < 8:
        return False

    if page.rotation % 360:
        target = display * page.derotation_matrix
    else:
        dx, dy = mb.x0, mb.y0
        target = display + (dx, dy, dx, dy)

    target = target.normalize() & mb
    if target.is_empty or target.width < 8 or target.height < 8:
        return False

    page.set_cropbox(target)
    return True


@dataclass
class CropMargins:
    """四边裁切量（PDF 点），以显示方向为准。"""

    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0
    left: float = 0.0


@dataclass
class CropReport:
    processed: list
    skipped: list
    all_same_size: bool = False


def auto_crop_pages(
    doc: pymupdf.Document,
    indices: Sequence[int],
    sensitivity: str = SENSITIVITY_STANDARD,
    safety_mm: float = DEFAULT_SAFETY_MM,
    unify: bool = False,
    progress: Progress_ = None,
) -> CropReport:
    """自动去白边。unify=True 时所有页面裁成同一尺寸。"""
    pr = progress or Progress()
    targets = [i for i in indices if 0 <= i < doc.page_count]
    if not targets:
        return CropReport(processed=[], skipped=[])

    detections = []
    for k, i in enumerate(targets):
        pr.step(k, len(targets), f"检测第 {i + 1} 页白边")
        det = detect_white_margins(doc.load_page(i), sensitivity, safety_mm)
        detections.append((i, det))

    processed, skipped = [], []
    if unify:
        boxes = [d.rect for _, d in detections if d.found]
        if not boxes:
            return CropReport(processed=[], skipped=list(targets))
        tw = max(b.width for b in boxes)
        th = max(b.height for b in boxes)
        for i, _ in detections:
            page = doc.load_page(i)
            pr_rect = page.rect
            w = min(tw, pr_rect.width)
            h = min(th, pr_rect.height)
            x0 = pr_rect.x0 + max(0.0, (pr_rect.width - w) / 2)
            y0 = pr_rect.y0 + max(0.0, (pr_rect.height - h) / 2)
            if _apply_cropbox(page, pymupdf.Rect(x0, y0, x0 + w, y0 + h)):
                processed.append(i)
            else:
                skipped.append(i)
    else:
        for i, det in detections:
            if not det.found:
                skipped.append(i)
                continue
            if _apply_cropbox(doc.load_page(i), det.rect):
                processed.append(i)
            else:
                skipped.append(i)

    sizes = {
        tuple(round(v, 1) for v in (doc.load_page(i).rect.width, doc.load_page(i).rect.height))
        for i in processed
    }
    pr.report(100, "完成")
    return CropReport(
        processed=processed,
        skipped=skipped,
        all_same_size=len(sizes) <= 1,
    )


def manual_crop_pages(
    doc: pymupdf.Document,
    indices: Sequence[int],
    margins: CropMargins,
) -> CropReport:
    """按固定四边裁切量裁剪。top/right/bottom/left 以显示方向为准。"""
    processed, skipped = [], []
    for i in indices:
        if not 0 <= i < doc.page_count:
            skipped.append(i)
            continue
        page = doc.load_page(i)
        base = page.rect
        rect = pymupdf.Rect(
            base.x0 + max(0.0, margins.left),
            base.y0 + max(0.0, margins.top),
            base.x1 - max(0.0, margins.right),
            base.y1 - max(0.0, margins.bottom),
        )
        if rect.width < 8 or rect.height < 8:
            raise ValueError("裁剪量太大，页面剩余尺寸无效")
        if _apply_cropbox(page, rect):
            processed.append(i)
        else:
            skipped.append(i)
    return CropReport(processed=processed, skipped=skipped)


def reset_crop(doc: pymupdf.Document, indices: Sequence[int]) -> int:
    """把 CropBox 恢复成 MediaBox。"""
    count = 0
    for i in indices:
        if 0 <= i < doc.page_count:
            page = doc.load_page(i)
            page.set_cropbox(page.mediabox)
            count += 1
    return count


def has_custom_crop(page: pymupdf.Page) -> bool:
    cb, mb = page.cropbox, page.mediabox
    return abs(cb.width - mb.width) > 0.5 or abs(cb.height - mb.height) > 0.5


def page_size_label(width: float, height: float) -> str:
    """识别常见纸张尺寸名。"""
    known = [
        ("A3", 841.89, 1190.55),
        ("A4", 595.28, 841.89),
        ("A5", 419.53, 595.28),
        ("B5", 498.90, 708.66),
        ("Letter", 612.0, 792.0),
        ("Legal", 612.0, 1008.0),
        ("Tabloid", 792.0, 1224.0),
    ]
    for name, w, h in known:
        for ww, hh in ((w, h), (h, w)):
            if abs(width - ww) < 1.5 and abs(height - hh) < 1.5:
                return name
    return f"{width:.0f}×{height:.0f}pt"


def mm_to_pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def pt_to_mm(pt: float) -> float:
    return pt * 25.4 / 72.0


UNIT_FACTORS = {
    "pt": 1.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
    "in": 72.0,
}


def to_points(value: float, unit: str) -> float:
    return value * UNIT_FACTORS.get(unit, 1.0)


def from_points(value: float, unit: str) -> float:
    f = UNIT_FACTORS.get(unit, 1.0)
    return value / f if f else value
