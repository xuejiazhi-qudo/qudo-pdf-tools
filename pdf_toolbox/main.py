"""应用入口。"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from . import APP_NAME, ORG_NAME, __version__
from .ui.mainwindow import MainWindow
from .ui.theme import APP_STYLE


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    bundle_root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    app_icon = os.path.join(bundle_root, "QudoPDF.ico")
    if os.path.isfile(app_icon):
        app.setWindowIcon(QIcon(app_icon))
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(APP_STYLE)

    window = MainWindow()
    window.show()

    if len(argv) > 1 and argv[1].lower().endswith(".pdf"):
        window.open_file(argv[1])

    selftest = os.environ.get("QUDOPDF_SELFTEST")
    tools_ok = -1
    tools_err = ""
    if selftest:
        from PySide6.QtCore import QTimer

        from .ui import dialogmodules, toolregistry

        modules = dialogmodules.all_modules()
        total = len(modules)
        tools_ok = 0
        for key, module in modules.items():
            try:
                widget = (
                    module.create_panel(window, window.doc, window.view)
                    if toolregistry.TOOL_MAP[key].kind == "mode"
                    else module.create(window, window.doc)
                )
                widget.deleteLater()
                tools_ok += 1
            except Exception as exc:  # noqa: BLE001
                tools_err = tools_err or f"{key}: {exc}"
        app.processEvents()
        QTimer.singleShot(int(selftest), app.quit)

    code = app.exec()
    if selftest:
        print(f"QUDOPDF_SELFTEST_OK pages={window.doc.page_count} tools={tools_ok}/{total} err={tools_err}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
