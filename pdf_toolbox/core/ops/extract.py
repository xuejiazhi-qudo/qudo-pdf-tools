"""内容提取：文字（TXT/Markdown/JSON）、内嵌图片、元数据读取与清除。"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import pymupdf

from ..worker import Progress
from .pages import _ensure_dir, _open, _safe_dir, _unique

Progress_ = Optional[Progress]

FMT_TEXT = "txt"
FMT_MARKDOWN = "markdown"
FMT_JSON = "json"
FMT_HTML = "html"


# ====================================================================== 文字


@dataclass
class PageText:
    index: int
    text: str
    char_count: int = 0
    word_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.text)
        self.word_count = len(re.findall(r"\S+", self.text))


def extract_text_pages(
    src_path: str,
    pages: Optional[Sequence[int]] = None,
    password: Optional[str] = None,
    sort: bool = True,
    progress: Progress_ = None,
) -> List[PageText]:
    """逐页提取纯文字，供界面分页展示与搜索。"""
    pr = progress or Progress()
    doc = _open(src_path, password)
    try:
        targets = list(pages) if pages else list(range(doc.page_count))
        out: List[PageText] = []
        for k, i in enumerate(targets):
            pr.step(k, len(targets), f"提取第 {i + 1} 页")
            if not 0 <= i < doc.page_count:
                continue
            text = doc.get_page_text(i, option="text", sort=sort)
            out.append(PageText(index=i, text=text))
        pr.report(100, "完成")
        return out
    finally:
        doc.close()


def extract_text(
    src_path: str,
    output: Optional[str] = None,
    fmt: str = FMT_TEXT,
    pages: Optional[Sequence[int]] = None,
    password: Optional[str] = None,
    include_page_marker: bool = True,
    progress: Progress_ = None,
) -> str:
    """提取文字并返回内容字符串；output 非空时同时写文件。"""
    pr = progress or Progress()
    fmt = fmt.lower()
    doc = _open(src_path, password)
    try:
        targets = list(pages) if pages else list(range(doc.page_count))
        targets = [t for t in targets if 0 <= t < doc.page_count]

        if fmt == FMT_MARKDOWN:
            content = _to_markdown(doc, targets, pr)
        elif fmt == FMT_JSON:
            content = _to_json(doc, targets, pr)
        elif fmt == FMT_HTML:
            content = _to_html(doc, targets, pr)
        elif fmt == FMT_TEXT:
            content = _to_plain(doc, targets, include_page_marker, pr)
        else:
            raise ValueError(f"不支持的导出格式：{fmt}")

        if output:
            _safe_dir(output)
            with open(output, "w", encoding="utf-8") as fh:
                fh.write(content)
        pr.report(100, "完成")
        return content
    finally:
        doc.close()


def _to_plain(
    doc: pymupdf.Document,
    targets: Sequence[int],
    marker: bool,
    pr: Progress,
) -> str:
    chunks: List[str] = []
    for k, i in enumerate(targets):
        pr.step(k, len(targets), f"提取第 {i + 1} 页")
        text = doc.get_page_text(i, option="text", sort=True).rstrip()
        if marker:
            chunks.append(f"===== 第 {i + 1} 页 =====\n{text}")
        else:
            chunks.append(text)
    return "\n\n".join(chunks)


def _to_markdown(doc: pymupdf.Document, targets: Sequence[int], pr: Progress) -> str:
    pr.report(20, "转换为 Markdown")
    try:
        import pymupdf4llm

        md = pymupdf4llm.to_markdown(doc, pages=list(targets))
        return md
    except Exception:
        # 回退：逐页纯文字加标题分隔
        chunks = []
        for k, i in enumerate(targets):
            pr.step(k, len(targets), f"第 {i + 1} 页")
            chunks.append(f"## 第 {i + 1} 页\n\n{doc.get_page_text(i, option='text', sort=True).strip()}")
        return "\n\n".join(chunks)


def _to_json(doc: pymupdf.Document, targets: Sequence[int], pr: Progress) -> str:
    pages: List[Dict[str, Any]] = []
    for k, i in enumerate(targets):
        pr.step(k, len(targets), f"第 {i + 1} 页")
        raw = doc.get_page_text(i, option="json")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = {"text": doc.get_page_text(i, option="text")}
        page = data.get("blocks") and data or {"blocks": data}
        rect = doc.load_page(i).rect
        pages.append(
            {
                "page": i + 1,
                "width": rect.width,
                "height": rect.height,
                "rotation": doc.load_page(i).rotation,
                "blocks": page.get("blocks", []),
            }
        )
    return json.dumps(
        {
            "source": os.path.basename(doc.name or ""),
            "page_count": doc.page_count,
            "pages": pages,
        },
        ensure_ascii=False,
        indent=2,
    )


def _to_html(doc: pymupdf.Document, targets: Sequence[int], pr: Progress) -> str:
    parts = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8"><title>提取文字</title>',
        "<style>body{font-family:sans-serif;max-width:800px;margin:2em auto;}"
        "h2{border-bottom:1px solid #ccc;padding-bottom:.3em}</style></head><body>",
    ]
    for k, i in enumerate(targets):
        pr.step(k, len(targets), f"第 {i + 1} 页")
        parts.append(f"<h2>第 {i + 1} 页</h2>")
        parts.append(doc.get_page_text(i, option="xhtml"))
    parts.append("</body></html>")
    return "\n".join(parts)


# ====================================================================== 图片


@dataclass
class ExtractedImage:
    xref: int
    page: int
    index_in_page: int
    width: int
    height: int
    ext: str
    size_bytes: int
    colorspace: str
    has_alpha: bool
    filename: str = ""


def list_images(
    src_path: str,
    password: Optional[str] = None,
    min_side: int = 1,
) -> List[ExtractedImage]:
    """列出文档中所有内嵌图片（按 xref 去重，记录首次出现的页面）。"""
    doc = _open(src_path, password)
    try:
        seen: Dict[int, ExtractedImage] = {}
        for pno in range(doc.page_count):
            page = doc.load_page(pno)
            for idx, item in enumerate(page.get_images(full=True)):
                xref = item[0]
                if xref <= 0 or xref in seen:
                    continue
                smask = item[1]
                w, h = item[2], item[3]
                if max(w, h) < min_side:
                    continue
                cs = item[5] or ""
                seen[xref] = ExtractedImage(
                    xref=xref,
                    page=pno,
                    index_in_page=idx,
                    width=w,
                    height=h,
                    ext="",
                    size_bytes=0,
                    colorspace=str(cs),
                    has_alpha=bool(smask),
                )
        return sorted(seen.values(), key=lambda e: (e.page, e.index_in_page))
    finally:
        doc.close()


def extract_images(
    src_path: str,
    out_dir: str,
    xrefs: Optional[Sequence[int]] = None,
    password: Optional[str] = None,
    min_side: int = 1,
    name_prefix: Optional[str] = None,
    progress: Progress_ = None,
) -> List[ExtractedImage]:
    """把选中的内嵌图片导出为独立文件，返回带 filename 的列表。"""
    pr = progress or Progress()
    doc = _open(src_path, password)
    try:
        infos = list_images(src_path, password, min_side)
        if xrefs is not None:
            wanted = set(xrefs)
            infos = [i for i in infos if i.xref in wanted]
        if not infos:
            raise ValueError("文档中没有可提取的图片")

        _ensure_dir(out_dir)
        base = name_prefix or os.path.splitext(os.path.basename(src_path))[0]
        results: List[ExtractedImage] = []

        for k, info in enumerate(infos):
            pr.step(k, len(infos), f"导出图片 {k + 1}/{len(infos)}")
            data = doc.extract_image(info.xref)
            raw = data.get("image") or b""
            ext = (data.get("ext") or "png").lower()

            smask = data.get("smask") or 0
            if smask:
                # 带透明通道：合成 RGBA 后统一存 PNG
                try:
                    pix = pymupdf.Pixmap(doc, info.xref)
                    mask = pymupdf.Pixmap(doc, smask)
                    if pix.colorspace and pix.colorspace.n != 3:
                        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                    pix = pymupdf.Pixmap(pix, mask)
                    raw = pix.tobytes("png")
                    ext = "png"
                except Exception:
                    pass

            fname = f"{base}_p{info.page + 1}_{info.index_in_page + 1:02d}.{ext}"
            target = _unique(os.path.join(out_dir, fname))
            with open(target, "wb") as fh:
                fh.write(raw)

            info.ext = ext
            info.size_bytes = len(raw)
            info.filename = target
            results.append(info)

        pr.report(100, "完成")
        return results
    finally:
        doc.close()


def extract_images_zip(
    src_path: str,
    zip_path: str,
    xrefs: Optional[Sequence[int]] = None,
    password: Optional[str] = None,
    min_side: int = 1,
    progress: Progress_ = None,
) -> List[ExtractedImage]:
    """提取图片并打包成 ZIP。"""
    pr = progress or Progress()
    import tempfile

    with tempfile.TemporaryDirectory(prefix="pdfimg_") as tmp:
        results = extract_images(src_path, tmp, xrefs, password, min_side, None, pr)
        pr.report(95, "打包 ZIP")
        _safe_dir(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for info in results:
                zf.write(info.filename, os.path.basename(info.filename))
    pr.report(100, "完成")
    return results


# ====================================================================== 元数据


@dataclass
class MetadataInfo:
    standard: Dict[str, str] = field(default_factory=dict)
    xmp: str = ""
    fonts: List[str] = field(default_factory=list)
    image_count: int = 0
    embedded_files: List[str] = field(default_factory=list)
    javascript: bool = False
    form_fields: int = 0
    annotations: int = 0
    links: int = 0
    outline_entries: int = 0
    toc: List[List[Any]] = field(default_factory=list)

    def non_empty_standard(self) -> Dict[str, str]:
        return {k: v for k, v in self.standard.items() if v}


def read_metadata(src_path: str, password: Optional[str] = None) -> MetadataInfo:
    doc = _open(src_path, password)
    try:
        info = MetadataInfo()
        info.standard = {
            k: (v or "")
            for k, v in (doc.metadata or {}).items()
            if k not in ("format", "encryption")
        }
        info.standard["format"] = (doc.metadata or {}).get("format", "")
        try:
            info.xmp = doc.xref_xml_metadata() or ""
        except Exception:
            info.xmp = ""

        fonts: set = set()
        images = 0
        annots = 0
        links = 0
        fields = 0
        for page in doc.pages():
            for f in page.get_fonts():
                fonts.add(f[3] or f[4] or "?")
            images += len(page.get_images(full=True))
            for _ in page.annots():
                annots += 1
            for _ in page.links():
                links += 1
            for _ in page.widgets():
                fields += 1

        info.fonts = sorted(fonts)
        info.image_count = images
        info.annotations = annots
        info.links = links
        info.form_fields = fields

        try:
            info.embedded_files = list(doc.embfile_names())
        except Exception:
            info.embedded_files = []

        info.javascript = _has_javascript(doc)
        info.outline_entries = len(doc.get_toc(simple=True))
        info.toc = doc.get_toc(simple=True)
        return info
    finally:
        doc.close()


def _has_javascript(doc: pymupdf.Document) -> bool:
    try:
        for xref in range(1, doc.xref_length()):
            obj = doc.xref_object(xref, compressed=True) or ""
            if "/JavaScript" in obj or "/JS" in obj:
                return True
    except Exception:
        return False
    return False


@dataclass
class CleanOptions:
    metadata: bool = True
    xmp: bool = True
    hidden_text: bool = True
    javascript: bool = True
    embedded_files: bool = True
    attachments: bool = True
    links: bool = False
    thumbnails: bool = True
    annotations: bool = False
    reset_fields: bool = False
    redactions: bool = False
    clean_pages: bool = False


def _clear_info(doc: pymupdf.Document) -> bool:
    """把 /Info 对象重写为空字典。

    PyMuPDF 2.0 的 set_metadata({}) / scrub(metadata=True) 在交叉引用流
    （pdf-lib 等工具产出的文件）上是静默空操作，必须直接改对象。
    """
    try:
        kind, value = doc.xref_get_key(-1, "Info")
        if kind != "xref":
            return False
        info_xref = int(value.split()[0])
        if info_xref <= 0:
            return False
        doc.update_object(info_xref, "<<>>")
        doc.init_doc()
        return True
    except Exception:
        return False


def clean_metadata(
    doc: pymupdf.Document,
    options: Optional[CleanOptions] = None,
) -> Dict[str, Any]:
    """清除隐藏信息。返回实际执行了哪些清理项。"""
    opts = options or CleanOptions()
    removed: Dict[str, Any] = {}

    if opts.metadata:
        removed["metadata"] = {k: v for k, v in (doc.metadata or {}).items() if v}
        removed["metadata_cleared"] = _clear_info(doc)

    doc.scrub(
        attached_files=opts.attachments,
        clean_pages=opts.clean_pages,
        embedded_files=opts.embedded_files,
        hidden_text=opts.hidden_text,
        javascript=opts.javascript,
        metadata=False,          # 由 _clear_info 处理
        redactions=opts.redactions,
        remove_links=opts.links,
        reset_fields=opts.reset_fields,
        reset_responses=True,
        thumbnails=opts.thumbnails,
        xml_metadata=opts.xmp,
    )
    removed["xmp"] = bool(opts.xmp)

    if opts.annotations:
        for page in doc.pages():
            for annot in list(page.annots()):
                page.delete_annot(annot)
        removed["annotations"] = True

    return removed


def set_metadata_values(doc: pymupdf.Document, values: Dict[str, str]) -> None:
    """写入自定义元数据（标题/作者等）。空值字段会被清空。"""
    current = dict(doc.metadata or {})
    merged: Dict[str, str] = {}
    for key in ("title", "author", "subject", "keywords", "creator", "producer",
                "creationDate", "modDate", "trapped"):
        if key in values:
            merged[key] = values[key] or ""
        else:
            merged[key] = current.get(key, "") or ""
    doc.set_metadata(merged)
