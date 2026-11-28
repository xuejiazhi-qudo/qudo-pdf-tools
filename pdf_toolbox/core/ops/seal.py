"""印章图片生成与 PDF 盖章。"""

from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass
from typing import Optional, Sequence

import pymupdf
from PIL import Image, ImageDraw, ImageFont

from ..worker import Progress

Progress_ = Optional[Progress]
RED = (190, 20, 32, 255)
WHITE = (255, 255, 255, 255)

SHAPES = ("circle", "oval", "square", "rectangle")
POSITIONS = ("tl", "tc", "tr", "ml", "mc", "mr", "bl", "bc", "br")


@dataclass
class SealDesign:
    shape: str = "circle"
    main_text: str = "公司名称"
    secondary_text: str = ""
    add_star: bool = True
    date_text: str = ""
    add_date: bool = False
    style: str = "zhuwen"  # zhuwen (red text) | baiwen (white text)


def _font_path(latin: bool = False) -> Optional[str]:
    windows = os.environ.get("WINDIR", "C:/Windows")
    names = (
        ("arial.ttf", "arialbd.ttf", "calibri.ttf", "segoeui.ttf", "simsun.ttc")
        if latin else
        ("simsun.ttc", "simhei.ttf", "msyh.ttc", "simkai.ttf")
    )
    candidates = [os.path.join(windows, "Fonts", name) for name in names]
    return next((path for path in candidates if os.path.isfile(path)), None)


def _font(size: int, latin: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = _font_path(latin)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    initial: int,
    latin: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    size = max(12, initial)
    while size > 12:
        font = _font(size, latin)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return _font(12, latin)


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, max_width: int, initial: int, latin: bool):
    """Fit text in up to two centered lines, wrapping Latin at word boundaries."""
    text = text.strip()
    if not text:
        return [], _font(initial, latin)
    units = text.split() if latin else list(text)
    size = max(16, initial)
    while size >= 16:
        font = _font(size, latin)
        lines = []
        current = ""
        for unit in units:
            candidate = f"{current} {unit}".strip() if current and latin else current + unit
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = unit
            else:
                current = candidate
        if current:
            lines.append(current)
        if len(lines) <= 2 and all(draw.textbbox((0, 0), line, font=font)[2] <= max_width for line in lines):
            return lines, font
        size -= 2
    font = _font(16, latin)
    return [text], font


def _text_center(draw: ImageDraw.ImageDraw, xy, text: str, font, fill) -> None:
    draw.text(xy, text, font=font, fill=fill, anchor="mm", stroke_width=0)


def _arc_text(image: Image.Image, text: str, center, radius: float, font, fill) -> None:
    if not text:
        return
    count = len(text)
    if count == 1:
        angles = [-90.0]
    else:
        span = min(145.0, max(50.0, count * 15.0))
        angles = [(-90.0 - span / 2) + i * span / (count - 1) for i in range(count)]
    glyph_size = max(40, int(getattr(font, "size", 40) * 2.2))
    for char, angle in zip(text, angles):
        theta = math.radians(angle)
        x = center[0] + radius * math.cos(theta)
        y = center[1] + radius * math.sin(theta)
        glyph = Image.new("RGBA", (glyph_size, glyph_size), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glyph)
        gd.text((glyph_size / 2, glyph_size / 2), char, font=font, fill=fill, anchor="mm")
        tangent = angle + 90.0
        glyph = glyph.rotate(-tangent, resample=Image.Resampling.BICUBIC, expand=False)
        image.alpha_composite(glyph, (round(x - glyph_size / 2), round(y - glyph_size / 2)))


def _star_points(cx: float, cy: float, radius: float):
    points = []
    for i in range(10):
        angle = math.radians(-90 + i * 36)
        r = radius if i % 2 == 0 else radius * 0.43
        points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    return points


