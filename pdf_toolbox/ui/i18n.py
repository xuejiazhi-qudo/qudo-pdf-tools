"""界面国际化：简体中文 / English。

策略：源码里的中文字面量即"键"。切换到英文时用 ZH2EN 映射递归替换控件文本；
切回中文时恢复首次记录的原文。带格式化占位符的字符串通过归一化
（{...} 与数字统一成 {}）匹配，翻译模板里的 {} 按顺序回填实际值。
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QTableWidget,
    QToolBar,
    QToolButton,
    QWidget,
)

LANG_ZH = "zh"
LANG_EN = "en"
LANGS = [(LANG_ZH, "简体中文"), (LANG_EN, "English")]

_SETTINGS_KEY = "language"

# ---------------------------------------------------------------- 翻译表

ZH2EN: Dict[str, str] = {
    # 主窗口 / 菜单 / 工具栏 / 状态栏
    "目录": "Outline",
    "页面": "Pages",
    "导航": "Navigation",
    "文件(&F)": "&File",
    "打开(&O)…": "&Open…",
    "重新打开": "Reopen",
    "保存(&S)": "&Save",
    "另存为…": "Save As…",
    "退出": "Exit",
    "编辑(&E)": "&Edit",
    "撤销": "Undo",
    "重做": "Redo",
    "视图(&V)": "&View",
    "放大": "Zoom In",
    "缩小": "Zoom Out",
    "适应宽度": "Fit Width",
    "适应页面": "Fit Page",
    "工具(&T)": "&Tools",
    "帮助(&H)": "&Help",
    "关于": "About",
    "设置": "Settings",
    "主工具栏": "Main Toolbar",
    "上一页": "Previous",
    "下一页": "Next",
    "工具": "Tools",
    "第 {} / {} 页": "Page {} / {}",
    "缩放 {}%": "Zoom {}%",
    "打开 PDF": "Open PDF",
    "PDF 文件 (*.pdf);;所有文件 (*)": "PDF files (*.pdf);;All files (*)",
    "需要密码": "Password required",
    "《{}》已加密，请输入打开密码：": "'{}' is encrypted. Enter the open password:",
    "密码错误": "Wrong password",
    "输入的密码不正确。": "The password is incorrect.",
    "打开失败": "Open failed",
    "保存失败": "Save failed",
    "另存为": "Save As",
    "PDF 文件 (*.pdf)": "PDF files (*.pdf)",
    "关于 {}": "About {}",
    "基于 PySide6 与 PyMuPDF 的离线 PDF 工具集，全部处理在本地完成，":
        "An offline PDF toolbox built on PySide6 and PyMuPDF. Everything is processed locally,",
    "不上传任何文件。\n\n包含合并、拆分、压缩、加密、涂销、标注、":
        "nothing is uploaded.\n\nIncludes merge, split, compress, encrypt, redact, annotate,",
    "水印、页码、填写签名、转 Word/Excel 等 20 项功能。":
        "watermark, page numbers, fill & sign, Word/Excel export and more.",
    "请先打开文件": "Open a file first",
    "该工具需要先打开一个 PDF 文件。": "This tool needs an open PDF file.",
    "{}：无法打开": "{}: cannot open",
    "有未保存的修改": "Unsaved changes",
    "当前文档有未保存的修改，是否保存？": "The document has unsaved changes. Save now?",
    "该文档没有目录。\n已切换到按页浏览。": "This document has no outline.\nSwitched to page-by-page view.",
    "{}　·　第 {} 页": "{} · Page {}",
    # 运行器 / 进度
    "准备中…": "Preparing…",
    "取消": "Cancel",
    "正在取消…": "Cancelling…",
    "未知错误": "Unknown error",
    "{}：失败": "{}: failed",
    # 缩略图 / 页面选择
    "全选": "Select all",
    "选中所有页": "Select all pages",
    "不选": "Clear",
    "清空选择": "Clear selection",
    "反选": "Invert",
    "奇": "Odd",
    "只选奇数页": "Odd pages only",
    "偶": "Even",
    "只选偶数页": "Even pages only",
    "页码范围，如 1-3,5,8-": "Page range, e.g. 1-3,5,8-",
    "页码范围无效": "Invalid page range",
    "选择页面": "Select pages",
    "页码范围，如 1-3,5": "Page range, e.g. 1-3,5",
    "当前页": "Current page",
    "缩略图已选页": "Selected in thumbnails",
    "如 1-3,5,8-": "e.g. 1-3,5,8-",
    # 工具注册表：名称 / 描述 / 短标签
    "转换": "Convert",
    "提取": "Extract",
    "编辑": "Edit",
    "安全与体积": "Security & Size",
    "PDF 合并": "Merge PDF",
    "把多个 PDF 按顺序合并成一个文件": "Combine multiple PDFs into one file in order",
    "PDF 拆分": "Split PDF",
    "按范围/每 N 页/每页/奇偶拆成多个文件": "Split by range / every N pages / per page / odd-even",
    "PDF 页面整理": "Organize Pages",
    "拖拽排序、删除、复制、旋转、插入空白页": "Drag to reorder, delete, duplicate, rotate, insert blank pages",
    "旋转 PDF 页面": "Rotate Pages",
    "左转/右转/180°，批量旋转选中或全部页": "Rotate left/right/180° for selected or all pages",
    "PDF 裁剪与去白边": "Crop & Trim Margins",
    "自动检测白边或按四边裁切量裁剪": "Auto-detect white margins or crop by margins",
    "图片转 PDF": "Images to PDF",
    "把 JPG/PNG/WebP 等图片合成 PDF": "Combine JPG/PNG/WebP images into a PDF",
    "PDF 转图片": "PDF to Images",
    "导出为 JPG/PNG/WebP，可选 DPI 与背景": "Export pages as JPG/PNG/WebP with DPI and background options",
    "PDF 转 Word": "PDF to Word",
    "导出可编辑 DOCX 或版式还原版本": "Export editable DOCX or a layout-faithful version",
    "PDF 转 Excel": "PDF to Excel",
    "检测表格并导出 XLSX/CSV，可编辑单元格": "Detect tables and export XLSX/CSV with editable cells",
    "提取 PDF 文字": "Extract Text",
    "按页查看/搜索，导出 TXT/Markdown/JSON": "View/search per page, export TXT/Markdown/JSON",
    "提取 PDF 图片": "Extract Images",
    "导出内嵌图片或框选区域，可打包 ZIP": "Export embedded images or a region, optionally zipped",
    "PDF 元数据清除": "Clean Metadata",
    "查看并清除标题/作者/XMP/附件等隐藏信息": "View and remove title/author/XMP/attachments and other hidden data",
    "PDF 加水印": "Add Watermark",
    "文字或 Logo 水印，支持平铺与旋转": "Text or logo watermark with tiling and rotation",
    "PDF 添加页码": "Add Page Numbers",
    "页码 + 页眉页脚，9 种格式与镜像排版": "Page numbers plus headers/footers, 9 formats and mirrored layout",
    "PDF 内容编辑": "Edit Content",
    "修改现有文字、删除区域、替换/删除图片": "Edit existing text, delete regions, replace/delete images",
    "PDF 填写与签名": "Fill & Sign",
    "添加文字/日期/符号/手写签名": "Add text, dates, symbols and handwritten signatures",
    "PDF 标注与批注": "Annotate",
    "高亮/画笔/文字/图形/便签/图章": "Highlight, ink, text, shapes, notes and stamps",
    "PDF 涂销": "Redact",
    "永久删除敏感文字与图像区域": "Permanently remove sensitive text and image regions",
    "PDF 压缩": "Compress PDF",
    "四档压缩，从无损优化到整页栅格化": "Four levels, from lossless optimization to full rasterization",
    "PDF 加密与密码保护": "Encrypt / Protect",
    "AES-256 设置打开密码与权限位": "AES-256 open password and permission flags",
    "解除 PDF 密码": "Unlock PDF",
    "输入正确密码后移除加密": "Remove encryption after entering the correct password",
    "合并": "Merge",
    "拆分": "Split",
    "整理": "Organize",
    "旋转": "Rotate",
    "裁剪": "Crop",
    "图转PDF": "Img2PDF",
    "转图片": "To Img",
    "转Word": "To Word",
    "转Excel": "To Excel",
    "提文字": "Text",
    "提图片": "Images",
    "元数据": "Metadata",
    "水印": "Watermark",
    "页码": "Numbers",
    "改内容": "Edit",
    "填写签名": "Fill+Sign",
    "标注": "Annotate",
    "涂销": "Redact",
    "压缩": "Compress",
    "加密": "Encrypt",
    "解密": "Unlock",
    # 标注面板
    "选择": "Select",
    "高亮": "Highlight",
    "下划线": "Underline",
    "删除线": "Strikeout",
    "画笔": "Ink",
    "文字": "Text",
    "便签": "Note",
    "图章": "Stamp",
    "矩形": "Rectangle",
    "圆形": "Circle",
    "直线": "Line",
    "箭头": "Arrow",
    "图片": "Image",
    "属性": "Properties",
    "颜色": "Color",
    "无填充": "No fill",
    "填充": "Fill",
    "不透明度": "Opacity",
    "线宽": "Line width",
    "字号": "Font size",
    "锁定（不可再编辑）": "Locked (no further editing)",
    "删除": "Delete",
    "复制": "Duplicate",
    "压平全部": "Flatten all",
    "标注列表": "Annotation list",
    "全部类型": "All types",
    "全部页": "All pages",
    "文字标注": "Text annotation",
    "输入文字：": "Enter text:",
    "作者：": "Author:",
    "内容：": "Content:",
    "选择图章：": "Choose stamp:",
    "选择图片": "Choose image",
    "图片 (*.png *.jpg *.jpeg)": "Images (*.png *.jpg *.jpeg)",
    "无法添加标注": "Cannot add annotation",
    "未选中任何标注": "No annotation selected",
    "压平标注": "Flatten annotations",
    "压平后标注会变成页面内容，无法再编辑或单独删除。确定继续？":
        "Flattened annotations become page content and can no longer be edited or removed individually. Continue?",
    "已压平": "Flattened",
    "共压平 {} 条标注。记得保存。": "Flattened {} annotations. Remember to save.",
    "第 {} 页": "Page {}",
    "共 {} 条标注": "{} annotations",
    # 通用对话框
    "关闭": "Close",
    "执行": "Run",
    "保存": "Save",
    "导出": "Export",
    "浏览…": "Browse…",
    "选择颜色": "Choose color",
    # 压缩
    "压缩级别": "Compression level",
    "级别": "Level",
    "使用默认值": "Default",
    "目标 DPI": "Target DPI",
    "图像质量": "Image quality",
    "转灰度": "Grayscale",
    "附加优化": "Extra optimization",
    "移除元数据": "Remove metadata",
    "移除附件/内嵌文件": "Remove attachments/embedded files",
    "线性化（便于网络浏览）": "Linearize (fast web view)",
    "选择压缩结果保存位置": "Choose where to save the compressed file",
    "压缩完成": "Compression finished",
    "压缩 PDF": "Compress PDF",
    # 裁剪
    "应用裁剪": "Apply crop",
    "自动去白边": "Auto trim margins",
    "低（只认深色内容）": "Low (dark content only)",
    "标准（推荐）": "Standard (recommended)",
    "高（浅色水印也算内容）": "High (light watermarks count as content)",
    "灵敏度": "Sensitivity",
    "安全边距": "Safety margin",
    "所有页面裁成相同尺寸": "Crop all pages to the same size",
    "手动裁切（按显示方向的四边裁切量）": "Manual crop (margins in display orientation)",
    "单位": "Unit",
    "四边联动": "Link all sides",
    "上": "Top",
    "右": "Right",
    "下": "Bottom",
    "左": "Left",
    "恢复原始尺寸": "Restore original size",
    "手动裁切": "Manual crop",
    "范围无效": "Invalid range",
    "未选择页面": "No pages selected",
    "没有要裁剪的页面。": "There are no pages to crop.",
    "，裁完尺寸一致": ", uniform size after crop",
    "裁剪完成": "Crop finished",
    "\n记得保存。": "\nRemember to save.",
    "已恢复": "Restored",
    "已恢复 {} 页的原始尺寸。": "Restored original size on {} pages.",
    # 内容编辑
    "改文字": "Edit text",
    "删除区域": "Delete region",
    "替换图片": "Replace image",
    "删除图片": "Delete image",
    "编辑文字": "Edit text",
    "编辑工具": "Editing tools",
    "未命中文字": "No text hit",
    "该位置没有可编辑的文字行。": "There is no editable text line at this position.",
    "已删除框选区域的内容。记得保存。": "Deleted the selected region. Remember to save.",
    "未命中图片": "No image hit",
    "该位置没有可替换的内嵌图片。": "There is no replaceable image at this position.",
    "选择新图片": "Choose new image",
    "图片 (*.png *.jpg *.jpeg *.webp)": "Images (*.png *.jpg *.jpeg *.webp)",
    "该位置没有可删除的内嵌图片。": "There is no deletable image at this position.",
    "新内容": "New content",
    # Excel
    "重新检测表格": "Re-detect tables",
    "正在检测…": "Detecting…",
    "添加行": "Add row",
    "删除选中行": "Delete selected rows",
    "添加列": "Add column",
    "删除选中列": "Delete selected columns",
    "排除/包含此表": "Exclude/include table",
    "导出选项": "Export options",
    "格式": "Format",
    "每个表格一个工作表": "One sheet per table",
    "每页一个工作表": "One sheet per page",
    "全部放入一个工作表": "All in one sheet",
    "工作表": "Sheets",
    "把可解析的单元格转成数值": "Convert parseable cells to numbers",
    "自动列宽": "Auto column width",
    "选择输出位置": "Choose output location",
    "正在检测表格…": "Detecting tables…",
    "（含无边框对齐表格，精度可能较低）": " (includes borderless aligned tables, lower accuracy)",
    "检测表格": "Detect tables",
    "列 {}": "Col {}",
    "没有可导出的表格": "No tables to export",
    "请先检测或包含至少一个表格。": "Detect or include at least one table first.",
    "导出完成": "Export finished",
    "导出表格": "Export tables",
    # 提取图片
    "重新扫描": "Rescan",
    "页": "Page",
    "全部": "All",
    "隐藏小于": "Hide smaller than",
    "不隐藏": "Show all",
    "合并重复图片": "Merge duplicates",
    "尺寸": "Size",
    "色彩空间": "Color space",
    "透明": "Alpha",
    "估计大小": "Est. size",
    "导出选中…": "Export selected…",
    "导出全部并打包 ZIP…": "Export all as ZIP…",
    "内嵌图片": "Embedded images",
    "导出倍率": "Export scale",
    "质量": "Quality",
    "在预览图上拖拽框选要导出的区域。": "Drag on the preview to select the export region.",
    "导出选区…": "Export region…",
    "区域导出": "Region export",
    "扫描图片": "Scan images",
    "是": "Yes",
    "否": "No",
    "无法预览": "Cannot preview",
    "图片 {}": "Image {}",
    "未选择图片": "No images selected",
    "请先勾选要导出的图片。": "Tick the images to export first.",
    "选择输出目录": "Choose output folder",
    "保存 ZIP": "Save ZIP",
    "打包图片": "Package images",
    "未框选区域": "No region selected",
    "请先在预览图上拖拽选择区域。": "Drag on the preview to choose a region first.",
    "保存选区": "Save region",
    "渲染选区": "Render region",
    "导出选区": "Export region",
    # 提取文字
    "重新提取": "Re-extract",
    "视图": "View",
    "在结果中搜索…": "Search in results…",
    "上一个": "Previous",
    "下一个": "Next",
    "文本清理": "Text cleanup",
    "合并多余空格": "Merge extra spaces",
    "合并空行": "Merge blank lines",
    "去除行首尾空白": "Trim line whitespace",
    "导出 TXT": "Export TXT",
    "导出 Markdown": "Export Markdown",
    "导出 JSON": "Export JSON",
    "导出 HTML": "Export HTML",
    "复制到剪贴板": "Copy to clipboard",
    "无文字": "no text",
    "{} 字": "{} chars",
    "提取文字": "Extract text",
    "导出文字": "Export text",
    "已复制": "Copied",
    "结果已复制到剪贴板。": "Results copied to the clipboard.",
    # 填写与签名
    "日期": "Date",
    "首字母": "Initials",
    "签名": "Signature",
    "⚠ 文档含数字签名，填写/签名会使其失效": "⚠ Document has a digital signature; filling/signing invalidates it",
    "未检测到表单字段，可直接点击页面添加内容。": "No form fields detected; click the page to add content.",
    "点击页面任意位置放置所选元素。": "Click anywhere on the page to place the selected element.",
    "放置工具（点击页面落位）": "Placement tools (click the page)",
    "表单字段填写": "Form field filling",
    "(未命名)": "(unnamed)",
    "(无表单字段)": "(no form fields)",
    "字段": "Field",
    "值": "Value",
    "填写选中字段": "Fill selected field",
    "已放置 0 个元素": "0 elements placed",
    "添加文字": "Add text",
    "日期格式": "Date format",
    "选择格式：": "Choose format:",
    "首字母缩写": "Initials",
    "输入缩写：": "Enter initials:",
    "没有表单字段": "No form fields",
    "该文档不含可填写的表单字段。": "This document has no fillable form fields.",
    "已填写": "Filled",
    "填写失败": "Fill failed",
    "找不到该字段。": "Field not found.",
    # 图片转 PDF
    "无边距": "No margin",
    "小（10mm）": "Small (10mm)",
    "中（20mm）": "Medium (20mm)",
    "大（30mm）": "Large (30mm)",
    "生成 PDF": "Create PDF",
    "添加图片…": "Add images…",
    "移除": "Remove",
    "左转": "Left",
    "右转": "Right",
    "上移": "Up",
    "下移": "Down",
    "清空": "Clear",
    "页面设置": "Page settings",
    "贴合图片尺寸": "Fit image size",
    "A4 横向": "A4 landscape",
    "页面尺寸": "Page size",
    "方向": "Orientation",
    "边距": "Margin",
    "背景色": "Background",
    "选择输出 PDF 位置": "Choose where to save the PDF",
    "无法读取图片": "Cannot read image",
    "没有图片": "No images",
    "请先添加至少一张图片。": "Add at least one image first.",
    "生成完成": "Created",
    # 合并
    "添加文件…": "Add files…",
    "拖拽可调整顺序；双击某一项可为该文件设置页码范围（默认全部页）。":
        "Drag to reorder; double-click an item to set its page range (default all pages).",
    "选中项的页码范围，如 1-3,5（留空=全部）": "Page range for the selected item, e.g. 1-3,5 (empty = all)",
    "选择合并结果保存位置": "Choose where to save the merged file",
    "输出文件": "Output file",
    "选择要合并的 PDF": "Choose PDFs to merge",
    "无法读取": "Cannot read",
    "页码范围": "Page range",
    "文件不足": "Not enough files",
    "至少需要两个 PDF 才能合并。": "At least two PDFs are required to merge.",
    "保存合并结果": "Save merged result",
    "合并完成": "Merge finished",
    "合并 PDF": "Merge PDF",
    # 元数据
    "标准元数据（标题/作者/主题/关键词/创建与修改时间/Creator/Producer）":
        "Standard metadata (title/author/subject/keywords/dates/Creator/Producer)",
    "XMP 扩展元数据": "XMP metadata",
    "隐藏文字（不可见文本层）": "Hidden text (invisible layer)",
    "内嵌 JavaScript": "Embedded JavaScript",
    "附件 / 内嵌文件": "Attachments / embedded files",
    "页面缩略图": "Page thumbnails",
    "链接（会破坏目录跳转）": "Links (breaks outline jumps)",
    "所有批注（会丢失标注）": "All annotations (loses markups)",
    "表单填写内容": "Form field values",
    "未应用的涂销标记": "Unapplied redactions",
    "清理页面内容流": "Clean page content streams",
    "应用清理": "Apply cleaning",
    "编辑元数据（留空=清除）": "Edit metadata (empty = clear)",
    "标题": "Title",
    "作者": "Author",
    "主题": "Subject",
    "关键词": "Keywords",
    "创建程序": "Creator",
    "生产者": "Producer",
    "写入这些元数据": "Write metadata",
    "推荐清理（默认开启）": "Recommended (on by default)",
    "高级清理（默认关闭，可能破坏内容）": "Advanced (off by default, may damage content)",
    "恢复默认": "Restore defaults",
    "导出清理报告…": "Export cleaning report…",
    "读取元数据": "Read metadata",
    "(空)": "(empty)",
    "无": "none",
    "(无)": "(none)",
    "已写入": "Written",
    "元数据已更新，记得保存。": "Metadata updated. Remember to save.",
    "确认高级清理": "Confirm advanced cleaning",
    "勾选的高级清理项可能破坏链接、批注或表单内容，确定继续？":
        "Selected advanced options may damage links, annotations or form content. Continue?",
    "清理完成": "Cleaning finished",
    "已清除：\n": "Cleared:\n",
    "无标准元数据": "No standard metadata",
    "尚未读取": "Not read yet",
    "请先等待元数据读取完成。": "Wait for the metadata scan to finish.",
    "保存报告": "Save report",
    "PDF 元数据报告": "PDF metadata report",
    "[标准元数据]": "[Standard metadata]",
    "[隐藏信息]": "[Hidden information]",
    "[字体]": "[Fonts]",
    "已导出": "Exported",
    # 整理
    "应用整理": "Apply organization",
    "移到首": "To start",
    "移到尾": "To end",
    "前移": "Back",
    "后移": "Forward",
    "插入空白页": "Insert blank page",
    "从文件插入…": "Insert from file…",
    "提取选中…": "Extract selected…",
    "重置": "Reset",
    "注意：应用整理会重建文档，数字签名将失效，书签/目录、内部链接与表单字段可能丢失。":
        "Note: applying rebuilds the document; digital signatures become invalid and bookmarks, internal links and form fields may be lost.",
    "空白": "blank",
    "不能删除全部": "Cannot delete all",
    "至少保留一页。": "Keep at least one page.",
    "选择要插入的 PDF": "Choose PDF to insert",
    "选择要插入的页面": "Choose pages to insert",
    "请先选择要提取的页面。": "Select pages to extract first.",
    "保存提取结果": "Save extraction",
    "没有可提取的页面": "No extractable pages",
    "选中的都是空白页或外部页，暂不支持提取。": "Selection contains only blank/external pages; extraction unsupported.",
    "提取完成": "Extraction finished",
    "没有页面": "No pages",
    "整理完成": "Organization finished",
    "插入": "Insert",
    "空白页设置": "Blank page settings",
    "宽": "Width",
    "高": "Height",
    "文档末尾": "End of document",
    "文档开头": "Start of document",
    "选中页之前": "Before selection",
    "选中页之后": "After selection",
    "位置": "Position",
    # 页码
    "左上": "Top left",
    "上中": "Top center",
    "右上": "Top right",
    "左下": "Bottom left",
    "下中": "Bottom center",
    "右下": "Bottom right",
    "左中": "Middle left",
    "正中": "Center",
    "右中": "Middle right",
    "添加页码": "Add page numbers",
    "页码位置": "Number position",
    "奇偶排版": "Odd/even layout",
    "奇数页": "Odd pages",
    "偶数页": "Even pages",
    "编号": "Numbering",
    "自定义模板": "Custom template",
    "起始编号": "Start number",
    "跳过前 N 页": "Skip first N pages",
    "跳过封面": "Skip cover",
    "自定义范围": "Custom range",
    "应用范围": "Apply to",
    "如 2-10,15": "e.g. 2-10,15",
    "编号方式": "Numbering mode",
    "「共 N 页」使用文档总页数": "Use document total for 'of N'",
    "样式": "Style",
    "字体": "Font",
    "粗体": "Bold",
    "页眉页脚（支持同样的占位符）": "Headers/footers (same placeholders)",
    "页眉 左/中/右": "Header L/C/R",
    "页脚 左/中/右": "Footer L/C/R",
    "边距与偏移（pt）": "Margins & offset (pt)",
    "上边距": "Top margin",
    "下边距": "Bottom margin",
    "左右边距": "Side margins",
    "X 偏移": "X offset",
    "Y 偏移": "Y offset",
    "设置无效": "Invalid settings",
    "页码已添加": "Page numbers added",
    # 转图片
    "标准（96 DPI）": "Standard (96 DPI)",
    "高清（150 DPI）": "HD (150 DPI)",
    "印刷（300 DPI）": "Print (300 DPI)",
    "自定义": "Custom",
    "分辨率": "Resolution",
    "自定义 DPI": "Custom DPI",
    "不限制": "Unlimited",
    "最大宽度": "Max width",
    "背景": "Background",
    "输出灰度": "Grayscale output",
    "输出": "Output",
    "输出目录": "Output folder",
    "留空则使用原文件名": "Empty = original file name",
    "文件名前缀": "File name prefix",
    "多张图片打包为 ZIP": "Zip multiple images",
    "缺少输出目录": "Missing output folder",
    "请先选择输出目录。": "Choose an output folder first.",
    "没有要导出的页面。": "There are no pages to export.",
    "没有导出文件": "Nothing exported",
    "请检查设置。": "Check the settings.",
    # 强度
    "弱": "Weak",
    "中": "Medium",
    "强": "Strong",
    # 加密
    "使用当前文档": "Use current document",
    "密码": "Password",
    "打开密码": "Open password",
    "确认密码": "Confirm password",
    "显示密码": "Show password",
    "强度": "Strength",
    "加密选项（网页版没有暴露权限位，这里补齐）": "Encryption options (permission flags included)",
    "算法": "Algorithm",
    "允许的操作": "Allowed operations",
    "多个文件时打包 ZIP": "Zip when multiple files",
    "选择 PDF": "Choose PDFs",
    "没有打开的文档": "No open document",
    "请先打开一个 PDF。": "Open a PDF first.",
    "没有文件": "No files",
    "请先添加要加密的 PDF。": "Add PDFs to encrypt first.",
    "密码不一致": "Passwords differ",
    "两次输入的密码不相同。": "The two passwords do not match.",
    "缺少密码": "Missing password",
    "请设置打开密码。": "Set an open password.",
    "请选择输出目录。": "Choose an output folder.",
    "加密完成": "Encryption finished",
    "加密 PDF": "Encrypt PDF",
    # 涂销
    "吸附到文本行": "Snap to text lines",
    "清空标记": "Clear marks",
    "删除选中标记": "Delete selected mark",
    "标记": "Marks",
    "输入关键词后回车查找": "Type a keyword and press Enter",
    "查找": "Find",
    "涂销选中项": "Redact selected",
    "涂销全部": "Redact all",
    "扫描敏感信息": "Scan sensitive data",
    "把勾选项加入涂销标记": "Add checked items as marks",
    "敏感信息": "Sensitive data",
    "涂销外观与安全": "Appearance & security",
    "覆盖色": "Cover color",
    "覆盖文字": "Cover text",
    "最高安全（整页栅格化）": "Maximum security (rasterize pages)",
    "应用涂销（不可撤销）": "Apply redaction (irreversible)",
    "在页面上拖拽框选要涂销的区域。": "Drag on the page to mark regions for redaction.",
    "未选择类型": "No types selected",
    "请先勾选要检测的敏感信息类型。": "Tick the sensitive-data types to detect first.",
    "没有标记": "No marks",
    "请先框选或添加要涂销的区域。": "Mark or add regions to redact first.",
    "确认涂销": "Confirm redaction",
    "涂销完成": "Redaction finished",
    # 旋转
    "应用旋转": "Apply rotation",
    "旋转角度（累加到页面现有旋转上）": "Rotation angle (added to existing page rotation)",
    "左转 90°": "Left 90°",
    "右转 90°": "Right 90°",
    "旋转 180°": "Rotate 180°",
    "旋转会直接修改当前文档（可撤销），确认后请记得保存。":
        "Rotation edits the current document (undoable). Remember to save.",
    "没有要旋转的页面。": "There are no pages to rotate.",
    "旋转完成": "Rotation finished",
    # 拆分
    "按范围拆分（每段一个文件）": "By ranges (one file each)",
    "每 N 页一个文件": "Every N pages",
    "每页一个文件": "One file per page",
    "平均切成 N 份": "Evenly into N parts",
    "奇偶页分开": "Odd/even split",
    "提取选中页为一个文件": "Extract selection to one file",
    "拆分方式": "Split mode",
    "模式": "Mode",
    "范围": "Ranges",
    "用分号分隔各段，如 1-3;4-6;7-": "Separate groups with semicolons, e.g. 1-3;4-6;7-",
    "每份页数": "Pages per file",
    "份数": "Parts",
    "多个文件时打包为 ZIP": "Zip when multiple files",
    "请先在左侧缩略图中选择要提取的页面。": "Select pages in the thumbnail panel first.",
    "提取页面": "Extract pages",
    "没有生成文件": "No files generated",
    "请检查拆分设置。": "Check the split settings.",
    "拆分完成": "Split finished",
    "拆分 PDF": "Split PDF",
    # 解密
    "解除密码": "Unlock",
    "检测": "Detect",
    "所有文件用同一个密码": "One password for all files",
    "每个文件单独输入": "Per-file passwords",
    "我确认有权解除这些文件的密码保护": "I confirm I am authorized to remove protection from these files",
    "待检测": "pending",
    "⚠含数字签名": "⚠ signed",
    "已加密": "encrypted",
    "未加密": "not encrypted",
    "需要授权确认": "Authorization required",
    "请先勾选授权确认复选框。": "Tick the authorization checkbox first.",
    "请先添加要解密的 PDF。": "Add PDFs to unlock first.",
    "解密完成": "Unlock finished",
    "输入密码": "Enter password",
    # 水印
    "添加水印": "Add watermark",
    "水印类型": "Watermark type",
    "文字水印": "Text watermark",
    "图片水印": "Image watermark",
    "内容": "Content",
    "选择水印图片（PNG 支持透明）": "Choose watermark image (PNG supports transparency)",
    "宽度": "Width",
    "外观与位置": "Appearance & position",
    "水平边距": "Horizontal margin",
    "垂直边距": "Vertical margin",
    "排布": "Layout",
    "平铺间距 X": "Tile spacing X",
    "平铺间距 Y": "Tile spacing Y",
    "错位平铺": "Staggered tiling",
    "置于内容上方（取消则垫在内容下）": "Above content (uncheck to place under)",
    "请先选择水印图片": "Choose a watermark image first",
    "水印已添加": "Watermark added",
    # 转 Word
    "转换模式": "Conversion mode",
    "可编辑（保留文字与表格版式，推荐）": "Editable (keeps text and table layout, recommended)",
    "纯文字（按段落重排）": "Plain text (reflowed paragraphs)",
    "版式还原（整页图片，文字不可选）": "Layout fidelity (page images, text not selectable)",
    "选择 DOCX 保存位置": "Choose where to save the DOCX",
    "使用 pdf2docx 还原文字、表格与基本版式，输出可直接编辑的 DOCX。":
        "Uses pdf2docx to recover text, tables and basic layout into an editable DOCX.",
    "只提取文字并按视觉段落重排，适合纯文本文档。":
        "Extracts text only and reflows it into visual paragraphs; best for plain-text documents.",
    "每页渲染成高清图片插入 Word，版式 100% 一致但文字不可选中。":
        "Renders each page as a high-res image into Word; layout is identical but text is not selectable.",
    "转换完成": "Conversion finished",
    # 签名对话框
    "插入签名": "Insert signature",
    "笔色": "Pen color",
    "笔宽": "Pen width",
    "手写": "Draw",
    "输入姓名": "Enter name",
    "姓名": "Name",
    "系统手写体": "System script",
    "黑体": "Hei (sans)",
    "宋体": "Song (serif)",
    "楷体": "Kai (script)",
    "倾斜": "Slant",
    "打字": "Type",
    "选择签名图片…": "Choose signature image…",
    "未选择": "Not selected",
    "抠除白底": "Remove white background",
    "白底容差": "White tolerance",
    "裁掉四周空白": "Crop whitespace",
    "上传": "Upload",
    "选择签名图片": "Choose signature image",
    "生成签名失败": "Failed to build signature",
    # 设置
    "语言": "Language",
    "界面语言（立即生效，已打开的对话框下次打开时更新）":
        "Interface language (applies immediately; open dialogs update when reopened)",
    "设置已保存": "Settings saved",
    # 新建 PDF
    "新建": "New",
    "新建 PDF": "New PDF",
    "纸张": "Paper",
    "页数": "Pages",
    "创建": "Create",
    "替换当前文档前确认（有未保存修改时）": "Confirm before replacing current document (if unsaved)",
    "当前文档有未保存的修改，新建会丢弃它们。继续？":
        "The current document has unsaved changes; creating a new one discards them. Continue?",
    " mm": " mm",
    # 插入文字 / 插入图片
    "插入文字": "Insert text",
    "插入图片": "Insert image",
    "对齐": "Alignment",
    "左对齐": "Left",
    "居中": "Center",
    "右对齐": "Right",
    "选择要插入的图片": "Choose image to insert",
    "图片 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*)":
        "Images (*.png *.jpg *.jpeg *.webp *.bmp);;All files (*)",
    "文字超出框": "Text overflows",
    "文本框放不下全部内容，已按框裁剪显示，可放大区域或减小字号。":
        "The text does not fit the box and was clipped. Enlarge the region or reduce the font size.",
    "已插入文字。记得保存。": "Text inserted. Remember to save.",
    "已插入图片。记得保存。": "Image inserted. Remember to save.",
    "当前工具：插入文字": "Current tool: Insert text",
    "选择/移动": "Select / Move",
    "自动（按内容选择）": "Auto (by content)",
    "内置中文黑体": "Built-in CJK Sans",
    "微软雅黑": "Microsoft YaHei",
    "宋体": "SimSun",
    "楷体": "KaiTi",
    "黑体": "SimHei",
    "应用到页面": "Apply to page",
    "删除选中元素": "Delete selected",
    "已应用": "Applied",
    "元素已写入页面。记得保存。": "Elements written to the page. Remember to save.",
    "已应用到页面。用「选择/移动」点击文字可继续编辑。记得保存。":
        "Applied to the page. Use 'Select / Move' and click text to keep editing. Remember to save.",
    "编辑选中元素": "Edit selected",
    "未选中元素": "No element selected",
    "先用「选择/移动」点选一个浮层元素，或双击它。":
        "Click a floating element with 'Select / Move' first, or double-click it.",
    "选择/移动：拖动浮层元素；双击浮层或点「编辑选中元素」可修改内容。\n":
        "Select/Move: drag floating elements; double-click one (or use 'Edit selected') to change its content.\n",
    "选择/移动：拖动浮层元素或页面已有文字/图片；双击浮层可改内容。\n":
        "Select/Move: drag floating elements or existing text/images; double-click a floating element to edit it.\n",
    "已移动文字。记得保存。": "Text moved. Remember to save.",
    "已移动图片。记得保存。": "Image moved. Remember to save.",
    "已移动{}（{}, {}）。记得保存。": "Moved {} by ({}, {}). Remember to save.",
    "该{}无法移动。": "This {} cannot be moved.",
    "已加入浮层，可拖动调整位置，完成后点「应用到页面」。":
        "Added as a floating element; drag to position, then click 'Apply to page'.",
    "当前工具：{}　待应用元素 {} 个": "Tool: {}　pending elements: {}",
    "插入文字/插入图片：拖拽框出区域（或单击用默认尺寸），插入后可用「选择/移动」拖动，\n":
        "Insert text/image: drag a region (or click for default size); then drag with 'Select / Move'.\n",
    "满意后点「应用到页面」写入 PDF；关闭面板或保存时会自动应用。\n":
        "Click 'Apply to page' when happy; applying is automatic on close or save.\n",
    "改文字：点击文字行替换；删除区域：拖拽删除；替换/删除图片：点击图片。\n":
        "Edit text: click a line to replace; Delete region: drag; Replace/delete image: click it.\n",
    "改文字：点击或框选文字后直接在页面上输入（Esc 取消，Ctrl+Enter 或点击别处提交）。\n":
        "Edit text: click or drag over text and type directly on the page (Esc cancels; Ctrl+Enter or click elsewhere commits).\n",
    "页上编辑中：Esc 取消，Ctrl+Enter 或点击别处提交。":
        "Editing on page: Esc cancels; Ctrl+Enter or click elsewhere commits.",
    "该位置没有可编辑的文字。": "There is no editable text at this position.",
    "插入文字/插入图片：拖拽框出区域（或单击用默认尺寸），插入后可用「选择/移动」拖动，满意后点「应用到页面」写入 PDF；关闭面板或保存时会自动应用。\n选择/移动：拖动浮层元素或页面已有文字/图片；双击浮层可改内容；选中后拖手柄可缩放。\n改文字：点击或框选文字后直接在页面上输入（Esc 取消，Ctrl+Enter 或点击别处提交）。\n删除区域：拖拽删除；替换/删除图片：点击图片。\n所有修改都可按 Ctrl+Z 撤销，记得保存。":
        "Insert text/image: drag a region (or click for a default size); then drag it with 'Select / Move'. Click 'Apply to page' when happy; applying is automatic on close or save.\n"
        "Select/Move: drag floating elements or existing text/images; double-click a floating element to edit it; drag its handles to resize.\n"
        "Edit text: click or drag over text and type directly on the page (Esc cancels; Ctrl+Enter or click elsewhere commits).\n"
        "Delete region: drag to remove; Replace/Delete image: click an image.\n"
        "All edits are undoable with Ctrl+Z. Remember to save.",
    "所有修改都可按 Ctrl+Z 撤销，记得保存。": "All edits are undoable with Ctrl+Z. Remember to save.",
    "插入文字/插入图片：拖拽框出放置区域（或单击用默认尺寸）。\n":
        "Insert text/image: drag a region (or click for a default size).\n",
}

# 运行时拼接串（源码里被拆成多行字面量）的补充映射
ZH2EN.update({
    "已选中：{}　第 {} 页": "Selected: {} page {}",
    "检测到 {} 个表单字段（可在下方直接填写）":
        "Detected {} form fields (fill them directly below)",
    "字段 {} 已更新。记得保存。": "Field {} updated. Remember to save.",
    "处理 {} 页，跳过 {} 页。记得保存。": "Processed {} pages, skipped {}. Remember to save.",
    "已把「{}」改为「{}」。记得保存。": "Changed '{}' to '{}'. Remember to save.",
    "已替换图片 xref={}。记得保存。": "Replaced image xref={}. Remember to save.",
    "已删除图片 xref={}。记得保存。": "Deleted image xref={}. Remember to save.",
    "已旋转 {} 页（{}°）。记得保存。": "Rotated {} pages ({}°). Remember to save.",
    "已裁剪 {} 页，跳过 {} 页（空白或无法检测）{}。":
        "Cropped {} pages, skipped {} (blank or undetectable){}.",
    "已裁剪 {} 页，跳过 {} 页。": "Cropped {} pages, skipped {}.",
    "现在共 {} 页。记得保存。": "Now {} pages in total. Remember to save.",
    "共 {} 页（原文档 {} 页）": "{} pages (source had {})",
    "共 {} 张图片": "{} images",
    "共 {} 个文件，合并后约 {} 页": "{} files, about {} pages after merge",
    "已保存到：\n{}\n大小 {}": "Saved to:\n{}\nSize {}",
    "共 {} 张到：\n{}": "{} images to:\n{}",
    "共 {} 张，已打包：\n{}": "{} images, zipped:\n{}",
    "共 {} 张：\n": "{} images:\n",
    "共 {} 个文件，已打包：\n{}": "{} files, zipped:\n{}",
    "共生成 {} 个文件：\n": "{} files generated:\n",
    "将生成 {} 个文件：{}{}": "Will generate {} files: {}{}",
    "{}（{} 页）": "{} ({} pages)",
    "显示 {} / {} 张": "Showing {} / {}",
    "共 {} 页　字符 {}　词 {}　无文字页 {}":
        "{} pages　chars {}　words {}　text-less pages {}",
    "第 {} 页　{}": "Page {}　{}",
    "第 {} 页　{}　{}×{}　{}": "Page {}　{}　{}×{}　{}",
    "检测到 {} 个表格{}": "Detected {} tables{}",
    "表格 {}　第 {} 页　{}×{}　{}": "Table {}　page {}　{}×{}　{}",
    "选区：{}×{} px（预览 1x）": "Region: {}×{} px (preview 1x)",
    "当前 {} 个涂销标记。应用后将永久删除这些区域的内容。":
        "{} redaction marks. Applying permanently removes content in these regions.",
    "第 {} 页　{}": "Page {}　{}",
    "第 {} 页　[{}]　{}": "Page {}　[{}]　{}",
    "找到 {} 处「{}」": "Found {} occurrences of '{}'",
    "检测到 {} 处敏感信息": "Detected {} sensitive items",
    "已加入 {} 个涂销标记": "Added {} redaction marks",
    "将永久删除 {} 个区域的内容，且不可撤销。建议先另存一份原件。\n确定继续？":
        "This permanently removes content in {} regions and cannot be undone. Keep a copy first.\nContinue?",
    "已永久删除 {} 个区域。记得保存。": "Permanently removed {} regions. Remember to save.",
    "已处理 {} 页。记得保存。": "Processed {} pages. Remember to save.",
    "压缩前 {} → 压缩后 {}": "Before {} → after {}",
    "（{}），节省 {}。\n{}": "({}), saved {}.\n{}",
    "已放置 {} 个元素。记得保存。": "Placed {} elements. Remember to save.",
    "原字号 {} pt　位置 ({}, {})": "Original size {} pt　at ({}, {})",
    "《{}》要合并的页码（留空=全部）：": "Pages of '{}' to merge (empty = all):",
    "《{}》的打开密码：": "Open password for '{}':",
    "{}　{} 页": "{}　{} pages",
    "页码 {}": "pages {}",
    "{} 页": "{} pages",
    "{}　(当前文档)": "{}　(current document)",
    "加密 {}": "Encrypting {}",
    "解密 {}": "Unlocking {}",
    "检测失败：{}": "Detection failed: {}",
    "当前工具：{}": "Current tool: {}",
    "当前工具：改文字": "Current tool: Edit text",
    "{}% 页宽": "{}% of page width",
    "25% 页宽": "25% of page width",
    "生成时间：{}": "Generated: {}",
    "文件：{}": "File: {}",
    "大小：{}": "Size: {}",
    "页数：{}": "Pages: {}",
    "格式：{}": "Format: {}",
    "加密：{}": "Encrypted: {}",
    "XMP 元数据：{}": "XMP metadata: {}",
    "预览：{}…": "Preview: {}…",
    "附件/内嵌文件：{} 个": "Attachments/embedded: {}",
    "批注：{} 个": "Annotations: {}",
    "链接：{} 个": "Links: {}",
    "表单字段：{} 个": "Form fields: {}",
    "内嵌 JavaScript：{}": "Embedded JavaScript: {}",
    "书签/目录条目：{} 个": "Outline entries: {}",
    "内嵌图片对象：{} 个": "Embedded image objects: {}",
    "=== 基本信息 ===": "=== Basic ===",
    "=== 标准元数据 ===": "=== Standard metadata ===",
    "=== 隐藏信息 ===": "=== Hidden information ===",
    "=== 字体 ===": "=== Fonts ===",
    "支持 {} {} {} {} {}": "Supports {} {} {} {} {}",
    "改文字：点击页面上的文字行，修改后回车确认（原文字会被移除并在原位写入新文字）。\n":
        "Edit text: click a text line, confirm to replace it in place.\n",
    "删除区域：拖拽框选要删除的文字/图形。\n": "Delete region: drag to remove text/graphics.\n",
    "替换/删除图片：点击页面上的图片。\n": "Replace/delete image: click an image on the page.\n",
    "所有修改都可按 Ctrl+Z 撤销，记得保存。": "All edits are undoable with Ctrl+Z. Remember to save.",
})


# ---------------------------------------------------------------- 匹配与查询

_EXACT: Dict[str, str] = dict(ZH2EN)


def _build_patterns() -> List[Tuple["re.Pattern[str]", str]]:
    out: List[Tuple["re.Pattern[str]", str]] = []
    for key, value in ZH2EN.items():
        if "{}" not in key:
            continue
        escaped = re.escape(key).replace("\\{\\}", "(.+?)")
        out.append((re.compile(f"^{escaped}$", re.DOTALL), value))
    # 长键优先，避免短键抢先匹配
    out.sort(key=lambda kv: -len(kv[0].pattern))
    return out


_PATTERNS = _build_patterns()

# 组合串里可能嵌套的标签，回填后再替换一次（白名单，避免误伤 PDF 自带中文标题）
_INNER_KEYS = [
    "高亮", "下划线", "删除线", "画笔", "文字", "便签", "图章",
    "矩形", "圆形", "直线", "箭头", "图片", "选择",
    "选择/移动", "插入文字", "插入图片", "改文字", "删除区域", "替换图片", "删除图片",
    "（含无边框对齐表格，精度可能较低）",
    "，裁完尺寸一致",
    "无文字",
]
_INNER = sorted(
    ((k, _EXACT[k]) for k in _INNER_KEYS if k in _EXACT),
    key=lambda kv: -len(kv[0]),
)


def _translate_inner(text: str) -> str:
    for zh, en in _INNER:
        if zh in text:
            text = text.replace(zh, en)
    return text


_LANG_CACHE: Optional[str] = None


def get_lang() -> str:
    global _LANG_CACHE
    if _LANG_CACHE is not None:
        return _LANG_CACHE
    try:
        value = QSettings().value(_SETTINGS_KEY, LANG_ZH)
    except Exception:  # noqa: BLE001
        value = LANG_ZH
    _LANG_CACHE = value if value in (LANG_ZH, LANG_EN) else LANG_ZH
    return _LANG_CACHE


def set_lang(lang: str) -> None:
    global _LANG_CACHE
    _LANG_CACHE = lang if lang in (LANG_ZH, LANG_EN) else LANG_ZH
    try:
        QSettings().setValue(_SETTINGS_KEY, _LANG_CACHE)
    except Exception:  # noqa: BLE001
        pass


def lang_label() -> str:
    return dict(LANGS).get(get_lang(), LANG_ZH)


def translate(text: Optional[str]) -> str:
    """把中文字面量翻译成当前语言；查不到就原样返回。"""
    if not text or get_lang() == LANG_ZH:
        return text or ""
    hit = _EXACT.get(text)
    if hit is not None:
        return hit
    for rx, tpl in _PATTERNS:
        m = rx.match(text)
        if m is None:
            continue
        out = tpl
        for group in m.groups():
            out = out.replace("{}", group, 1)
        return _translate_inner(out)
    return text


# ---------------------------------------------------------------- 递归重翻译

_P_TEXT = "_zh_text"
_P_TITLE = "_zh_title"
_P_WIN = "_zh_win"
_P_PLACE = "_zh_place"
_P_TIP = "_zh_tip"
_P_ITEMS = "_zh_items"
_P_SUFFIX = "_zh_suffix"
_P_PREFIX = "_zh_prefix"
_P_SPECIAL = "_zh_special"


def _swap(obj, getter, setter, prop: str) -> None:
    current = getter()
    if not current:
        return
    original = obj.property(prop)
    if original is None:
        obj.setProperty(prop, current)
        original = current
    setter(original if get_lang() == LANG_ZH else translate(original))


def _apply_widget(w: QWidget) -> None:
    if isinstance(w, QGroupBox):
        _swap(w, w.title, w.setTitle, _P_TITLE)
    elif isinstance(w, QDockWidget):
        _swap(w, w.windowTitle, w.setWindowTitle, _P_WIN)
    elif isinstance(w, (QLabel, QPushButton, QCheckBox, QRadioButton, QToolButton)):
        _swap(w, w.text, w.setText, _P_TEXT)
    elif isinstance(w, QToolBar):
        _swap(w, w.windowTitle, w.setWindowTitle, _P_WIN)
    elif w.isWindow():
        _swap(w, w.windowTitle, w.setWindowTitle, _P_WIN)

    if isinstance(w, QLineEdit):
        _swap(w, w.placeholderText, w.setPlaceholderText, _P_PLACE)
    if isinstance(w, QTabWidget):
        originals = w.property(_P_ITEMS)
        if originals is None:
            originals = [w.tabText(i) for i in range(w.count())]
            w.setProperty(_P_ITEMS, originals)
        for i, orig in enumerate(originals):
            w.setTabText(i, orig if get_lang() == LANG_ZH else translate(orig))
    if isinstance(w, QComboBox):
        originals = w.property(_P_ITEMS)
        if originals is None:
            originals = [w.itemText(i) for i in range(w.count())]
            w.setProperty(_P_ITEMS, originals)
        for i, orig in enumerate(originals):
            w.setItemText(i, orig if get_lang() == LANG_ZH else translate(orig))
    if isinstance(w, QAbstractSpinBox):
        _swap(w, w.suffix, w.setSuffix, _P_SUFFIX)
        _swap(w, w.prefix, w.setPrefix, _P_PREFIX)
        _swap(w, w.specialValueText, w.setSpecialValueText, _P_SPECIAL)
    if isinstance(w, QTableWidget):
        originals = w.property(_P_ITEMS)
        if originals is None:
            originals = [
                w.horizontalHeaderItem(c).text() if w.horizontalHeaderItem(c) else ""
                for c in range(w.columnCount())
            ]
            w.setProperty(_P_ITEMS, originals)
        for c, orig in enumerate(originals):
            item = w.horizontalHeaderItem(c)
            if item and orig:
                item.setText(orig if get_lang() == LANG_ZH else translate(orig))

    tip = w.toolTip()
    if tip:
        _swap(w, w.toolTip, w.setToolTip, _P_TIP)


def _apply_action(action: QAction) -> None:
    _swap(action, action.text, action.setText, _P_TEXT)
    if action.toolTip():
        _swap(action, action.toolTip, action.setToolTip, _P_TIP)


def retranslate_widget(root: QWidget) -> None:
    """按当前语言刷新 root 及其所有子控件/动作的文本。

    注意：QMenu 的标题由其 QAction 驱动，不能单独 swap，
    否则会把已翻译文本误存为"原文"，切回中文时覆盖错误。
    """
    _apply_widget(root)
    for child in root.findChildren(QWidget):
        _apply_widget(child)
    for action in root.findChildren(QAction):
        _apply_action(action)
    if isinstance(root, QMenuBar):
        for action in root.actions():
            _apply_action(action)


# ---------------------------------------------------------------- 设置对话框


class SettingsDialog(QDialog):
    def __init__(self, parent=None, on_changed=None) -> None:
        super().__init__(parent)
        self._on_changed = on_changed
        self.setWindowTitle(translate("设置"))
        self.setMinimumWidth(380)

        layout = QFormLayout(self)
        label = QLabel(translate("语言"))
        self._lang = QComboBox()
        for code, name in LANGS:
            self._lang.addItem(name, code)
        idx = [c for c, _ in LANGS].index(get_lang())
        self._lang.setCurrentIndex(idx)
        layout.addRow(label, self._lang)

        hint = QLabel(translate("界面语言（立即生效，已打开的对话框下次打开时更新）"))
        hint.setWordWrap(True)
        layout.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        retranslate_widget(self)

    def _accept(self) -> None:
        set_lang(self._lang.currentData())
        self.accept()
        if self._on_changed is not None:
            self._on_changed()
