"""主窗口：菜单、工具栏、查看器、缩略图与工具调度。"""

from __future__ import annotations

import importlib
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QSize, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QToolBar,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core.doc import PasswordRequiredError, PdfDoc, WrongPasswordError
from . import dialogmodules
from . import toolregistry as reg
from . import icons
from . import i18n
from .history import HistoryPanel
from .outline import OutlinePanel
from .theme import human_size
from .thumbnails import ThumbnailPanel
from .viewer import PdfView


def _delete_registry_tree(winreg, root, subkey: str) -> None:
    """Delete a registry key and its children, ignoring an absent key."""
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as key:
            while True:
                try:
                    child = winreg.EnumKey(key, 0)
                except OSError:
                    break
                _delete_registry_tree(winreg, root, subkey + "\\" + child)
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        return


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 880)

        self.doc = PdfDoc(self)
        self._mode_panels = {}

        self.view = PdfView(self.doc, self)
        self.view.fileDropped.connect(self.open_file)
        self.setCentralWidget(self.view)

        self.thumbs = ThumbnailPanel(self.doc, self)
        self.outline = OutlinePanel(self.doc, self)
        self.history = HistoryPanel(self)

        self._side_tabs = QTabWidget()
        self._side_tabs.addTab(self.outline, "目录")
        self._side_tabs.addTab(self.thumbs, "页面")
        self._side_tabs.addTab(self.history, "历史")
        self._side_tabs.setTabIcon(0, icons.icon("outline", 16))
        self._side_tabs.setTabIcon(1, icons.icon("pages", 16))
        self._side_tabs.setTabIcon(2, icons.icon("open", 16))

        dock = QDockWidget("导航", self)
        dock.setWidget(self._side_tabs)
        dock.setObjectName("navDock")
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._thumb_dock = dock

        self.outline.gotoPage.connect(self.view.goto_page)
        self.history.openRequested.connect(self._open_path)
        self.view.currentPageChanged.connect(self.outline.set_current)
        self.doc.structureChanged.connect(self._select_side_tab)

        self.thumbs.currentChanged.connect(self.view.goto_page)
        self.view.currentPageChanged.connect(self.thumbs.set_current)
        self.view.currentPageChanged.connect(self._update_status)
        self.view.zoomChanged.connect(self._update_status)
        self.doc.dirtyChanged.connect(self._update_title)
        self.doc.titleChanged.connect(self._update_title)
        self.doc.structureChanged.connect(self._update_status)

        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        i18n.retranslate_widget(self)
        self._update_title()
        self._update_status()

    # ---------------------------------------------------------------- 菜单

    def _build_menus(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("文件(&F)")
        self.act_new = file_menu.addAction(
            icons.icon("new"), "新建", self.new_pdf, QKeySequence.New
        )
        self.act_open = file_menu.addAction(icons.icon("open"), "打开(&O)…", self.open_file, QKeySequence.Open)
        file_menu.addAction("注册 PDF 右键打开", self.register_pdf_context_menu)
        file_menu.addAction("移除 PDF 右键菜单", self.unregister_pdf_context_menu)
        file_menu.addAction("重新打开", self.reopen)
        file_menu.addSeparator()
        self.act_save = file_menu.addAction(icons.icon("save"), "保存(&S)", self.save, QKeySequence.Save)
        self.act_save_as = file_menu.addAction("另存为…", self.save_as, QKeySequence.SaveAs)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close, QKeySequence.Quit)

        edit_menu = mb.addMenu("编辑(&E)")
        self.act_undo = edit_menu.addAction(icons.icon("undo"), "撤销", self.undo, QKeySequence.Undo)
        self.act_redo = edit_menu.addAction(icons.icon("redo"), "重做", self.redo, QKeySequence.Redo)

        view_menu = mb.addMenu("视图(&V)")
        view_menu.addAction(icons.icon("zoom_in"), "放大", self.view.zoom_in, QKeySequence.ZoomIn)
        view_menu.addAction(icons.icon("zoom_out"), "缩小", self.view.zoom_out, QKeySequence.ZoomOut)
        view_menu.addAction(icons.icon("fit_width"), "适应宽度", self.view.fit_width)
        view_menu.addAction(icons.icon("fit_page"), "适应页面", self.view.fit_page)
        view_menu.addSeparator()
        view_menu.addAction(self._thumb_dock.toggleViewAction())

        tools_menu = mb.addMenu("工具(&T)")
        for group in reg.GROUP_ORDER:
            sub = tools_menu.addMenu(group)
            for tool in reg.TOOLS:
                if tool.group != group:
                    continue
                action = sub.addAction(icons.icon(tool.key), f"{tool.name}　{tool.desc}")
                action.setToolTip(tool.desc)
                action.triggered.connect(lambda _=False, k=tool.key: self.run_tool(k))

        help_menu = mb.addMenu("帮助(&H)")
        help_menu.addAction(icons.icon("outline"), "设置", self.open_settings)
        help_menu.addAction("关于", self.about)

    def open_settings(self) -> None:
        dialog = i18n.SettingsDialog(self, on_changed=self._apply_language)
        dialog.exec()

    def _apply_language(self) -> None:
        i18n.retranslate_widget(self)
        self.history.refresh()
        self._update_status()
        self._update_title()

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏", self)
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        tb.addAction(self.act_new)
        tb.addAction(self.act_open)
        tb.addAction(self.act_save)
        tb.addSeparator()
        tb.addAction(self.act_undo)
        tb.addAction(self.act_redo)
        tb.addSeparator()

        tb.addAction(icons.icon("zoom_out"), "−", self.view.zoom_out).setToolTip("缩小")
        self._zoom_label = QLabel("100%")
        self._zoom_label.setMinimumWidth(48)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        tb.addWidget(self._zoom_label)
        tb.addAction(icons.icon("zoom_in"), "＋", self.view.zoom_in).setToolTip("放大")
        tb.addAction(icons.icon("fit_width"), "适应宽度", self.view.fit_width)
        tb.addAction(icons.icon("fit_page"), "适应页面", self.view.fit_page)
        tb.addSeparator()

        tb.addAction(icons.icon("prev"), "上一页", lambda: self.view.goto_page(self.view.current_page - 1))
        self._page_spin = QSpinBox()
        self._page_spin.setMinimum(1)
        self._page_spin.setMaximum(1)
        self._page_spin.valueChanged.connect(lambda v: self.view.goto_page(v - 1))
        tb.addWidget(self._page_spin)
        self._page_total = QLabel("/ 0")
        tb.addWidget(self._page_total)
        tb.addAction(icons.icon("next"), "下一页", lambda: self.view.goto_page(self.view.current_page + 1))

        spacer = QWidget(tb)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)
        tb.addAction(
            icons.icon("website"), "www.qudo.cc",
            lambda: QDesktopServices.openUrl(QUrl("https://www.qudo.cc")),
        ).setToolTip("打开作者网站")
        tb.addAction(
            icons.icon("email"), "xuejiazhi@gmail.com",
            lambda: QDesktopServices.openUrl(QUrl("mailto:xuejiazhi@gmail.com")),
        ).setToolTip("给作者发送邮件")

        # 第二行：全部工具的快捷按钮（独占一行）
        self._mode_actions = {}
        self.addToolBarBreak()
        tb2 = QToolBar("工具", self)
        tb2.setMovable(False)
        tb2.setIconSize(QSize(22, 22))
        tb2.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(tb2)

        for group in reg.GROUP_ORDER:
            first = True
            for tool in reg.TOOLS:
                if tool.group != group:
                    continue
                if first:
                    if group != reg.GROUP_ORDER[0]:
                        tb2.addSeparator()
                    first = False
                action = tb2.addAction(
                    icons.icon(tool.key),
                    reg.SHORT_LABELS.get(tool.key, tool.name),
                    lambda _=False, k=tool.key: self.run_tool(k),
                )
                action.setToolTip(f"{tool.name}：{tool.desc}")
                if tool.kind == "mode":
                    action.setCheckable(True)
                    self._mode_actions[tool.key] = action

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self._status_page = QLabel("")
        self._status_zoom = QLabel("")
        self._status_file = QLabel("")
        sb.addWidget(self._status_page, 1)
        sb.addWidget(self._status_zoom)
        sb.addPermanentWidget(self._status_file)

    # ---------------------------------------------------------------- 状态

    def _update_title(self, *_args) -> None:
        title = APP_NAME
        if self.doc.is_open:
            mark = " *" if self.doc.dirty else ""
            title = f"{self.doc.title}{mark} - {APP_NAME}"
        self.setWindowTitle(title)
        has = self.doc.is_open
        for act in (self.act_save, self.act_save_as, self.act_undo, self.act_redo):
            act.setEnabled(has)
        self.act_undo.setEnabled(has and self.doc.can_undo)
        self.act_redo.setEnabled(has and self.doc.can_redo)

    def _select_side_tab(self, *_args) -> None:
        if self._side_tabs.currentIndex() in (0, 1):
            self._side_tabs.setCurrentIndex(0 if self.outline.has_outline else 1)

    def _update_status(self, *_args) -> None:
        n = self.doc.page_count
        self._page_spin.setMaximum(max(1, n))
        self._page_spin.blockSignals(True)
        self._page_spin.setValue(min(self.view.current_page + 1, max(1, n)))
        self._page_spin.blockSignals(False)
        self._page_total.setText(f"/ {n}")
        self._zoom_label.setText(f"{self.view.zoom * 100:.0f}%")
        self._status_page.setText(
            i18n.translate(f"第 {min(self.view.current_page + 1, n) if n else 0} / {n} 页")
        )
        self._status_zoom.setText(i18n.translate(f"缩放 {self.view.zoom * 100:.0f}%"))
        if self.doc.is_open and self.doc.path:
            try:
                size = os.path.getsize(self.doc.path)
                self._status_file.setText(f"{self.doc.path}　{human_size(size)}")
            except OSError:
                self._status_file.setText(self.doc.path)
        else:
            self._status_file.setText("")

    # ---------------------------------------------------------------- 文件

    def new_pdf(self) -> None:
        try:
            dialog = dialogmodules.DIALOG_MODULES["new_pdf"].create(self, self.doc)
        except Exception as exc:  # noqa: BLE001
            self._show_tool_error("新建 PDF", exc)
            return
        dialog.exec()
        self._update_title()
        self._update_status()

    def open_file(self, path: Optional[str] = None) -> bool:
        path = path or QFileDialog.getOpenFileName(
            self, "打开 PDF", "", "PDF 文件 (*.pdf);;所有文件 (*)"
        )[0]
        if not path:
            return False
        return self._open_path(path)

    def _open_path(self, path: str, password: Optional[str] = None) -> bool:
        try:
            self.doc.open(path, password)
        except PasswordRequiredError:
            password, ok = QInputDialog.getText(
                self, i18n.translate("需要密码"),
                i18n.translate(f"《{os.path.basename(path)}》已加密，请输入打开密码："),
                echo=QInputDialog.Password,
            )
            if not ok:
                return False
            return self._open_path(path, password)
        except WrongPasswordError:
            QMessageBox.warning(self, i18n.translate("密码错误"), i18n.translate("输入的密码不正确。"))
            return self._open_path(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, i18n.translate("打开失败"), str(exc))
            return False

        self.view.set_zoom(1.0)
        self.view.fit_width()
        self.history.remember(path)
        return True

    def reopen(self) -> None:
        if self.doc.path:
            self._open_path(self.doc.path)

    def register_pdf_context_menu(self) -> None:
        """Register direct and Open with verbs for PDFs for this Windows user."""
        try:
            import subprocess
            import winreg
            import ctypes

            if getattr(sys, "frozen", False):
                command = subprocess.list2cmdline([sys.executable, "%1"])
                icon_path = sys.executable
                app_id = os.path.basename(sys.executable)
            else:
                command = subprocess.list2cmdline(
                    [sys.executable, os.path.abspath(sys.argv[0]), "%1"]
                )
                icon_path = os.path.abspath(sys.argv[0])
                app_id = "QudoPDF-dev.exe"

            key_path = r"Software\Classes\SystemFileAssociations\.pdf\shell\QudoPDF"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                winreg.SetValueEx(key, "MUIVerb", 0, winreg.REG_SZ, "使用 QudoPDF 打开")
                winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, icon_path)
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command") as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)

            # Also advertise the app through Windows' standard "Open with" list.
            app_key = rf"Software\Classes\Applications\{app_id}"
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, app_key + r"\shell\open\command"
            ) as key:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
            with winreg.CreateKey(
                winreg.HKEY_CURRENT_USER, app_key + r"\SupportedTypes"
            ) as key:
                winreg.SetValueEx(key, ".pdf", 0, winreg.REG_SZ, "")
            # Tell Explorer to refresh its cached file-association data.
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        except (ImportError, OSError) as exc:
            QMessageBox.warning(self, i18n.translate("注册失败"), str(exc))
            return
        QMessageBox.information(
            self, i18n.translate("注册完成"),
            i18n.translate("现在可以在 PDF 文件上右键，选择“使用 QudoPDF 打开”。"),
        )

    def unregister_pdf_context_menu(self) -> None:
        """Remove QudoPDF's current-user direct and Open with registrations."""
        try:
            import winreg
            import ctypes

            key_path = r"Software\Classes\SystemFileAssociations\.pdf\shell\QudoPDF"
            app_id = (
                os.path.basename(sys.executable)
                if getattr(sys, "frozen", False)
                else "QudoPDF-dev.exe"
            )
            _delete_registry_tree(winreg, winreg.HKEY_CURRENT_USER, key_path)
            _delete_registry_tree(
                winreg,
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\Applications\{app_id}",
            )
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        except FileNotFoundError:
            QMessageBox.information(self, i18n.translate("未注册"), i18n.translate("未找到 QudoPDF 的右键菜单项。"))
            return
        except (ImportError, OSError) as exc:
            QMessageBox.warning(self, i18n.translate("移除失败"), str(exc))
            return
        QMessageBox.information(self, i18n.translate("已移除"), i18n.translate("QudoPDF 右键菜单项已移除。"))

    def _apply_pending_elements(self) -> None:
        for _key, (panel, _dock) in list(self._mode_panels.items()):
            apply_fn = getattr(panel, "apply_pending", None)
            if apply_fn is not None:
                apply_fn()

    def save(self) -> bool:
        if not self.doc.is_open:
            return False
        self._apply_pending_elements()
        if not self.doc.path:
            return self.save_as()
        try:
            self.doc.save()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, i18n.translate("保存失败"), str(exc))
            return False
        return True

    def save_as(self) -> bool:
        if not self.doc.is_open:
            return False
        self._apply_pending_elements()
        path = QFileDialog.getSaveFileName(
            self, "另存为", self.doc.path or "output.pdf", "PDF 文件 (*.pdf)"
        )[0]
        if not path:
            return False
        try:
            self.doc.save(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, i18n.translate("保存失败"), str(exc))
            return False
        return True

    def undo(self) -> None:
        if self.doc.undo():
            self._update_title()

    def redo(self) -> None:
        if self.doc.redo():
            self._update_title()

    def about(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(i18n.translate(f"关于 {APP_NAME}"))
        box.setIcon(QMessageBox.Information)
        box.setStandardButtons(QMessageBox.Ok)
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.setText(
            f"<p>{APP_NAME} v{__version__}</p>"
            f"<p>{i18n.translate('基于 PySide6 与 PyMuPDF 的离线 PDF 工具集，全部处理在本地完成，')}"
            f"{i18n.translate('不上传任何文件。')}</p>"
            f"<p>{i18n.translate('包含合并、拆分、压缩、加密、涂销、标注、')}"
            f"{i18n.translate('水印、印章、页码、填写签名、转 Word/Excel 等 22 项功能。')}</p>"
            f"<p>{i18n.translate('作者网站：')}<a href=\"https://www.qudo.cc\">https://www.qudo.cc</a><br>"
            f"{i18n.translate('作者邮箱：')}<a href=\"mailto:xuejiazhi@gmail.com\">xuejiazhi@gmail.com</a></p>"
        )
        label = box.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setOpenExternalLinks(True)
        box.exec()

    # ---------------------------------------------------------------- 工具调度

    def run_tool(self, key: str) -> None:
        tool = reg.TOOL_MAP[key]
        if tool.needs_doc and not self.doc.is_open:
            QMessageBox.information(self, i18n.translate("请先打开文件"), i18n.translate("该工具需要先打开一个 PDF 文件。"))
            return

        if tool.kind == "mode":
            self._toggle_mode(key)
            return

        try:
            module = dialogmodules.DIALOG_MODULES[key]
            dialog = module.create(self, self.doc)
        except Exception as exc:  # noqa: BLE001
            self._show_tool_error(tool.name, exc)
            return
        dialog.exec()
        self._update_title()
        self._update_status()

    def _show_tool_error(self, name: str, exc: BaseException) -> None:
        import traceback

        detail = traceback.format_exc(limit=6)
        QMessageBox.critical(self, i18n.translate(f"{name}：无法打开"), f"{exc}\n\n{detail}")

    def _toggle_mode(self, key: str) -> None:
        action = getattr(self, "_mode_actions", {}).get(key)
        if action is None:
            return

        # 先关掉其它模式
        for other_key, panel in list(self._mode_panels.items()):
            if other_key != key:
                self._close_mode(other_key)

        if key in self._mode_panels:
            self._close_mode(key)
            return

        try:
            module = dialogmodules.PANEL_MODULES[key]
            panel = module.create_panel(self, self.doc, self.view)
        except Exception as exc:  # noqa: BLE001
            self._show_tool_error(reg.TOOL_MAP[key].name, exc)
            return
        dock = QDockWidget(reg.TOOL_MAP[key].name, self)
        dock.setWidget(panel)
        dock.setObjectName(f"mode_{key}")
        dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        # 注意：QDockWidget 没有 closed 信号，只能用 visibilityChanged
        dock.visibilityChanged.connect(
            lambda visible, k=key: self._on_mode_dock_visibility(k, visible)
        )
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self._mode_panels[key] = (panel, dock)
        if action is not None:
            action.setChecked(True)
        i18n.retranslate_widget(panel)
        i18n.retranslate_widget(dock)
        panel.activate()

    def _on_mode_dock_visibility(self, key: str, visible: bool) -> None:
        if not visible and key in self._mode_panels:
            self._close_mode(key)

    def _close_mode(self, key: str) -> None:
        entry = self._mode_panels.pop(key, None)
        if entry is None:
            return
        panel, dock = entry
        panel.deactivate()
        dock.close()
        dock.deleteLater()
        action = getattr(self, "_mode_actions", {}).get(key)
        if action is not None:
            action.setChecked(False)

    # ---------------------------------------------------------------- 关闭

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self.doc.dirty:
            ret = QMessageBox.question(
                self,
                i18n.translate("有未保存的修改"),
                i18n.translate("当前文档有未保存的修改，是否保存？"),
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if ret == QMessageBox.Cancel:
                event.ignore()
                return
            if ret == QMessageBox.Save and not self.save():
                event.ignore()
                return
        for key in list(self._mode_panels):
            self._close_mode(key)
        self.view.close()
        self.thumbs.close()
        event.accept()
