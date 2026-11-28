"""最近打开过的 PDF 文件列表。"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QSettings, Signal
from PySide6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QMenu, QStackedLayout, QVBoxLayout, QWidget

from . import i18n


class HistoryPanel(QWidget):
    openRequested = Signal(str)
    MAX_ITEMS = 20
    SETTINGS_KEY = "recentPdfFiles"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paths = self._load_paths()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._stack = QStackedLayout()
        layout.addLayout(self._stack)
        self._empty = QLabel("最近打开的 PDF 会显示在这里")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
        self._stack.addWidget(self._empty)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._open_item)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_menu)
        self._stack.addWidget(self._list)
        self.refresh()

    @classmethod
    def _load_paths(cls) -> list[str]:
        raw = QSettings().value(cls.SETTINGS_KEY, [], type=list)
        paths = []
        seen = set()
        for path in raw:
            if not isinstance(path, str) or not path.strip():
                continue
            path = os.path.abspath(os.path.expanduser(path))
            key = os.path.normcase(path)
            if key not in seen:
                seen.add(key)
                paths.append(path)
        return paths[: cls.MAX_ITEMS]

    def remember(self, path: str) -> None:
        path = os.path.abspath(path)
        key = os.path.normcase(path)
        self._paths = [p for p in self._paths if os.path.normcase(p) != key]
        self._paths.insert(0, path)
        self._paths = self._paths[: self.MAX_ITEMS]
        self._save()
        self.refresh()

    def retranslate(self) -> None:
        self._empty.setText(i18n.translate("最近打开的 PDF 会显示在这里"))

    def refresh(self) -> None:
        self._list.clear()
        for path in self._paths:
            name = os.path.basename(path) or path
            if not os.path.isfile(path):
                name += f"（{i18n.translate('文件不存在')}）"
            item = QListWidgetItem(name)
            item.setToolTip(path)
            item.setData(Qt.UserRole, path)
            self._list.addItem(item)
        self._stack.setCurrentWidget(self._list if self._paths else self._empty)

    def _open_item(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        if path:
            self.openRequested.emit(path)

    def _show_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is not None:
            self._list.setCurrentItem(item)
        menu = QMenu(self)
        open_action = menu.addAction(i18n.translate("打开"))
        remove_action = menu.addAction(i18n.translate("从历史中移除"))
        open_action.setEnabled(item is not None)
        remove_action.setEnabled(item is not None)
        menu.addSeparator()
        clear_action = menu.addAction(i18n.translate("清空历史记录"))
        clear_action.setEnabled(bool(self._paths))
        chosen = menu.exec(self._list.mapToGlobal(pos))
        if chosen == open_action and item is not None:
            self._open_item(item)
        elif chosen == remove_action and item is not None:
            path = item.data(Qt.UserRole)
            key = os.path.normcase(path)
            self._paths = [p for p in self._paths if os.path.normcase(p) != key]
            self._save()
            self.refresh()
        elif chosen == clear_action:
            self._paths.clear()
            self._save()
            self.refresh()

    def _save(self) -> None:
        QSettings().setValue(self.SETTINGS_KEY, self._paths)