def render_seal_png(design: SealDesign, width_mm: float, height_mm: float, dpi: int = 600) -> bytes:
    """Render a high-resolution transparent seal image from a design."""
    if design.shape not in SHAPES:
        raise ValueError("未知的印章形状")
    if not design.main_text.strip():
        raise ValueError("请输入印章主文字")
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("印章尺寸必须大于 0")

    scale = dpi / 25.4
    width = max(240, round(width_mm * scale))
    height = max(240, round(height_mm * scale))
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = round(min(width, height) * 0.055)
    line = max(4, round(min(width, height) * 0.012))
    color = RED
    text_color = RED
    if design.style == "baiwen":
        color = WHITE
        text_color = WHITE

    if design.shape == "circle":
        side = min(width, height) - 2 * margin
        left, top = (width - side) // 2, (height - side) // 2
        box = (left, top, left + side, top + side)
        if design.style != "baiwen":
            draw.ellipse(box, outline=color, width=line * 2)
            inset = line * 3
            draw.ellipse((box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset), outline=color, width=line)
        else:
            draw.ellipse(box, fill=RED, outline=WHITE, width=line * 2)
            inset = line * 3
            draw.ellipse((box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset), outline=WHITE, width=line)
        center = (width / 2, height / 2)
        radius = side * 0.36
        main = design.main_text.strip()
        latin_main = main.isascii()
        main_font_size = max(24, round(side * (0.095 if latin_main else 0.105)))
        if latin_main:
            main_lines, main_font = _fit_lines(draw, main, round(side * 0.72), main_font_size, True)
            line_height = getattr(main_font, "size", 30) * 1.18
            first_y = height * 0.34 - (len(main_lines) - 1) * line_height / 2
            for line_index, line_text in enumerate(main_lines):
                _text_center(draw, (center[0], first_y + line_index * line_height), line_text, main_font, text_color)
        else:
            main_font = _font(main_font_size)
            _arc_text(image, main, center, radius, main_font, text_color)
        draw = ImageDraw.Draw(image)
        current_y = height * 0.51
        if design.add_star:
            star_radius = min(width, height) * 0.12
            draw.polygon(_star_points(center[0], current_y, star_radius), fill=text_color)
            current_y += star_radius * 1.45
        if design.secondary_text.strip():
            font = _fit_font(draw, design.secondary_text.strip(), width * 0.72, round(min(width, height) * 0.075))
            _text_center(draw, (center[0], current_y), design.secondary_text.strip(), font, text_color)
            current_y += getattr(font, "size", 20) * 1.2
        if design.add_date and design.date_text.strip():
            font = _fit_font(draw, design.date_text.strip(), width * 0.66, round(min(width, height) * 0.055))
            _text_center(draw, (center[0], min(height * 0.88, current_y + 4)), design.date_text.strip(), font, text_color)
    else:
        radius = margin // 2 if design.shape == "oval" else 0
        box = (margin, margin, width - margin, height - margin)
        if design.shape == "oval":
            draw.ellipse(box, fill=RED if design.style == "baiwen" else None, outline=color, width=line * 2)
            if design.style != "baiwen":
                draw.ellipse((margin + line * 3, margin + line * 3, width - margin - line * 3, height - margin - line * 3), outline=color, width=line)
        else:
            draw.rounded_rectangle(box, radius=radius, fill=RED if design.style == "baiwen" else None, outline=color, width=line * 2)
            if design.style != "baiwen":
                draw.rounded_rectangle((margin + line * 3, margin + line * 3, width - margin - line * 3, height - margin - line * 3), radius=max(0, radius - line), outline=color, width=line)
        center = (width / 2, height / 2)
        usable = width * 0.78
        main = design.main_text.strip()
        latin_main = main.isascii()
        main_lines, main_font = _fit_lines(
            draw, main, round(usable), round(min(width, height) * (0.12 if latin_main else 0.14)), latin_main
        )
        content_height = getattr(main_font, "size", 30) * len(main_lines) * 1.12
        second_font = _fit_font(draw, design.secondary_text.strip(), usable, round(min(width, height) * 0.085)) if design.secondary_text.strip() else None
        date_font = _fit_font(draw, design.date_text.strip(), usable, round(min(width, height) * 0.07)) if design.add_date and design.date_text.strip() else None
        extra_height = (getattr(second_font, "size", 0) if second_font else 0) + (getattr(date_font, "size", 0) if date_font else 0)
        star_size = min(width, height) * 0.105 if design.add_star else 0
        gap = min(width, height) * 0.035
        total = content_height + extra_height + (star_size * 2 if design.add_star else 0) + gap * 2
        y = center[1] - total / 2
        main_line_height = getattr(main_font, "size", 30) * 1.12
        for line_index, line_text in enumerate(main_lines):
            _text_center(
                draw,
                (center[0], y + main_line_height * (line_index + 0.5)),
                line_text,
                main_font,
                text_color,
            )
        y += content_height + gap
        if design.add_star:
            draw.polygon(_star_points(center[0], y + star_size, star_size), fill=text_color)
            y += star_size * 2 + gap
        if second_font:
            second = design.secondary_text.strip()
            h = getattr(second_font, "size", 20)
            _text_center(draw, (center[0], y + h / 2), second, second_font, text_color)
            y += h + gap
        if date_font:
            date = design.date_text.strip()
            h = getattr(date_font, "size", 18)
            _text_center(draw, (center[0], y + h / 2), date, date_font, text_color)

    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return stream.getvalue()


