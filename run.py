"""启动脚本：python run.py [file.pdf]

打包单文件 exe：
    python -m PyInstaller QudoPDF.spec --noconfirm
产物在 dist/QudoPDF.exe。设置 QUDOPDF_SELFTEST=<毫秒> 可让应用自检后自动退出。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_toolbox.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
