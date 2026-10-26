"""
Desktop launcher window - Lista tekstów / polsoft.ITS.

A standalone module for the "Desktop" window opened by the left-hand button
(Desktop.png icon) in the main window's button bar.

The window is a launcher: it holds a list of applications/scripts that the
user adds through the context menu ("Dodaj" / "Add"). Each entry can have a
custom name and icon; when no icon is picked, the file's own icon is used.
Entries can be shown either as a list or as a grid of icons.

Author: Sebastian Januchowski / polsoft.ITS Group
"""

import os
import sys

from PyQt6.QtCore import Qt, QFileInfo, QSize
from PyQt6.QtGui import QIcon, QAction, QCursor
from PyQt6.QtWidgets import (
    QDialog, QFrame, QLabel, QLineEdit, QPushButton, QFileDialog,
    QVBoxLayout, QHBoxLayout, QFormLayout, QListWidget, QListWidgetItem,
    QListView, QMenu, QStackedWidget, QToolButton,
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def launcher_entries_file():
    # Return the path of the persisted launcher entries file."
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "desktop_launcher_data.json")


def load_launcher_entries():
    # Load launcher entries for clients that need a lightweight menu."
    try:
        import json
        with open(launcher_entries_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            continue
        name = entry.get("name")
        icon_path = entry.get("icon_path")
        entries.append({
            "path": path,
            "name": name if isinstance(name, str) and name else os.path.basename(path),
            "icon_path": icon_path if isinstance(icon_path, str) and icon_path else None,
            "is_dir": bool(entry.get("is_dir")),
        })
    return entries


def _open_with_os(path):
    # Open a file, application or folder with the operating system.
    if not path:
        return
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(path)  # Windows
        except OSError:
            print(f"Nie udało się otworzyć: {path}", file=sys.stderr)
        return

    import subprocess
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.Popen([opener, path])
    except OSError:
        print(f"Nie udało się otworzyć: {path}", file=sys.stderr)


def launch_path(path):
    # Open an application, script, or directory with the operating system."
    if not path or not os.path.exists(path):
        return
    _open_with_os(path)


def native_file_icon(path):
    """Return the OS-provided icon for `path`, or an empty icon.

    This is the "original icon of the file" used when the user does not pick
    a custom icon.
    """
    # QFileIconProvider returns the real shell icon on Windows.
    try:
        from PyQt6.QtWidgets import QFileIconProvider
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(path))
        if icon is not None and not icon.isNull():
            return icon
    except Exception:
        pass

    # Fallback: let QIcon try to load the file itself (works for .png/.ico).
    icon = QIcon(path)
    if not icon.isNull():
        return icon

    return QIcon()


def _format_size(size):
    """Return a human-readable file size string."""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} kB"
    return f"{size} B"


def _describe_type(path):
    """Return the human-readable type label for the properties dialog."""
    if os.path.isdir(path):
        return "Katalog"
    if not os.path.exists(path):
        return "Nieznany"
    extension = os.path.splitext(path)[1].lstrip(".").upper()
    return f"{extension} - plik" if extension else "Plik"