def load_image_bytes(path: str) -> tuple[bytes, float]:
    if not path or not os.path.isfile(path):
        raise ValueError("请选择有效的印章图片")
    try:
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            aspect = rgba.width / max(1, rgba.height)
            stream = io.BytesIO()
            rgba.save(stream, format="PNG", optimize=True)
            return stream.getvalue(), aspect
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"无法读取印章图片：{exc}") from exc


def _seam_slices(image_bytes: bytes, count: int) -> list[bytes]:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGBA")
        out = []
        for index in range(count):
            left = round(index * image.width / count)
            right = round((index + 1) * image.width / count)
            crop = image.crop((left, 0, max(left + 1, right), image.height))
            stream = io.BytesIO()
            crop.save(stream, format="PNG", optimize=True)
            out.append(stream.getvalue())
        return out


def apply_seal(
    doc: pymupdf.Document,
    image_bytes: bytes,
    width_mm: float,
    height_mm: float,
    pages: Optional[Sequence[int]] = None,
    position: str = "br",
    margin_mm: float = 12.0,
    seam: bool = False,
    seam_edge: str = "right",
    seam_depth_mm: float = 10.0,
    progress: Progress_ = None,
) -> int:
    """Place a seal at a physical size, optionally divided across page edges."""
    if not image_bytes:
        raise ValueError("印章图片为空")
    if position not in POSITIONS:
        raise ValueError("未知的印章位置")
    if seam_edge not in ("left", "right"):
        raise ValueError("骑缝章目前支持左侧或右侧页缘")
    if width_mm <= 0 or height_mm <= 0 or margin_mm < 0 or seam_depth_mm <= 0:
        raise ValueError("印章尺寸或边距无效")

    targets = list(pages) if pages is not None else list(range(doc.page_count))
    targets = [i for i in targets if 0 <= i < doc.page_count]
    if not targets:
        return 0
    if seam and targets != list(range(min(targets), max(targets) + 1)):
        raise ValueError("骑缝章需要选择连续页面")

    pr = progress or Progress()
    seam_images = _seam_slices(image_bytes, len(targets)) if seam else []
    mm_to_pt = 72.0 / 25.4
    width = width_mm * mm_to_pt
    height = height_mm * mm_to_pt
    margin = margin_mm * mm_to_pt
    seam_strip = seam_depth_mm * mm_to_pt / len(targets)

    for index, page_index in enumerate(targets):
        pr.step(index, len(targets), f"第 {page_index + 1} 页")
        page = doc.load_page(page_index)
        page_width, page_height = page.rect.width, page.rect.height
        if seam:
            rect_width = min(seam_strip, max(1.0, page_width - margin))
            rect_height = min(height, max(1.0, page_height - margin * 2))
            y = (page_height - rect_height) / 2
            if position.startswith("t"):
                y = margin
            elif position.startswith("b"):
                y = page_height - margin - rect_height
            x = margin if seam_edge == "left" else page_width - margin - rect_width
            page.insert_image(
                pymupdf.Rect(x, y, x + rect_width, y + rect_height),
                stream=seam_images[index], overlay=True,
            )
            continue

        left = margin if position.endswith("l") else (page_width - width) / 2 if position.endswith("c") else page_width - margin - width
        top = margin if position.startswith("t") else (page_height - height) / 2 if position.startswith("m") else page_height - margin - height
        page.insert_image(
            pymupdf.Rect(left, top, left + width, top + height),
            stream=image_bytes,
            overlay=True,
        )

    pr.report(100, "印章已盖入 PDF")
    return len(targets)
