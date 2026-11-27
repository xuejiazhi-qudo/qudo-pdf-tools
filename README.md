# Qudo PDF Toolbox

**An offline, fully local desktop PDF toolkit** — built on PySide6 (Qt) and PyMuPDF. 21 tools covering merge, split, organize, crop, rotate, compress, encrypt/decrypt, redact, annotate, watermark, page numbers, fill & sign, content editing, text/image extraction, metadata cleaning, and Word/Excel export. No uploads, no server, no telemetry.

[English](#english) | [中文](#中文)

---

<a id="english"></a>
## English

### Highlights

- **Everything runs on your machine.** Files never leave your computer.
- **A real editor, not just converters.** Insert text/images as floating elements you can drag, resize with handles and double-click to edit; edit existing text inline on the page; move existing text blocks and images; redact sensitive data permanently.
- **Reader-grade viewer.** Continuous scrolling with async rendering, bookmark outline panel, uniform thumbnail grid, zoom/fit controls, undo/redo with atomic saves.
- **Bilingual UI.** English and Simplified Chinese, switchable at runtime (Help → Settings).
- **Single-file distribution.** Ships as one `QudoPDF.exe` (~130 MB) via PyInstaller.

### Feature list

**Viewer**

- Continuous scroll + background async rendering; zoom in/out, fit width, fit page
- Left navigation dock: **Outline** (auto-selected when the PDF has bookmarks; click to jump, current chapter highlighted while scrolling) and **Pages** (uniform thumbnail cells with page-number badges, multi-select, odd/even/range selection)
- Undo / redo (snapshot stack), unsaved-changes marker, atomic save (temp file + replace)

**Pages**

| Tool | Description |
| --- | --- |
| Merge PDF | Combine files in order; optional per-file page ranges |
| Split PDF | By ranges / every N pages / per page / N equal parts / odd-even / extract selection; optional ZIP |
| Organize Pages | Drag reorder, rotate, duplicate, delete, insert blank pages, insert pages from other PDFs, extract selection |
| Rotate Pages | Left / right / 180°, applied to selected or all pages |
| Crop & Trim Margins | Auto white-margin removal (background estimation + projection scan + confidence + safety margin) or manual four-side crop with unit conversion |
| Images to PDF | Page size / orientation / margins / background color / per-image rotation |
| PDF to Images | JPG / PNG / WebP with DPI presets, quality, max width, background (white / transparent / custom) |

**Convert**

| Tool | Description |
| --- | --- |
| PDF to Word | Editable DOCX (pdf2docx with tables; automatic native fallback in packaged builds), plain-text reflow, or layout-faithful page images |
| PDF to Excel | Ruled-line + alignment table detection, editable cell grid (add/remove rows & columns), XLSX / CSV export, three sheet layouts |

**Extract & Privacy**

| Tool | Description |
| --- | --- |
| Extract Text | Per-page browsing, in-result search, cleanup options; export TXT / Markdown / JSON / HTML |
| Extract Images | Embedded image list with filters, dedupe and preview; region (crop-box) export; optional ZIP with report |
| Clean Metadata | Inspect Info dict / XMP / attachments / JavaScript / fonts / form fields; 16 cleaning switches; exportable cleaning report |

**Edit**

| Tool | Description |
| --- | --- |
| Watermark | Text or logo, 9-grid position, tiling with stagger, rotation, opacity, margins/offsets; CJK-capable |
| Page Numbers | 9 numbering formats + custom template placeholders, odd/even mirrored layout, six header/footer zones, margins & offsets |
| Edit Content | Insert text (font family/size/color/alignment; box auto-fits the text) and images as floating elements — drag to move, drag handles to resize, double-click to edit; inline on-page text editing (click or drag over text and type); delete regions; replace / delete images; **existing page text and images can be dragged to new positions** |
| Fill & Sign | Text, dates (5 formats), symbols, initials, handwritten signature pad, typed signature, uploaded signature (white-background removal); form-field detection and filling |
| Annotate | Highlight / underline / strikeout / ink / free text / sticky note / stamp / rectangle / circle / line / arrow / image — stored as real PDF annotations with a properties panel, filterable list and optional flattening |
| Redact | Area select, snap-to-text-line, keyword search, sensitive-data regexes (email, phone, national ID, bank card, IP, URL, date, passport, license plate); permanent removal with optional full-page rasterization for maximum security |

**Security & Size**

| Tool | Description |
| --- | --- |
| Compress | Four levels: lossless restructure / balanced / strong / extreme (rasterize); grayscale, metadata removal, embedded-file removal, linearize |
| Encrypt | AES-256 / AES-128 / RC4; open password plus permission flags (print, high-quality print, modify, copy, annotate, fill forms, accessibility, assemble) |
| Unlock | Batch decryption with single or per-file passwords, authorization checkbox and digital-signature warnings |

**Also**: create blank PDFs (paper size / orientation / page count / background color); runtime language switch.

### Install & run

Requirements: Python 3.10+ (developed on 3.13); Windows 10/11 (system CJK fonts are used for signatures and the font picker).

```bash
pip install -r requirements.txt
python run.py            # or: python run.py some.pdf
```

### Package as a single executable

```bash
python -m PyInstaller QudoPDF.spec --noconfirm
# output: dist/QudoPDF.exe
```

Useful switches:

- `QUDOPDF_CONSOLE=1` — build a console variant for startup debugging
- `QUDOPDF_ONEDIR=1` — build a folder variant (faster startup, easier AV whitelisting)
- `QUDOPDF_SELFTEST=2500` — run the app, construct every tool UI, then quit (CI-friendly smoke test)

### Tests

```bash
python _test_engines.py   # engine-level functional tests (crop, encrypt, redact, convert, …)
python _smoke.py          # construct all 21+ tool dialogs/panels offscreen
python _e2e.py            # drive the tools end-to-end offscreen (24 assertions)
```

### Project layout

```
pdf-toolbox/
├── run.py                  # entry point
├── QudoPDF.spec            # PyInstaller configuration
├── requirements.txt
└── pdf_toolbox/
    ├── main.py             # QApplication bootstrap + self-test switch
    ├── core/
    │   ├── doc.py          # document session: render cache / undo stack / atomic save
    │   ├── worker.py       # thread-pool tasks with progress + cancellation
    │   ├── pagerange.py    # "1-3,5,8-" range parsing
    │   └── ops/            # UI-free engines: pages / crop / extract / redact /
    │                       # stamp / annotate / security / compress / convert / edit
    └── ui/
        ├── mainwindow.py   # menus, two-row toolbar, docks, status bar
        ├── viewer.py       # continuous viewer + background render thread
        ├── thumbnails.py   # thumbnail sidebar
        ├── outline.py      # bookmark tree panel
        ├── icons.py        # runtime-drawn vector icons (no external assets)
        ├── i18n.py         # zh↔en map + recursive retranslation walker
        ├── dialogmodules.py# static import table (PyInstaller module collection)
        └── dialogs/        # 21 tool dialogs / interactive panels
```

### License

This project depends on **PyMuPDF (AGPL-3.0)** and **pdf2docx (AGPL-3.0)** and is therefore released under the **AGPL-3.0**. For closed-source commercial distribution you must purchase a commercial PyMuPDF license from Artifex and remove the AGPL dependencies. Other dependencies: PySide6 (LGPL), openpyxl (MIT), python-docx (MIT), Pillow (MIT), numpy (BSD).

### Known limitations

- No OCR: scanned documents need OCR before text extraction or editable Word export
- Existing page content can be moved, re-typed and deleted, but not resized or rotated (floating elements can)
- Edited/inserted text is rewritten with standard or system fonts; glyph details may differ from the originally embedded font
- Vector graphics (lines / shapes) cannot yet be moved as a whole

---

<a id="中文"></a>
## 中文

**离线、全本地处理的桌面 PDF 工具集** —— 基于 PySide6 (Qt) 与 PyMuPDF，共 21 项工具：合并、拆分、整理、裁剪、旋转、压缩、加密/解密、涂销、标注、水印、页码、填写签名、内容编辑、文字/图片提取、元数据清除、转 Word/Excel。不上传、无服务端、无遥测。

### 亮点

- **全部处理在本机完成**，文件不出电脑；
- **是真编辑器，不只是转换器**：插入的文字/图片为浮层元素，可拖动、手柄缩放、双击改内容；页上直接改字；已有文字块与图片可拖动移动；敏感信息永久涂销；
- **阅读器级查看器**：连续滚动 + 异步渲染、书签目录面板、统一格子缩略图、缩放/适应、撤销/重做与原子保存；
- **中英双语界面**：帮助 → 设置 即时切换；
- **单文件分发**：PyInstaller 打包为单个 `QudoPDF.exe`（约 130 MB）。

### 功能清单

**查看器**：连续滚动 + 后台异步渲染；缩放/适应宽度/适应页面；左侧导航含**目录**（有书签自动显示、点击跳转、滚动高亮）与**页面**（统一格子缩略图 + 页码角标、多选、奇偶/范围选择）；撤销/重做、未保存标记、原子保存。

**页面**：PDF 合并（可按文件指定页码范围）｜PDF 拆分（范围/每 N 页/每页/平均 N 份/奇偶/提取选中，可打包 ZIP）｜页面整理（拖拽排序、旋转、复制、删除、插空白页、从他件插页、提取）｜旋转页面｜裁剪与去白边（背景估计 + 投影扫描 + 置信度 + 安全边距，或四边手动裁切）｜图片转 PDF（尺寸/方向/边距/背景/单图旋转）｜PDF 转图片（JPG/PNG/WebP、DPI、质量、最大宽度、背景）。

**转换**：PDF 转 Word（可编辑含表格 / 纯文字 / 版式还原整页图）｜PDF 转 Excel（线框 + 对齐双法检测、可编辑单元格、XLSX/CSV、三种工作表模式）。

**提取与隐私**：提取文字（分页/搜索/清理，TXT/Markdown/JSON/HTML）｜提取图片（内嵌列表 + 区域框选 + ZIP 报告）｜元数据清除（Info/XMP/附件/JS/字体/表单，16 项开关 + 清理报告）。

**编辑**：加水印（文字/Logo、九宫格、平铺错位、旋转、透明度、中文支持）｜添加页码（9 种格式 + 模板占位符、奇偶镜像、页眉页脚六区）｜内容编辑（插入文字/图片浮层可拖拽缩放、双击改内容、页上内联改字、删除区域、替换/删除图片、**已有文字与图片可拖动**）｜填写与签名（文字/日期/符号/首字母/手写板/打字/上传签名、表单检测填写）｜标注批注（高亮/下划线/删除线/画笔/文字/便签/图章/矩形/圆/直线/箭头/图片，真实注释对象 + 属性面板 + 可选压平）｜涂销（框选/吸附文本行/关键词/敏感信息正则：邮箱、手机、身份证、银行卡、IP、网址、日期、护照、车牌；可整页栅格化最高安全）。

**安全与体积**：压缩（无损/均衡/强力/极限四档，灰度、清元数据、线性化）｜加密（AES-256/128、RC4，打开密码 + 8 项权限位）｜解密（批量、单/逐文件密码、授权确认与签名提示）。

**其它**：新建空白 PDF（纸张/方向/页数/背景色）；界面中英双语。

### 安装与运行

要求 Python 3.10+（开发于 3.13）、Windows 10/11（签名与字体选择使用系统中文字体）。

```bash
pip install -r requirements.txt
python run.py            # 或 python run.py 某个文件.pdf
```

### 打包单个 exe

```bash
python -m PyInstaller QudoPDF.spec --noconfirm
# 产物：dist/QudoPDF.exe
```

- `QUDOPDF_CONSOLE=1`：带控制台版本（排查启动问题）
- `QUDOPDF_ONEDIR=1`：目录版本（启动更快）
- `QUDOPDF_SELFTEST=2500`：自检后自动退出（可用于 CI）

### 测试

```bash
python _test_engines.py   # 引擎级功能测试
python _smoke.py          # 离屏构造全部工具界面
python _e2e.py            # 离屏端到端驱动（24 项断言）
```

### 许可

依赖 **PyMuPDF（AGPL-3.0）** 与 **pdf2docx（AGPL-3.0）**，本仓库以 **AGPL-3.0** 发布；闭源商业分发需向 Artifex 购买 PyMuPDF 商业授权并移除 AGPL 依赖。其余依赖：PySide6 (LGPL)、openpyxl (MIT)、python-docx (MIT)、Pillow (MIT)、numpy (BSD)。

### 已知限制

- 无 OCR：扫描件需先 OCR 才能提取文字/转可编辑 Word；
- 页面已有内容可移动/改字/删除，但不能缩放或旋转（浮层元素可以）；
- 改字/插入文字以标准或系统字体重写，与原嵌入字体字形细节可能略有差异；
- 矢量图形（线条/色块）暂不支持整体移动。
