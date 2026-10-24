"""压缩：四档压缩策略，从无损结构优化到整页栅格化。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import pymupdf

from ..worker import Progress
from .pages import _open, _safe_dir

Progress_ = Optional[Progress]

LEVEL_LOSSLESS = "lossless"
LEVEL_BALANCED = "balanced"
LEVEL_STRONG = "strong"
LEVEL_EXTREME = "extreme"

LEVEL_LABELS = {
    LEVEL_LOSSLESS: "无损优化",
    LEVEL_BALANCED: "均衡（推荐）",
    LEVEL_STRONG: "强力",
    LEVEL_EXTREME: "极限（转为图片）",
}

LEVEL_DESC = {
    LEVEL_LOSSLESS: "只重组文件结构、压缩数据流，不改变任何可见内容和文字可选中性。",
    LEVEL_BALANCED: "在保持清晰度的前提下降低内嵌图片分辨率与质量，文字仍可选中。",
    LEVEL_STRONG: "更激进地重采样图片并精简字体，适合扫描类和图片类 PDF。",
    LEVEL_EXTREME: "把每页渲染成图片重建 PDF，体积最小，但文字不再可选中/搜索。",
}


@dataclass
class CompressOptions:
    level: str = LEVEL_BALANCED
    grayscale: bool = False
    remove_metadata: bool = False
    remove_embedded: bool = False
    linearize: bool = False
    dpi_target: Optional[int] = None     # 覆盖该档默认值
    quality: Optional[int] = None        # 覆盖该档默认值
    extreme_dpi: int = 120               # 极限档的渲染分辨率
    extreme_quality: int = 70

    def validate(self) -> None:
        if self.level not in LEVEL_LABELS:
            raise ValueError(f"未知的压缩档位：{self.level}")


@dataclass
class CompressResult:
    output: str
    before: int
    after: int

    @property
    def saved(self) -> int:
        return max(0, self.before - self.after)

    @property
    def ratio(self) -> float:
        return (self.after / self.before) if self.before else 1.0


def compress_file(
    src_path: str,
    output: str,
    options: Optional[CompressOptions] = None,
    password: Optional[str] = None,
    progress: Progress_ = None,
) -> CompressResult:
    pr = progress or Progress()
    opts = options or CompressOptions()
    opts.validate()

    before = os.path.getsize(src_path)
    _safe_dir(output)

    if opts.level == LEVEL_EXTREME:
        _compress_extreme(src_path, output, opts, password, pr)
    else:
        _compress_normal(src_path, output, opts, password, pr)

    after = os.path.getsize(output)
    pr.report(100, "完成")
    return CompressResult(output=output, before=before, after=after)


def _compress_normal(
    src_path: str,
    output: str,
    opts: CompressOptions,
    password: Optional[str],
    pr: Progress,
) -> None:
    doc = _open(src_path, password)
    try:
        pr.report(10, "分析文档")

        if opts.grayscale:
            pr.report(20, "转换为灰度")
            try:
                doc.recolor()
            except Exception:
                pass

        if opts.level in (LEVEL_BALANCED, LEVEL_STRONG):
            dpi_target = opts.dpi_target or (150 if opts.level == LEVEL_BALANCED else 110)
            quality = opts.quality or (82 if opts.level == LEVEL_BALANCED else 62)
            pr.report(45, f"重采样图片（目标 {dpi_target} DPI）")
            try:
                doc.rewrite_images(
                    dpi_threshold=dpi_target + 40,
                    dpi_target=dpi_target,
                    quality=quality,
                    lossy=True,
                    lossless=True,
                    bitonal=True,
                    color=True,
                    gray=True,
                    set_to_gray=opts.grayscale,
                )
            except Exception:
                pass

        if opts.level == LEVEL_STRONG:
            pr.report(65, "精简字体")
            try:
                doc.subset_fonts(fallback=True)
            except Exception:
                pass

        if opts.remove_metadata:
            pr.report(75, "清除元数据")
            doc.set_metadata({})
            try:
                doc.del_xml_metadata()
            except Exception:
                pass

        if opts.remove_embedded:
            pr.report(80, "移除附件")
            try:
                for name in list(doc.embfile_names()):
                    doc.embfile_del(name)
            except Exception:
                pass

        pr.report(90, "重组文件结构")
        doc.save(
            output,
            garbage=4,
            clean=1,
            deflate=1,
            deflate_images=1,
            deflate_fonts=1,
            use_objstms=1,
            linear=1 if opts.linearize else 0,
        )
    finally:
        doc.close()


def _compress_extreme(
    src_path: str,
    output: str,
    opts: CompressOptions,
    password: Optional[str],
    pr: Progress,
) -> None:
    """整页栅格化：体积最小，代价是文字不可选中。"""
    src = _open(src_path, password)
    out = pymupdf.open()
    try:
        zoom = max(0.5, opts.extreme_dpi / 72.0)
        colorspace = pymupdf.csGRAY if opts.grayscale else pymupdf.csRGB
        total = src.page_count
        for i in range(total):
            pr.step(i, total, f"栅格化第 {i + 1}/{total} 页")
            page = src.load_page(i)
            pix = page.get_pixmap(
                matrix=pymupdf.Matrix(zoom, zoom),
                alpha=False,
                colorspace=colorspace,
            )
            new = out.new_page(width=page.rect.width, height=page.rect.height)
            new.insert_image(
                new.rect,
                stream=pix.tobytes("jpg", jpg_quality=opts.extreme_quality),
                keep_proportion=False,
            )

        pr.report(92, "写出文件")
        out.save(
            output,
            garbage=4,
            deflate=1,
            use_objstms=1,
            linear=1 if opts.linearize else 0,
        )
    finally:
        src.close()
        out.close()


def estimate_savings(src_path: str, password: Optional[str] = None) -> dict:
    """快速统计可用于压缩判断的信息：图片数量、平均 DPI 等。"""
    doc = _open(src_path, password)
    try:
        images = 0
        big = 0
        for page in doc.pages():
            for item in page.get_images(full=True):
                images += 1
                if max(item[2], item[3]) > 1600:
                    big += 1
        return {
            "page_count": doc.page_count,
            "image_count": images,
            "large_image_count": big,
            "size": os.path.getsize(src_path),
        }
    finally:
        doc.close()
