"""工具模块的静态导入表。

必须用静态 import 而不是 importlib.import_module：PyInstaller 只做静态分析，
动态导入的对话框模块不会被打进 exe，导致打包版里点任何工具都没反应。
"""

from __future__ import annotations

from .dialogs import annotate
from .dialogs import compress
from .dialogs import crop
from .dialogs import edit_content
from .dialogs import excel
from .dialogs import extract_images
from .dialogs import extract_text
from .dialogs import fill_sign
from .dialogs import image_to_pdf
from .dialogs import merge
from .dialogs import metadata
from .dialogs import new_pdf
from .dialogs import organize
from .dialogs import page_numbers
from .dialogs import pdf_to_image
from .dialogs import protect
from .dialogs import redact
from .dialogs import rotate
from .dialogs import split
from .dialogs import unlock
from .dialogs import watermark
from .dialogs import word

DIALOG_MODULES = {
    "merge": merge,
    "split": split,
    "organize": organize,
    "rotate": rotate,
    "crop": crop,
    "image_to_pdf": image_to_pdf,
    "pdf_to_image": pdf_to_image,
    "pdf_to_word": word,
    "pdf_to_excel": excel,
    "extract_text": extract_text,
    "extract_images": extract_images,
    "metadata": metadata,
    "new_pdf": new_pdf,
    "watermark": watermark,
    "page_numbers": page_numbers,
    "compress": compress,
    "protect": protect,
    "unlock": unlock,
}

PANEL_MODULES = {
    "annotate": annotate,
    "redact": redact,
    "fill_sign": fill_sign,
    "edit_content": edit_content,
}


def all_modules() -> dict:
    merged = dict(DIALOG_MODULES)
    merged.update(PANEL_MODULES)
    return merged