def _properties_info_rows(path, name):
    """Return a list of (label, value) detail rows for the properties dialog."""
    rows = []
    exists = os.path.exists(path)
    is_dir = os.path.isdir(path)
    rows.append(("Nazwa:", name or os.path.basename(path)))
    rows.append(("Typ:", _describe_type(path)))
    rows.append(("Lokalizacja:", path if is_dir else os.path.dirname(path)))
    if exists and not is_dir:
        try:
            import datetime
            mtime = os.path.getmtime(path)
            rows.append(("Rozmiar:", _format_size(os.path.getsize(path))))
            rows.append(("Zmodyfikowano:",
                         datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")))
        except OSError:
            pass
    if not exists:
        rows.append(("Stan:", "⚠ Plik nie istnieje (przeniesiony lub usunięty)"))
    return rows


def _escape_html(value):
    """Escape characters that would otherwise break the HTML markup."""
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def properties_html(path, name):
    """Build the HTML body shown in the properties dialog."""
    lines = [
        f"<b>{label}</b><br>{_escape_html(value)}<br>"
        for label, value in _properties_info_rows(path, name)
    ]
    return "<div>" + "<hr>".join(lines) + "</div>"


# ----------------------------------------------------------------------
# "Add application" dialog
# ----------------------------------------------------------------------
class AddAppDialog(QDialog):
    """Let the user pick an app/script and personalise name and icon.

    Fields:
        path  - the executable/script file chosen
        name  - display name (defaults to the file name without extension)
        icon  - custom icon path, or None to use the file's own icon
    """

    def __init__(self, stylesheet="", base_dir="", parent=None, is_directory=False):
        super().__init__(parent)
        self.setWindowTitle("Dodaj katalog" if is_directory else "Dodaj aplikację")
        if stylesheet:
            self.setStyleSheet(stylesheet)
        self.setMinimumWidth(440)

        self._icon_path = None
        self._path = None
        self._base_dir = base_dir
        self._is_directory = is_directory

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # --- File row -------------------------------------------------
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("Nie wybrano pliku")
        path_row.addWidget(self.path_edit, 1)
        browse_btn = QPushButton("Przeglądaj...")
        browse_btn.setObjectName("neutralBtn")
        browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        browse_btn.clicked.connect(self._browse_file)
        path_row.addWidget(browse_btn)
        form.addRow("Katalog:" if is_directory else "Aplikacja / skrypt:", path_row)

        # --- Name -----------------------------------------------------
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Nazwa (domyślnie nazwa pliku)")
        form.addRow("Nazwa:", self.name_edit)

        # --- Icon row -------------------------------------------------
        icon_row = QHBoxLayout()
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(28, 28)
        icon_row.addWidget(self.icon_preview)
        self.icon_edit = QLineEdit()
        self.icon_edit.setReadOnly(True)
        self.icon_edit.setPlaceholderText("Domyślna ikona pliku")
        icon_row.addWidget(self.icon_edit, 1)
        icon_btn = QPushButton("Zmień...")
        icon_btn.setObjectName("neutralBtn")
        icon_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        icon_btn.clicked.connect(self._browse_icon)
        icon_row.addWidget(icon_btn)
        reset_icon_btn = QPushButton("Domyślna")
        reset_icon_btn.setObjectName("neutralBtn")
        reset_icon_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        reset_icon_btn.clicked.connect(self._reset_icon)
        icon_row.addWidget(reset_icon_btn)
        form.addRow("Ikona:", icon_row)

        root.addLayout(form)
        root.addStretch(1)

        # --- Buttons --------------------------------------------------
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        cancel_btn = QPushButton("Anuluj")
        cancel_btn.setObjectName("neutralBtn")
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        add_btn = QPushButton("Dodaj")
        add_btn.setObjectName("accentBtn")
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.clicked.connect(self._accept)
        btn_row.addWidget(add_btn)
        root.addLayout(btn_row)

    # -- browsing ------------------------------------------------------
    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Wybierz aplikację lub skrypt", self._base_dir or "",
            "Programy i skrypty (*.exe *.bat *.cmd *.ps1 *.py *.pyw *.lnk *.sh);;"
            "Wszystkie pliki (*)",
        )
        if not path:
            return
        self._path = path
        self.path_edit.setText(path)
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])
        self._refresh_preview()

    def _browse_icon(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Wybierz ikonę", self._base_dir or "",
            "Obrazy (*.png *.ico *.jpg *.jpeg *.bmp *.svg);;Wszystkie pliki (*)",
        )
        if not path:
            return
        self._icon_path = path
        self.icon_edit.setText(path)
        self._refresh_preview()

    def _reset_icon(self):
        self._icon_path = None
        self.icon_edit.clear()
        self._refresh_preview()

    def _refresh_preview(self):
        icon = self.current_icon()
        if icon.isNull():
            self.icon_preview.clear()
        else:
            self.icon_preview.setPixmap(icon.pixmap(QSize(24, 24)))

    # -- data ----------------------------------------------------------
    def current_icon(self):
        """Icon to use: the custom one, or the file's own icon."""
        if self._icon_path and os.path.exists(self._icon_path):
            icon = QIcon(self._icon_path)
            if not icon.isNull():
                return icon
        if self._path:
            return native_file_icon(self._path)
        return QIcon()

    def _accept(self):
        if not self._path:
            return
        if not self.name_edit.text().strip():
            self.name_edit.setText(
                os.path.splitext(os.path.basename(self._path))[0]
            )
        self.accept()

    def result_entry(self):
        """Return the entry dict (path, name, icon_path) for the new item."""
        return {
            "path": self._path,
            "name": self.name_edit.text().strip(),
            "icon_path": self._icon_path,
            "is_dir": self._is_directory,
        }


