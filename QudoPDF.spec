# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 exe。

构建：python -m PyInstaller QudoPDF.spec --noconfirm
产物：dist/QudoPDF.exe
"""

from PyInstaller.utils.hooks import collect_all

import os

CONSOLE = os.environ.get("QUDOPDF_CONSOLE") == "1"
ONEDIR = os.environ.get("QUDOPDF_ONEDIR") == "1"

datas = []
binaries = []
hiddenimports = []

# 这些包带二进制/数据文件/动态子模块，静态分析抓不全，整包收集
for pkg in ("pymupdf", "fitz", "docx", "pymupdf4llm", "openpyxl"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] skip {pkg}: {exc}")

# Qt 中文界面不需要 WebEngine/Sql 等，排除以减小体积
excludes = [
    "cv2",
    "onnxruntime",
    "networkx",
    "protobuf",
    "flatbuffers",
    "pdf2docx",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtPositioning",
    "PySide6.QtSql",
    "PySide6.QtXml",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtMultimedia",
    "PySide6.QtNetwork",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtWebSockets",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "tkinter",
    "matplotlib",
    "scipy",
    "pandas",
    "pytest",
]

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEDIR:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="QudoPDF",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="QudoPDF",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="QudoPDF",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=CONSOLE,        # QUDOPDF_CONSOLE=1 时带控制台，便于排查启动问题
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
