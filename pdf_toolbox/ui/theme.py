"""全局样式：深色中性界面 + 强调色。"""

APP_STYLE = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog { background: #f4f5f7; }
QToolBar {
    background: #ffffff;
    border-bottom: 1px solid #dcdfe4;
    spacing: 4px;
    padding: 4px;
}
QToolBar QToolButton {
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 5px 8px;
    background: transparent;
}
QToolBar QToolButton:hover { background: #eef1f5; }
QToolBar QToolButton:pressed { background: #e0e5ec; }
QToolBar QToolButton:checked { background: #dce8fb; border: 1px solid #7aa7e8; }
QToolBar QToolButton:disabled { color: #a8adb5; }
QMenuBar { background: #ffffff; border-bottom: 1px solid #dcdfe4; }
QMenuBar::item:selected { background: #eef1f5; }
QMenu { background: #ffffff; border: 1px solid #d5d9df; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 20px; border-radius: 4px; }
QMenu::item:selected { background: #e8eef8; }
QMenu::separator { height: 1px; background: #e2e5ea; margin: 4px 8px; }
QStatusBar { background: #ffffff; border-top: 1px solid #dcdfe4; }
QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QTextEdit, QSpinBox,
QDoubleSpinBox, QComboBox, QLineEdit {
    background: #ffffff;
    border: 1px solid #d5d9df;
    border-radius: 5px;
    padding: 3px;
    selection-background-color: #cfe1fa;
}
QListWidget::item { padding: 4px; }
QListWidget::item:selected { background: #cfe1fa; color: #101418; }
QPushButton {
    background: #ffffff;
    border: 1px solid #c9ced6;
    border-radius: 5px;
    padding: 6px 14px;
}
QPushButton:hover { background: #f0f3f7; }
QPushButton:pressed { background: #e2e7ee; }
QPushButton:checked {
    background: #2f6fd0;
    border: 1px solid #24549c;
    color: #ffffff;
    font-weight: 600;
}
QPushButton:checked:hover { background: #2a63ba; }
QPushButton:disabled { color: #a8adb5; background: #f2f3f5; }
QPushButton[primary="true"] {
    background: #2f6fd0;
    border: 1px solid #2f6fd0;
    color: #ffffff;
    font-weight: 600;
}
QPushButton[primary="true"]:hover { background: #2a63ba; }
QPushButton[primary="true"]:disabled { background: #9db8e0; border-color: #9db8e0; }
QPushButton[danger="true"] {
    background: #ffffff;
    border: 1px solid #d8a0a0;
    color: #b3372f;
}
QPushButton[danger="true"]:hover { background: #fbeeee; }
QGroupBox {
    border: 1px solid #d5d9df;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
QTabWidget::pane { border: 1px solid #d5d9df; border-radius: 4px; background: #ffffff; }
QTabBar::tab {
    background: #eef0f3;
    border: 1px solid #d5d9df;
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}
QTabBar::tab:selected { background: #ffffff; border-bottom-color: #ffffff; }
QSlider::groove:horizontal { height: 5px; background: #d8dce2; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; margin: -5px 0; border-radius: 7px; background: #2f6fd0;
}
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QProgressBar {
    border: 1px solid #d5d9df; border-radius: 5px; background: #eef0f3;
    text-align: center; height: 18px;
}
QProgressBar::chunk { background: #2f6fd0; border-radius: 4px; }
QSplitter::handle { background: #dcdfe4; width: 1px; }
QGraphicsView { border: none; background: #525659; }
QScrollArea { border: none; }
QToolTip { background: #2b2f36; color: #f2f4f7; border: none; padding: 4px 8px; }
"""


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"
