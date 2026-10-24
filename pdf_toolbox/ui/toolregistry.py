"""20 个 PDF 工具的注册表。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class ToolDef:
    key: str
    name: str
    desc: str
    group: str
    dialog: str          # ui.dialogs 下的模块名
    needs_doc: bool = True
    kind: str = "dialog"  # dialog | mode


GROUP_PAGE = "页面"
GROUP_CONVERT = "转换"
GROUP_EXTRACT = "提取"
GROUP_EDIT = "编辑"
GROUP_SECURITY = "安全与体积"

TOOLS: List[ToolDef] = [
    ToolDef("merge", "PDF 合并", "把多个 PDF 按顺序合并成一个文件", GROUP_PAGE, "merge", needs_doc=False),
    ToolDef("split", "PDF 拆分", "按范围/每 N 页/每页/奇偶拆成多个文件", GROUP_PAGE, "split"),
    ToolDef("organize", "PDF 页面整理", "拖拽排序、删除、复制、旋转、插入空白页", GROUP_PAGE, "organize"),
    ToolDef("rotate", "旋转 PDF 页面", "左转/右转/180°，批量旋转选中或全部页", GROUP_PAGE, "rotate"),
    ToolDef("crop", "PDF 裁剪与去白边", "自动检测白边或按四边裁切量裁剪", GROUP_PAGE, "crop"),
    ToolDef("image_to_pdf", "图片转 PDF", "把 JPG/PNG/WebP 等图片合成 PDF", GROUP_PAGE, "image_to_pdf", needs_doc=False),
    ToolDef("pdf_to_image", "PDF 转图片", "导出为 JPG/PNG/WebP，可选 DPI 与背景", GROUP_PAGE, "pdf_to_image"),

    ToolDef("pdf_to_word", "PDF 转 Word", "导出可编辑 DOCX 或版式还原版本", GROUP_CONVERT, "word"),
    ToolDef("pdf_to_excel", "PDF 转 Excel", "检测表格并导出 XLSX/CSV，可编辑单元格", GROUP_CONVERT, "excel"),

    ToolDef("extract_text", "提取 PDF 文字", "按页查看/搜索，导出 TXT/Markdown/JSON", GROUP_EXTRACT, "extract_text"),
    ToolDef("extract_images", "提取 PDF 图片", "导出内嵌图片或框选区域，可打包 ZIP", GROUP_EXTRACT, "extract_images"),
    ToolDef("metadata", "PDF 元数据清除", "查看并清除标题/作者/XMP/附件等隐藏信息", GROUP_EXTRACT, "metadata"),

    ToolDef("watermark", "PDF 加水印", "文字或 Logo 水印，支持平铺与旋转", GROUP_EDIT, "watermark"),
    ToolDef("page_numbers", "PDF 添加页码", "页码 + 页眉页脚，9 种格式与镜像排版", GROUP_EDIT, "page_numbers"),
    ToolDef("edit_content", "PDF 内容编辑", "修改现有文字、删除区域、替换/删除图片", GROUP_EDIT, "edit_content", kind="mode"),
    ToolDef("fill_sign", "PDF 填写与签名", "添加文字/日期/符号/手写签名", GROUP_EDIT, "fill_sign", kind="mode"),
    ToolDef("annotate", "PDF 标注与批注", "高亮/画笔/文字/图形/便签/图章", GROUP_EDIT, "annotate", kind="mode"),
    ToolDef("redact", "PDF 涂销", "永久删除敏感文字与图像区域", GROUP_EDIT, "redact", kind="mode"),

    ToolDef("compress", "PDF 压缩", "四档压缩，从无损优化到整页栅格化", GROUP_SECURITY, "compress"),
    ToolDef("protect", "PDF 加密与密码保护", "AES-256 设置打开密码与权限位", GROUP_SECURITY, "protect", needs_doc=False),
    ToolDef("unlock", "解除 PDF 密码", "输入正确密码后移除加密", GROUP_SECURITY, "unlock", needs_doc=False),
]

TOOL_MAP: Dict[str, ToolDef] = {t.key: t for t in TOOLS}

# 工具栏按钮用的短标签（完整名称在菜单与悬停提示里）
SHORT_LABELS: Dict[str, str] = {
    "merge": "合并",
    "split": "拆分",
    "organize": "整理",
    "rotate": "旋转",
    "crop": "裁剪",
    "image_to_pdf": "图转PDF",
    "pdf_to_image": "转图片",
    "pdf_to_word": "转Word",
    "pdf_to_excel": "转Excel",
    "extract_text": "提文字",
    "extract_images": "提图片",
    "metadata": "元数据",
    "watermark": "水印",
    "page_numbers": "页码",
    "edit_content": "改内容",
    "fill_sign": "填写签名",
    "annotate": "标注",
    "redact": "涂销",
    "compress": "压缩",
    "protect": "加密",
    "unlock": "解密",
}

GROUP_ORDER = [GROUP_PAGE, GROUP_CONVERT, GROUP_EXTRACT, GROUP_EDIT, GROUP_SECURITY]
