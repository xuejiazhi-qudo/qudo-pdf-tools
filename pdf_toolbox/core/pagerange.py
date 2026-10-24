"""页面范围字符串解析，例如 "1-3,5,8-" -> [0,1,2,4,7,8,...]。"""

from __future__ import annotations

import re
from typing import List

_TOKEN_RE = re.compile(r"^\s*(\d*)\s*(?:-\s*(\d*)\s*)?$")


class PageRangeError(ValueError):
    pass


def parse(spec: str, page_count: int) -> List[int]:
    """把 "1-3,5,8-" 这样的范围串解析成 0 基页索引列表（去重、保序）。

    页码按 1 基输入；开区间 "8-" 表示到最后一页；"-3" 表示从第一页开始。
    """
    if page_count <= 0:
        raise PageRangeError("文档没有页面")

    text = (spec or "").strip()
    if not text:
        return list(range(page_count))

    result: List[int] = []
    seen = set()

    for raw in text.split(","):
        chunk = raw.strip()
        if not chunk:
            continue
        m = _TOKEN_RE.match(chunk)
        if not m:
            raise PageRangeError(f"无法识别的页码范围：{chunk!r}")

        start_s, end_s = m.group(1), m.group(2)
        is_range = "-" in chunk

        if not is_range:
            if not start_s:
                raise PageRangeError(f"无法识别的页码范围：{chunk!r}")
            lo = hi = int(start_s)
        else:
            lo = int(start_s) if start_s else 1
            hi = int(end_s) if end_s else page_count

        if lo < 1 or hi < 1:
            raise PageRangeError("页码必须从 1 开始")
        if lo > page_count or hi > page_count:
            raise PageRangeError(f"页码超出范围，文档共 {page_count} 页")
        if lo > hi:
            lo, hi = hi, lo

        for p in range(lo - 1, hi):
            if p not in seen:
                seen.add(p)
                result.append(p)

    if not result:
        raise PageRangeError("没有选中任何页面")
    return result


def format(indices: List[int]) -> str:
    """把 0 基页索引列表压回 "1-3,5" 形式，用于界面回显。"""
    if not indices:
        return ""
    ordered = sorted(set(indices))
    groups: List[str] = []
    start = prev = ordered[0]
    for p in ordered[1:]:
        if p == prev + 1:
            prev = p
            continue
        groups.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
        start = prev = p
    groups.append(str(start + 1) if start == prev else f"{start + 1}-{prev + 1}")
    return ",".join(groups)


def chunk_even(total: int, parts: int) -> List[range]:
    """把 total 页尽量均匀切成 parts 份，返回 0 基 range 列表。"""
    if parts <= 0:
        raise PageRangeError("份数必须大于 0")
    parts = min(parts, total)
    base, extra = divmod(total, parts)
    out: List[range] = []
    cur = 0
    for i in range(parts):
        size = base + (1 if i < extra else 0)
        out.append(range(cur, cur + size))
        cur += size
    return out