# ----------------------------------------------------------------------
# Launcher window
# ----------------------------------------------------------------------
class DesktopLauncher(QDialog):
    """Launcher window shown by the Desktop.png button.

    Shows the added applications/scripts. Right-clicking opens a context menu
    with "Dodaj" (add). Entries can be viewed as a list or as a grid of icons.
    """

    TITLE = "Apps"
    LIST_VIEW = "list"
    ICON_VIEW = "icons"

    def __init__(self, stylesheet="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.TITLE)
        if stylesheet:
            self.setStyleSheet(stylesheet)
        self.setMinimumSize(520, 360)

        self._entries = []           # dicts: path, name, icon_path
        self._view_mode = self.ICON_VIEW
        self._load_entries()         # restore the saved launcher items

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # --- Top toolbar (view switch) --------------------------------
        toolbar = QHBoxLayout()
        toolbar.addStretch(1)

        self.list_btn = QToolButton()
        self.list_btn.setText("\u2630")          # ☰
        self.list_btn.setToolTip("Widok listy")
        self.list_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.list_btn.clicked.connect(lambda: self.set_view_mode(self.LIST_VIEW))
        toolbar.addWidget(self.list_btn)

        self.icons_btn = QToolButton()
        self.icons_btn.setText("\u25a6")         # ▦
        self.icons_btn.setToolTip("Widok ikon")
        self.icons_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.icons_btn.clicked.connect(lambda: self.set_view_mode(self.ICON_VIEW))
        toolbar.addWidget(self.icons_btn)
        root.addLayout(toolbar)

        # --- The two views in a stacked widget ------------------------
        self.stack = QStackedWidget()

        self.list_widget = QListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemActivated.connect(self._launch_item)
        self.list_widget.itemDoubleClicked.connect(self._launch_item)

        self.icon_widget = QListWidget()
        self.icon_widget.setViewMode(QListView.ViewMode.IconMode)
        self.icon_widget.setIconSize(QSize(48, 48))
        self.icon_widget.setGridSize(QSize(96, 96))
        self.icon_widget.setResizeMode(QListView.ResizeMode.Adjust)
        self.icon_widget.setMovement(QListView.Movement.Static)
        self.icon_widget.setWordWrap(True)
        self.icon_widget.setSpacing(8)
        self.icon_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.icon_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.icon_widget.itemActivated.connect(self._launch_item)
        self.icon_widget.itemDoubleClicked.connect(self._launch_item)

        self.stack.addWidget(self.list_widget)
        self.stack.addWidget(self.icon_widget)
        root.addWidget(self.stack, 1)

        self.set_view_mode(self.ICON_VIEW)

    # -- persistence -------------------------------------------------
    def _entries_file(self):
        """Path of the json file keeping the launcher items (next to the
        script, or next to the .exe when frozen with PyInstaller)."""
        return launcher_entries_file()

    def _load_entries(self):
        self._entries = load_launcher_entries()

    def _save_entries(self):
        try:
            import json
            with open(self._entries_file(), "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Zapis nieudany",
                "Nie udało się zapisać listy aplikacji:\n"
                f"{self._entries_file()}\n\n{exc}",
            )

    # -- view handling -------------------------------------------------
    def set_view_mode(self, mode):
        self._view_mode = mode
        if mode == self.LIST_VIEW:
            self.stack.setCurrentWidget(self.list_widget)
        else:
            self.stack.setCurrentWidget(self.icon_widget)
        self._refresh_views()

    def _refresh_views(self):
        """Rebuild both view widgets from self._entries."""
        for widget in (self.list_widget, self.icon_widget):
            widget.clear()
            for index, entry in enumerate(self._entries):
                item = QListWidgetItem(self._entry_icon(entry), entry["name"])
                item.setData(Qt.ItemDataRole.UserRole, entry["path"])
                item.setData(Qt.ItemDataRole.UserRole + 1, index)
                item.setToolTip(entry["path"])
                widget.addItem(item)

    def _entry_icon(self, entry):
        if entry.get("icon_path") and os.path.exists(entry["icon_path"]):
            icon = QIcon(entry["icon_path"])
            if not icon.isNull():
                return icon
        # Fallback: the file's own icon.
        return native_file_icon(entry["path"])

    # -- context menu --------------------------------------------------
    def _show_context_menu(self, pos):
        source = self.sender()
        menu = QMenu(self)

        add_action = QAction("Dodaj", self)
        add_action.triggered.connect(self.add_entry)
        menu.addAction(add_action)

        add_dir_action = QAction("Dodaj katalog", self)
        add_dir_action.triggered.connect(self.add_directory)
        menu.addAction(add_dir_action)

        item = source.itemAt(pos) if source is not None else None
        if item is not None and item.data(Qt.ItemDataRole.UserRole):
            launch_action = QAction("Uruchom", self)
            launch_action.triggered.connect(lambda: self._launch_item(item))
            menu.addAction(launch_action)

            open_folder_action = QAction("Otwórz folder", self)
            open_folder_action.triggered.connect(
                lambda: self._open_item_folder(item.data(Qt.ItemDataRole.UserRole))
            )
            menu.addAction(open_folder_action)

            props_action = QAction("Właściwości", self)
            props_action.triggered.connect(
                lambda: self._show_properties(item.data(Qt.ItemDataRole.UserRole),
                                              item.text())
            )
            menu.addAction(props_action)

            remove_action = QAction("Usuń", self)
            remove_action.triggered.connect(lambda: self._remove_item(item))
            menu.addAction(remove_action)

        if source is not None:
            menu.exec(source.mapToGlobal(pos))
        else:
            menu.exec(self.mapToGlobal(pos))

    # -- add / remove / launch -----------------------------------------
    def _default_base_dir(self):
        """Folder the file pickers should start in.

        Uses the last entry's folder, or the folder itself when the last
        entry is a directory.
        """
        if not self._entries:
            return ""
        last = self._entries[-1]
        return last["path"] if last.get("is_dir") else os.path.dirname(last["path"])

    def _prompt_and_add_entry(self, path=None, is_directory=False):
        """Open the add dialog and append the resulting entry.

        When ``path`` is given the dialog opens pre-filled with it (used by
        the "add folder" flow); ``is_directory`` marks the entry as a group.
        """
        base_dir = self._default_base_dir()
        dlg = AddAppDialog(
            stylesheet=self.styleSheet(), base_dir=base_dir, parent=self,
            is_directory=is_directory,
        )
        if path is not None:
            dlg._path = path
            dlg.path_edit.setText(path)
            dlg.name_edit.setText(os.path.basename(path.rstrip("/\\")))
            dlg._refresh_preview()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dlg.result_entry()
        if not entry["path"]:
            return
        if is_directory:
            entry["is_dir"] = True
        self._entries.append(entry)
        self._refresh_views()
        self._save_entries()

    def add_entry(self):
        self._prompt_and_add_entry()

    def add_directory(self):
        """Add a folder as a group, for tidier organisation of the launcher."""
        base_dir = self._default_base_dir()
        path = QFileDialog.getExistingDirectory(
            self, "Wybierz katalog", base_dir or ""
        )
        if not path:
            return
        self._prompt_and_add_entry(path=path, is_directory=True)

    @staticmethod
    def _open_item_folder(path):
        """Open the folder containing the application/script (or the folder
        itself when the entry is a directory)."""
        if not path:
            return
        if os.path.isdir(path):
            folder = path
        else:
            folder = os.path.dirname(path)
        if folder and os.path.isdir(folder):
            _open_with_os(folder)

    def _show_properties(self, path, name):
        """Show a small dialog with the details of the added item."""
        if not path:
            return
        from PyQt6.QtWidgets import QTextBrowser

        dlg = QDialog(self)
        dlg.setWindowTitle("Właściwości")
        if self.styleSheet():
            dlg.setStyleSheet(self.styleSheet())
        dlg.setMinimumSize(480, 320)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        details = QTextBrowser()
        details.setOpenExternalLinks(False)
        details.setFrameShape(QFrame.Shape.NoFrame)
        details.setHtml(properties_html(path, name))
        layout.addWidget(details, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        folder_btn = QPushButton("Otwórz folder")
        folder_btn.setObjectName("neutralBtn")
        folder_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        folder_btn.clicked.connect(lambda: self._open_item_folder(path))
        btn_row.addWidget(folder_btn)

        close_btn = QPushButton("Zamknij")
        close_btn.setObjectName("accentBtn")
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dlg.exec()

    def _remove_item(self, item):
        """Remove the entry behind the clicked row.

        The entry index stored on the item is used so duplicate paths (two
        shortcuts pointing at the same file) are handled correctly: only the
        selected row is dropped, even when the view is filtered or sorted.
        """
        path = item.data(Qt.ItemDataRole.UserRole)
        index = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(index, int) or not 0 <= index < len(self._entries):
            # Fallback: remove only the first entry matching this path.
            index = -1
            for candidate, entry in enumerate(self._entries):
                if entry["path"] == path:
                    index = candidate
                    break
        if index >= 0:
            del self._entries[index]
        self._refresh_views()
        self._save_entries()

    def _launch_item(self, item):
        launch_path(item.data(Qt.ItemDataRole.UserRole))


def show_desktop_launcher(stylesheet="", parent=None):
    """Build and show the desktop launcher window (modal)."""
    dlg = DesktopLauncher(stylesheet=stylesheet, parent=parent)
    dlg.exec()
    return dlg
