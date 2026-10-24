"""涂销（Redaction）：永久删除 PDF 中的敏感文字与图像区域。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import pymupdf

from ..worker import Progress

Progress_ = Optional[Progress]

# 图像处理方式
IMG_NONE = 0        # 不处理图片
IMG_REMOVE = 1      # 与涂销区相交的图片整张删除
IMG_PIXELS = 2      # 只把相交像素涂黑（推荐）

# 矢量图形处理方式
GFX_NONE = 0
GFX_IF_INTERSECT = 1
GFX_IF_COVERED = 2

# 文字处理方式
TEXT_REMOVE = 0
TEXT_NONE = 1


@dataclass
class PatternDef:
    key: str
    label: str
    regex: str
    flags: int = 0


PATTERNS: List[PatternDef] = [
    PatternDef("email", "电子邮箱", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    PatternDef(
        "phone_cn",
        "中国手机号",
        r"(?<!\d)1[3-9]\d{9}(?!\d)",
    ),
    PatternDef(
        "phone_landline",
        "固定电话",
        r"(?<!\d)(?:0\d{2,3}[-\s]?)?\d{7,8}(?:[-\s]\d{1,6})?(?!\d)",
    ),
    PatternDef(
        "id_card_cn",
        "身份证号",
        r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)",
    ),
    PatternDef(
        "bank_card",
        "银行卡号",
        r"(?<!\d)\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}(?:[\s\-]?\d{1,3})?(?!\d)",
    ),
    PatternDef("ip", "IP 地址", r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    PatternDef(
        "url",
        "网址链接",
        r"(?:https?://|www\.)[^\s<>\"'，。；、）】]+",
        re.IGNORECASE,
    ),
    PatternDef(
        "date",
        "日期",
        r"(?<!\d)(?:19|20)\d{2}[-/.年](?:0?[1-9]|1[0-2])[-/.月](?:0?[1-9]|[12]\d|3[01])日?(?!\d)",
    ),
    PatternDef(
        "passport_cn",
        "护照号",
        r"(?<![A-Za-z0-9])[EeGgDdSsPp]\d{8}(?!\d)",
    ),
    PatternDef(
        "plate_cn",
        "车牌号",
        r"[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼使领][A-HJ-NP-Z][A-HJ-NP-Z0-9]{4,5}[A-HJ-NP-Z0-9挂学警港澳]",
    ),
]

PATTERN_MAP: Dict[str, PatternDef] = {p.key: p for p in PATTERNS}


@dataclass
class RedactMatch:
    page: int
    rect: Tuple[float, float, float, float]
    text: str
    kind: str          # pattern key 或 "keyword" / "manual"

    def as_rect(self) -> pymupdf.Rect:
        return pymupdf.Rect(*self.rect)


@dataclass
class RedactOptions:
    fill_color: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    overlay_text: str = ""
    images: int = IMG_PIXELS
    graphics: int = GFX_IF_INTERSECT
    text_mode: int = TEXT_REMOVE
    also_clean_hidden: bool = True


@dataclass
class RedactResult:
    applied: int = 0
    pages_touched: int = 0
    removed_chars: int = 0


def find_matches(
    doc: pymupdf.Document,
    pages: Sequence[int],
    pattern_keys: Sequence[str] = (),
    keywords: Sequence[str] = (),
    case_sensitive: bool = False,
    progress: Progress_ = None,
) -> List[RedactMatch]:
    """按内置正则模式和关键词查找待涂销区域。"""
    pr = progress or Progress()
    matches: List[RedactMatch] = []

    compiled: List[Tuple[str, "re.Pattern[str]"]] = []
    for key in pattern_keys:
        pdef = PATTERN_MAP.get(key)
        if pdef:
            compiled.append((pdef.key, re.compile(pdef.regex, pdef.flags)))

    kw_flags = 0 if case_sensitive else re.IGNORECASE
    kw_re = [
        (f"keyword:{kw}", re.compile(re.escape(kw), kw_flags))
        for kw in keywords
        if kw and kw.strip()
    ]

    targets = [i for i in pages if 0 <= i < doc.page_count]
    for k, pno in enumerate(targets):
        pr.step(k, len(targets), f"扫描第 {pno + 1} 页")
        page = doc.load_page(pno)
        words = page.get_text("words") or []
        if not words:
            continue

        lines: Dict[Tuple[int, int], List] = {}
        for w in words:
            lines.setdefault((int(w[5]), int(w[6])), []).append(w)

        for group in lines.values():
            group.sort(key=lambda w: w[7])
            text = " ".join(w[4] for w in group)
            if not text.strip():
                continue

            offsets: List[Tuple[int, int]] = []
            pos = 0
            for w in group:
                offsets.append((pos, pos + len(w[4])))
                pos += len(w[4]) + 1

            for kind, rx in compiled + kw_re:
                for m in rx.finditer(text):
                    rects = [
                        pymupdf.Rect(w[0], w[1], w[2], w[3])
                        for w, (s, e) in zip(group, offsets)
                        if e > m.start() and s < m.end()
                    ]
                    if not rects:
                        continue
                    box = rects[0]
                    for r in rects[1:]:
                        box |= r
                    matches.append(
                        RedactMatch(
                            page=pno,
                            rect=(box.x0, box.y0, box.x1, box.y1),
                            text=m.group(0),
                            kind=kind,
                        )
                    )

    pr.report(100, "完成")
    return matches


def add_redactions(
    doc: pymupdf.Document,
    matches: Sequence[RedactMatch],
    options: Optional[RedactOptions] = None,
) -> int:
    """把匹配区域登记为涂销注释（尚未真正删除）。"""
    opts = options or RedactOptions()
    count = 0
    by_page: Dict[int, List[RedactMatch]] = {}
    for m in matches:
        by_page.setdefault(m.page, []).append(m)

    for pno, items in by_page.items():
        if not 0 <= pno < doc.page_count:
            continue
        page = doc.load_page(pno)
        for m in items:
            page.add_redact_annot(
                m.as_rect(),
                text=opts.overlay_text or None,
                fill=opts.fill_color,
            )
            count += 1
    return count


def apply_redactions(
    doc: pymupdf.Document,
    pages: Optional[Sequence[int]] = None,
    options: Optional[RedactOptions] = None,
    progress: Progress_ = None,
) -> RedactResult:
    """真正执行涂销：删除文字、处理图片与矢量图形。"""
    pr = progress or Progress()
    opts = options or RedactOptions()
    targets = (
        [i for i in pages if 0 <= i < doc.page_count]
        if pages is not None
        else list(range(doc.page_count))
    )

    applied = 0
    touched = set()
    for k, pno in enumerate(targets):
        pr.step(k, len(targets), f"涂销第 {pno + 1} 页")
        page = doc.load_page(pno)
        had = list(page.annots()) and any(
            a.type[0] == pymupdf.PDF_ANNOT_REDACT for a in page.annots()
        )
        if not had:
            continue
        page.apply_redactions(
            images=opts.images,
            graphics=opts.graphics,
            text=opts.text_mode,
        )
        applied += 1
        touched.add(pno)

    if opts.also_clean_hidden:
        pr.report(90, "清理隐藏文字")
        try:
            doc.scrub(hidden_text=True, javascript=False, metadata=False,
                      xml_metadata=False, embedded_files=False, attached_files=False,
                      thumbnails=False, links=False)
        except Exception:
            pass

    pr.report(100, "完成")
    return RedactResult(applied=applied, pages_touched=len(touched))


def redact_rects(
    doc: pymupdf.Document,
    rects_by_page: Dict[int, Sequence[Tuple[float, float, float, float]]],
    options: Optional[RedactOptions] = None,
) -> int:
    """直接按矩形区域涂销（界面框选用）。"""
    opts = options or RedactOptions()
    count = 0
    for pno, rects in rects_by_page.items():
        if not 0 <= pno < doc.page_count:
            continue
        page = doc.load_page(pno)
        for r in rects:
            page.add_redact_annot(pymupdf.Rect(*r), fill=opts.fill_color)
            count += 1
        page.apply_redactions(
            images=opts.images, graphics=opts.graphics, text=opts.text_mode
        )
    return count
