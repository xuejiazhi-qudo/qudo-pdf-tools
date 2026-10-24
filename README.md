# Qudo PDF 工具箱 / Qudo PDF Toolbox

**离线、本地处理的桌面 PDF 工具集** —— 基于 PySide6 (Qt) 与 PyMuPDF，覆盖合并、拆分、压缩、加密、涂销、标注、水印、页码、填写签名、内容编辑、转 Word/Excel 等 21 项功能。
**An offline, fully local desktop PDF toolkit** — built on PySide6 (Qt) and PyMuPDF, covering merge, split, compress, encrypt, redact, annotate, watermark, page numbers, fill & sign, content editing, Word/Excel export and more (21 tools).

[中文](#中文) | [English](#english)

---

## 中文

### 功能一览

**查看器**

- 连续滚动阅读 + 后台异步渲染，缩放 / 适应宽度 / 适应页面
- 左侧导航：**目录**（有书签时自动显示，点击跳转、滚动高亮）与**页面**（统一格子的缩略图、多选、奇偶/范围选择）
- 撤销 / 重做（内存快照栈），未保存标记，原子保存（先写临时文件再替换）

**页面**

| 工具 | 说明 |
| --- | --- |
| PDF 合并 | 多文件按顺序合并，可为每个文件指定页码范围 |
| PDF 拆分 | 按范围 / 每 N 页 / 每页 / 平均 N 份 / 奇偶 / 提取选中页，多文件可打包 ZIP |
| PDF 页面整理 | 拖拽排序、旋转、复制、删除、插入空白页、从其它 PDF 插页、提取选中页 |
| 旋转 PDF 页面 | 左转 / 右转 / 180°，作用于选中页或全部页 |
| PDF 裁剪与去白边 | 背景色估计 + 投影扫描自动去白边（含置信度与安全边距），或按四边裁切量手动裁剪 |
| 图片转 PDF | 多图合成，页面尺寸 / 方向 / 边距 / 背景色 / 单图旋转 |
| PDF 转图片 | JPG / PNG / WebP，DPI、质量、最大宽度、背景（白 / 透明 / 自定义） |

**转换**

| 工具 | 说明 |
| --- | --- |
| PDF 转 Word | 可编辑（pdf2docx，含表格版式；打包版自动回退原生实现）、纯文字、版式还原（整页图片） |
| PDF 转 Excel | 线框法 + 对齐法表格检测，可编辑单元格/行列后导出 XLSX / CSV，三种工作表模式 |

**提取与隐私**

| 工具 | 说明 |
| --- | --- |
| 提取 PDF 文字 | 分页查看 / 搜索 / 清理，导出 TXT / Markdown / JSON / HTML |
| 提取 PDF 图片 | 内嵌图片列表（过滤/去重/预览）+ 区域框选导出，可打包 ZIP |
| PDF 元数据清除 | 查看 Info / XMP / 附件 / JS / 字体等，16 项清理开关，导出清理报告 |

**编辑**

| 工具 | 说明 |
| --- | --- |
| PDF 加水印 | 文字或图片水印，九宫格位置 / 平铺 / 错位 / 旋转 / 透明度，支持中文 |
| PDF 添加页码 | 9 种编号格式 + 自定义模板，奇偶镜像，页眉页脚六区 |
| PDF 内容编辑 | 插入文字（字体/字号/颜色/对齐，框随文字自动收紧）、插入图片；**浮层元素可拖动、可手柄缩放、双击改内容**；页上直接改字（内联编辑器）；删除区域；替换 / 删除图片；**页面已有文字与图片也可拖动移动** |
| PDF 填写与签名 | 文字 / 日期 / 符号 / 首字母 / 手写签名板 / 打字签名 / 上传签名，表单字段检测与填写 |
| PDF 标注与批注 | 高亮 / 下划线 / 删除线 / 画笔 / 文字 / 便签 / 图章 / 矩形 / 圆形 / 直线 / 箭头 / 图片，真实 PDF 注释对象，属性面板 + 列表筛选 + 可选压平 |
| PDF 涂销 | 框选 / 吸附文本行 / 关键词 / 敏感信息正则（邮箱、手机、身份证、银行卡、IP、网址、日期、护照、车牌），永久删除并可整页栅格化 |

**安全与体积**

| 工具 | 说明 |
| --- | --- |
| PDF 压缩 | 四档：无损优化 / 均衡 / 强力 / 极限（整页栅格化），可转灰度、清元数据、线性化 |
| PDF 加密 | AES-256/128、RC4，打开密码 + 权限位（打印/复制/修改/批注/填表/无障碍/组装） |
| 解除 PDF 密码 | 批量，单密码或逐文件密码，授权确认与数字签名提示 |

**其它**：新建空白 PDF（纸张 / 方向 / 页数 / 背景色）；界面中英双语（帮助 → 设置）。

### 安装与运行

要求：Python 3.10+（开发于 3.13）、Windows 10/11（系统中文字体用于签名与字体选择）。

```bash
pip install -r requirements.txt
python run.py            # 或 python run.py 某个文件.pdf
```

### 打包成单个 exe

```bash
python -m PyInstaller QudoPDF.spec --noconfirm
# 产物：dist/QudoPDF.exe
```

- `QUDOPDF_CONSOLE=1` 打带控制台版本（排查启动问题）
- `QUDOPDF_ONEDIR=1` 打目录版（启动更快）
- 运行 `QUDOPDF_SELFTEST=2500 dist/QudoPDF.exe` 可让应用自检后自动退出（用于 CI）

### 测试

```bash
python _test_engines.py   # 引擎级功能测试
python _smoke.py          # 离屏构造全部工具界面
python _e2e.py            # 离屏驱动 20+ 工具真实执行（24 项断言）
```

### 项目结构

```
pdf-toolbox/
├── run.py                  # 入口
├── QudoPDF.spec            # PyInstaller 配置
├── requirements.txt
└── pdf_toolbox/
    ├── main.py             # QApplication  bootstrap + 自检开关
    ├── core/
    │   ├── doc.py          # 文档会话：渲染缓存 / 撤销栈 / 原子保存
    │   ├── worker.py       # 线程池任务 + 进度 + 取消
    │   ├── pagerange.py    # "1-3,5,8-" 范围解析
    │   └── ops/            # 与 UI 解耦的引擎：pages/crop/extract/redact/
    │                       # stamp/annotate/security/compress/convert/edit
    └── ui/
        ├── mainwindow.py   # 菜单 / 双行工具栏 / dock / 状态栏
        ├── viewer.py       # 连续滚动查看器 + 后台渲染线程
        ├── thumbnails.py   # 缩略图侧栏
        ├── outline.py      # 目录树
        ├── icons.py        # 运行时绘制的矢量图标（无外部资源）
        ├── i18n.py         # 中英映射 + 递归重翻译
        ├── dialogmodules.py# 静态导入表（PyInstaller 依赖它收集模块）
        └── dialogs/        # 21 个工具对话框 / 交互面板
```

### 许可

本项目依赖 **PyMuPDF（AGPL-3.0）** 与 **pdf2docx（AGPL-3.0）**，因此本仓库以 **AGPL-3.0** 发布。若需闭源商业分发，请向 Artifex 购买 PyMuPDF 商业授权并移除 AGPL 依赖。其余依赖：PySide6 (LGPL)、openpyxl (MIT)、python-docx (MIT)、Pillow (MIT)、numpy (BSD)。

### 已知限制

- 无 OCR（扫描件转 Word/提取文字需先 OCR）
- 页面已有内容可移动/改字/删除，但不能缩放或旋转（浮层元素可以）
- 改字/插入文字使用标准字体或系统字体重写，与原嵌入字体的字形细节可能略有差异
- 矢量图形（线条/色块）暂不支持整体移动

---

## English

### Features

**Viewer**

- Continuous scrolling with background async rendering; zoom / fit width / fit page
- Left navigation: **Outline** (auto-shown when bookmarks exist, click to jump, scroll highlight) and **Pages** (uniform thumbnail grid, multi-select, odd/even/range selection)
- Undo / redo (in-memory snapshot stack), dirty marker, atomic save (temp file + replace)

**Pages**

| Tool | Description |
| --- | --- |
| Merge PDF | Combine files in order, optional per-file page ranges |
| Split PDF | By ranges / every N pages / per page / N equal parts / odd-even / extract selection; optional ZIP |
| Organize Pages | Drag reorder, rotate, duplicate, delete, insert blank pages, insert from other PDFs, extract |
| Rotate Pages | Left / right / 180°, applied to selected or all pages |
| Crop & Trim | Auto white-margin detection (background estimation + projection + confidence + safety margin) or manual four-side crop |
| Images to PDF | Page size / orientation / margins / background / per-image rotation |
| PDF to Images | JPG / PNG / WebP with DPI, quality, max width, background (white / transparent / custom) |

**Convert**

| Tool | Description |
| --- | --- |
| PDF to Word | Editable (pdf2docx with tables; automatic native fallback in packaged builds), plain text, or layout-faithful page images |
| PDF to Excel | Ruled + alignment table detection, editable grid, XLSX / CSV export, three sheet modes |

**Extract & Privacy**

| Tool | Description |
| --- | --- |
| Extract Text | Per-page view / search / cleanup, export TXT / Markdown / JSON / HTML |
| Extract Images | Embedded image list (filter / dedupe / preview) plus region export, optional ZIP |
| Clean Metadata | Inspect Info / XMP / attachments / JS / fonts; 16 cleaning switches; cleaning report |

**Edit**

| Tool | Description |
| --- | --- |
| Watermark | Text or image, 9-grid position / tiling / stagger / rotation / opacity, CJK supported |
| Page Numbers | 9 formats + custom template, odd/even mirrored layout, six header/footer zones |
| Edit Content | Insert text (font/size/color/align, box auto-fits content) and images as **floating elements: drag, resize via handles, double-click to edit**; inline on-page text editing; delete regions; replace / delete images; **existing page text and images can be dragged to move** |
| Fill & Sign | Text / date / symbols / initials / draw-pad signature / typed signature / uploaded signature; form field detection and filling |
| Annotate | Highlight / underline / strikeout / ink / free text / note / stamp / rect / circle / line / arrow / image as real PDF annotations, properties panel, list filters, optional flattening |
| Redact | Area / snap-to-line / keyword / sensitive-data regexes (email, phone, ID, bank card, IP, URL, date, passport, plate); permanent removal with optional full-page rasterization |

**Security & Size**

| Tool | Description |
| --- | --- |
| Compress | Four levels: lossless / balanced / strong / extreme (rasterize); grayscale, metadata removal, linearize |
| Encrypt | AES-256/128, RC4; open password + permission flags (print/copy/modify/annotate/form/accessibility/assemble) |
| Unlock | Batch, single or per-file passwords, authorization checkbox and digital-signature warnings |

**Also**: create blank PDFs (paper / orientation / page count / background); bilingual UI (Help → Settings).

### Install & Run

Requires Python 3.10+ (developed on 3.13) and Windows 10/11 (system CJK fonts are used for signatures and font choices).

```bash
pip install -r requirements.txt
python run.py            # or: python run.py some.pdf
```

### Package as a single exe

```bash
python -m PyInstaller QudoPDF.spec --noconfirm
# output: dist/QudoPDF.exe
```

- `QUDOPDF_CONSOLE=1` builds a console variant for startup debugging
- `QUDOPDF_ONEDIR=1` builds a folder variant (faster startup)
- `QUDOPDF_SELFTEST=2500 dist/QudoPDF.exe` makes the app self-check and quit (useful for CI)

### Tests

```bash
python _test_engines.py   # engine-level functional tests
python _smoke.py          # construct every tool UI offscreen
python _e2e.py            # drive 20+ tools offscreen (24 assertions)
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
    │   ├── worker.py       # thread-pool tasks with progress + cancel
    │   ├── pagerange.py    # "1-3,5,8-" range parsing
    │   └── ops/            # UI-free engines: pages/crop/extract/redact/
    │                       # stamp/annotate/security/compress/convert/edit
    └── ui/
        ├── mainwindow.py   # menus / two-row toolbar / docks / status bar
        ├── viewer.py       # continuous viewer + background render thread
        ├── thumbnails.py   # thumbnail sidebar
        ├── outline.py      # bookmark tree
        ├── icons.py        # runtime-drawn vector icons (no external assets)
        ├── i18n.py         # zh/en map + recursive retranslation
        ├── dialogmodules.py# static import table (PyInstaller relies on it)
        └── dialogs/        # 21 tool dialogs / interactive panels
```

### License

This project depends on **PyMuPDF (AGPL-3.0)** and **pdf2docx (AGPL-3.0)**, so the repository is released under **AGPL-3.0**. For closed-source commercial distribution, purchase a commercial PyMuPDF license from Artifex and remove the AGPL dependencies. Other dependencies: PySide6 (LGPL), openpyxl (MIT), python-docx (MIT), Pillow (MIT), numpy (BSD).

### Known limitations

- No OCR (scanned documents need OCR before text extraction / Word export)
- Existing page content can be moved / re-typed / deleted but not resized or rotated (floating elements can)
- Edited or inserted text is rewritten with standard or system fonts; glyph details may differ from the original embedded font
- Vector graphics (lines / shapes) cannot yet be moved as a whole
