"""离屏冒烟测试：构建主窗口并逐个实例化所有对话框，捕获导入/构造错误。"""

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from pdf_toolbox.ui.mainwindow import MainWindow
from pdf_toolbox.ui import toolregistry as reg

FAIL = []


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # 打开一个测试文档
    fx = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test-fixtures", "extract-text-test.pdf"))
    ok = win.open_file(fx)
    print("open:", ok, "pages:", win.doc.page_count)

    import importlib

    for tool in reg.TOOLS:
        try:
            module = importlib.import_module(f"pdf_toolbox.ui.dialogs.{tool.dialog}")
            if tool.kind == "dialog":
                dlg = module.create(win, win.doc)
                dlg.deleteLater()
                print(f"  [dialog] {tool.key:14s} OK")
            else:
                panel = module.create_panel(win, win.doc, win.view)
                panel.deleteLater()
                print(f"  [panel ] {tool.key:14s} OK")
        except Exception as exc:  # noqa: BLE001
            FAIL.append((tool.key, traceback.format_exc(limit=4)))
            print(f"  [FAIL  ] {tool.key:14s} {exc}")

    QTimer.singleShot(300, app.quit)
    app.exec()

    if FAIL:
        print("\n=== FAILURES ===")
        for key, tb in FAIL:
            print(f"--- {key} ---\n{tb}")
        return 1
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
