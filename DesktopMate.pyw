"""
DeskMate (formerly Desktop Mate) v2.7 / Lista tekstów - polsoft.ITS
PyQt6 rewrite: paste text, 15 editable list items, per-item copy button.
EN/PL language switcher, light/dark (Catppuccin Mocha) theme switcher.

Author: Sebastian Januchowski / polsoft.ITS Group
"""

import json
import os
import sys
import re
import runpy
import ctypes
import ctypes.wintypes as wintypes
import subprocess

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, pyqtSignal, QObject, QAbstractNativeEventFilter
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QPen, QColor, QPolygonF, QFont, QCursor, QAction
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QLabel, QPushButton, QLineEdit, QTextEdit, QMenu,
    QFrame, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox, QInputDialog,
    QComboBox,
)

from sticky_notes import StickyNotesManager, default_notes_data_path
from hotkeys import HotkeyManager, Shortcut
from desktop_launcher import show_desktop_launcher, load_launcher_entries, launch_path, native_file_icon

NUM_ITEMS = 15

# Helper tools embedded in the same executable. When frozen, DesktopMate
# re-runs itself with one of these switches and executes the bundled
# script (magnifier.py / pslauncher.py) instead of showing the main window.
HELPER_RUN_ARGS = {
    "--run-magnifier": "magnifier.py",
    "--run-pslauncher": "pslauncher.py",
    "--run-character-picker": "character_picker.py",
}

# Shipped defaults: Ctrl+Alt+T toggles the window, Ctrl+Alt+N the notes.
# They can be changed in Settings; whichever keys the user wins out with are
# saved in text_list_data.json.
def default_hotkeys():
    return (
        Shortcut(kind="key", key=Qt.Key.Key_T,
                 mods={Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier}),
        Shortcut(kind="key", key=Qt.Key.Key_N,
                 mods={Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.AltModifier}),
    )

# Path of the file last used in a save dialog is remembered here (persisted in
# text_list_data.json) so the next save dialog opens in the same location.
LAST_SAVE_DIR = {"dir": ""}

# --- Themes -------------------------------------------------------------
# "dark" = Catppuccin Mocha (default), "light" = Visual Studio style
THEMES = {
    "dark": {
        "bg": "#1e1e2e",             # base
        "fg": "#cdd6f4",             # text
        "entry_bg": "#181825",       # mantle
        "entry_border": "#45475a",   # surface1
        "accent": "#89b4fa",         # blue
        "accent_fg": "#1e1e2e",
        "accent_dark": "#74a8f5",
        "success": "#a6e3a1",        # green
        "muted": "#a6adc8",          # subtext0
        "btn_neutral": "#313244",    # surface0
        "btn_neutral_hover": "#45475a",
        "danger": "#f38ba8",         # red
    },
    "light": {
        "bg": "#f3f3f3",
        "fg": "#1e1e1e",
        "entry_bg": "#ffffff",
        "entry_border": "#c8c8c8",
        "accent": "#0078d4",
        "accent_fg": "#ffffff",
        "accent_dark": "#005a9e",
        "success": "#107c10",
        "muted": "#6e6e6e",
        "btn_neutral": "#e1e1e1",
        "btn_neutral_hover": "#cfcfcf",
        "danger": "#c42b1c",
    },
}


def _load_hotkey(raw, default):
    """Build a Shortcut from persisted JSON, falling back to *default* when the
    stored value is missing or malformed (wrong type, unknown kind, no key)."""
    if raw is None:
        return default
    try:
        shortcut = Shortcut.from_dict(raw)
    except Exception:
        return default
    if shortcut.is_set():
        return shortcut
    return default


def get_app_dir():
    """Return the folder next to the script, or next to the .exe when frozen (PyInstaller)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """Return path to a bundled resource (icon, etc.), working both in dev
    and inside a PyInstaller onefile .exe (where files are unpacked to _MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


# Names of assets already reported as missing, so a missing icon warns once
# per process instead of on every lookup (e.g. each theme switch).
_MISSING_RESOURCES = set()


def resource_or_none(relative_path):
    """Return the path to a bundled resource, or None when it is absent.

    A stripped or incomplete build (or a dev checkout without the assets)
    would otherwise hand Qt a non-existent path, which silently loads an empty
    QPixmap/QIcon.  The absence is reported once to stderr so the cause is
    visible without spamming the log."""
    path = resource_path(relative_path)
    if os.path.exists(path):
        return path
    if relative_path not in _MISSING_RESOURCES:
        _MISSING_RESOURCES.add(relative_path)
        print(
            "DeskMate: resource '{}' not found at '{}' - using a "
            "placeholder icon instead.".format(relative_path, path),
            file=sys.stderr,
        )
    return None


DATA_PATH = os.path.join(get_app_dir(), "text_list_data.json")
ICON_ICO_PATH = resource_or_none("icon.ico")
DESKTOP_PNG_PATH = resource_or_none("Desktop.png")
PSLAUNCHER_PNG_PATH = resource_or_none("pslauncher_icon.png")

ABOUT_INFO = {
    "name": "DeskMate",
    "author": "Sebastian Januchowski",
    "group": "polsoft.ITS\u2122 Group",
    "github": "https://github.com/polsoft-it",
    "email": "polsoft.its@mail.com",
    "license": "Freeware",
    "version": "v2.7",
}

# Tools built into DesktopMate and listed in the About dialog. The names are
# proper nouns, so they stay untranslated; only the section heading
# ("about_apps") follows the interface language.
ABOUT_APPS = (
    ("Character Picker", "characters map picker"),
    ("Desktop Launcher", "app launcher"),
    ("Lupa", "magnifier"),
    ("psLauncher (mod)", "scripts runner"),
    ("Sticky Notes", "handy notes"),
)

STRINGS = {
    "en": {
        "window_title": "DeskMate",
        "title": "DeskMate (15 items)",
        "split_btn": "Split into list ⬇",
        "clear_btn": "Clear all",
        "copy_all_btn": "Copy all",
        "copied_all_btn": "Copied all!",
        "copy_btn": "Copy",
        "copied_btn": "Copied!",
        "ontop_on": "📌 On top",
        "ontop_off": "📌 Normal",
        "compact_btn": "🗕 Compact",
        "compact_hint": "Double-click icon to restore",
        "about_btn": "ℹ About",
        "about_title": "About",
        "about_apps": "Included apps:",
        "status_filled": "{n}/{total} filled",
        "status_saved": "Saved ✓",
        "status_save_error": "Save failed: {err}",
        "status_load_error": "Could not load saved data: {err}",
        "export_btn": "⬇ Export .txt",
        "import_btn": "⬆ Import .txt",
        "export_dialog_title": "Export list to text file",
        "import_dialog_title": "Import list from text file",
        "file_filter_txt": "Text files (*.txt);;All files (*)",
        "status_exported": "Exported ✓",
        "status_imported": "Imported ✓",
        "export_error_title": "Export error",
        "export_error_msg": "Could not save the file:\n{err}",
        "import_error_title": "Import error",
        "import_error_msg": "Could not read the file:\n{err}",
        "notes_btn": "📝 Sticky Notes",
        "settings_btn": "⚙ Settings",
        "settings_title": "Settings",
        "settings_appearance_section": "Appearance",
        "settings_language": "Language:",
        "settings_theme": "Theme:",
        "settings_theme_dark": "Dark",
        "settings_theme_light": "Light",
        "settings_language_en": "English",
        "settings_language_pl": "Polski",
        "settings_notes_path": "Default save location for sticky notes:",
        "settings_browse": "Browse...",
        "settings_reset": "Reset to default",
        "settings_ok": "OK",
        "settings_cancel": "Cancel",
        "settings_folder_dialog": "Select folder for sticky notes data",
        "settings_notes_section": "Sticky notes",
        "settings_table_section": "Save location for the list (one file for all 15 tables)",
        "settings_table_path": "Save location for tables:",
        "settings_table_hint": "One common file for the whole list. If left empty, each save asks about the file and starts in the last location used.",
        "settings_table_dialog": "Select the save file for the tables",
        "settings_table_file": "tables.txt",
        "save_confirm_title": "Confirm save",
        "save_confirm_msg": "Save all 15 tables to:\n{path}?",
        "hotkeys_section": "Hotkeys (keyboard and mouse)",
        "hotkeys_hint": "Global shortcuts work anywhere in Windows. Click a field, then press the key combination (a mouse shortcut needs double-click), or use the Clear button.",
        "hotkey_toggle_window": "Show / hide the main window:",
        "hotkey_toggle_notes": "Show / hide sticky notes:",
        "hotkey_clear": "Clear",
        "hotkey_none": "(not set)",
        "hotkey_press": "Press keys...",
        "hotkey_mouse": "Mouse: {buttons}",
        "hotkey_conflict": "This shortcut is already used by: {owner}",
        "hotkey_conflict_title": "Shortcut in use",
        "hotkey_failed": "Could not register this shortcut system-wide (it may be taken by another program). It will still work while the app has focus.",
        "hotkey_failed_title": "Global shortcut",
        "hotkey_alt": "Alt",
        "hotkey_ctrl": "Ctrl",
        "hotkey_shift": "Shift",
        "hotkey_win": "Win",
        "mouse_left": "Left",
        "mouse_middle": "Middle",
        "mouse_right": "Right",
        "mouse_double": "double-click",
        "hotkey_owner_window": "show/hide main window",
        "hotkey_owner_notes": "show/hide sticky notes",
        "magnifier_btn": "🔍 Magnifier",
        "magnifier_hint": "Magnifier (Alt+Scroll = zoom, Esc = close, Ctrl+Alt+L = show/hide)",
        "magnifier_error_title": "Magnifier error",
        "magnifier_error_msg": "Could not start the magnifier:\n{err}",
        "pslauncher_btn": "psLauncher",
        "pslauncher_hint": "psLauncher – script launcher",
        "pslauncher_error_title": "psLauncher error",
        "pslauncher_error_msg": "Could not start psLauncher:\n{err}",
        "charmap_btn": "Characters",
        "charmap_hint": "Character Picker – click a character to copy it",
        "charmap_error_title": "Character Picker error",
        "charmap_error_msg": "Could not start the Character Picker:\n{err}",
        "apps_btn": "Apps",
        "open_apps_menu": "Open Apps",
    },
    "pl": {
        "window_title": "DeskMate",
        "title": "DeskMate (15 pozycji)",
        "split_btn": "Podziel na listę ⬇",
        "clear_btn": "Wyczyść wszystko",
        "copy_all_btn": "Kopiuj wszystko",
        "copied_all_btn": "Skopiowano!",
        "copy_btn": "Kopiuj",
        "copied_btn": "Skopiowano!",
        "ontop_on": "📌 Na wierzchu",
        "ontop_off": "📌 Normalnie",
        "compact_btn": "🗕 Kompakt",
        "compact_hint": "Kliknij 2x aby przywrócić",
        "about_btn": "ℹ O programie",
        "about_title": "O programie",
        "about_apps": "Aplikacje w programie:",
        "status_filled": "{n}/{total} wypełnionych",
        "status_saved": "Zapisano ✓",
        "status_save_error": "Zapis nieudany: {err}",
        "status_load_error": "Nie udało się wczytać danych: {err}",
        "export_btn": "⬇ Eksportuj .txt",
        "import_btn": "⬆ Importuj .txt",
        "export_dialog_title": "Eksportuj listę do pliku tekstowego",
        "import_dialog_title": "Importuj listę z pliku tekstowego",
        "file_filter_txt": "Pliki tekstowe (*.txt);;Wszystkie pliki (*)",
        "status_exported": "Wyeksportowano ✓",
        "status_imported": "Zaimportowano ✓",
        "export_error_title": "Błąd eksportu",
        "export_error_msg": "Nie udało się zapisać pliku:\n{err}",
        "import_error_title": "Błąd importu",
        "import_error_msg": "Nie udało się odczytać pliku:\n{err}",
        "notes_btn": "📝 Notatki",
        "settings_btn": "⚙ Ustawienia",
        "settings_title": "Ustawienia",
        "settings_appearance_section": "Wygląd",
        "settings_language": "Język:",
        "settings_theme": "Motyw:",
        "settings_theme_dark": "Ciemny",
        "settings_theme_light": "Jasny",
        "settings_language_en": "English",
        "settings_language_pl": "Polski",
        "settings_notes_path": "Domyślna lokalizacja zapisu notatek:",
        "settings_browse": "Przeglądaj...",
        "settings_reset": "Domyślne",
        "settings_ok": "OK",
        "settings_cancel": "Anuluj",
        "settings_folder_dialog": "Wybierz folder na dane notatek",
        "settings_notes_section": "Notatki",
        "settings_table_section": "Lokalizacja zapisu listy (jeden plik dla wszystkich 15 tabel)",
        "settings_table_path": "Lokalizacja zapisu tabel:",
        "settings_table_hint": "Jeden wspólny plik dla całej listy. Jeśli pole jest puste, program pyta o plik przy każdym zapisie i otwiera ostatnią lokalizację.",
        "settings_table_dialog": "Wybierz plik zapisu tabel",
        "settings_table_file": "tabele.txt",
        "save_confirm_title": "Potwierdź zapis",
        "save_confirm_msg": "Zapisać wszystkie 15 tabel w pliku:\n{path}?",
        "hotkeys_section": "Skróty klawiszowe i myszki",
        "hotkeys_hint": "Skróty globalne działają w całym Windows. Kliknij pole i naciśnij kombinację (skrót myszki wymaga podwójnego kliknięcia) albo użyj przycisku Wyczyść.",
        "hotkey_toggle_window": "Pokaż / ukryj główne okno:",
        "hotkey_toggle_notes": "Pokaż / ukryj notatki:",
        "hotkey_clear": "Wyczyść",
        "hotkey_none": "(brak)",
        "hotkey_press": "Naciśnij klawisze...",
        "hotkey_mouse": "Mysz: {buttons}",
        "hotkey_conflict": "Ten skrót jest już używany przez: {owner}",
        "hotkey_conflict_title": "Skrót zajęty",
        "hotkey_failed": "Nie udało się zarejestrować tego skrótu globalnie (może być zajęty przez inny program). Nadal będzie działać, gdy program ma fokus.",
        "hotkey_failed_title": "Skrót globalny",
        "hotkey_alt": "Alt",
        "hotkey_ctrl": "Ctrl",
        "hotkey_shift": "Shift",
        "hotkey_win": "Win",
        "mouse_left": "Lewy",
        "mouse_middle": "Środkowy",
        "mouse_right": "Prawy",
        "mouse_double": "podwójne kliknięcie",
        "hotkey_owner_window": "pokazywanie/ukrywanie głównego okna",
        "hotkey_owner_notes": "pokazywanie/ukrywanie notatek",
        "magnifier_btn": "🔍 Lupa",
        "magnifier_hint": "Lupa (Alt+kółko = zoom, Esc = zamknij, Ctrl+Alt+L = pokaż/ukryj)",
        "magnifier_error_title": "Błąd lupy",
        "magnifier_error_msg": "Nie udało się uruchomić lupy:\n{err}",
        "pslauncher_btn": "psLauncher",
        "pslauncher_hint": "psLauncher – uruchamiacz skryptów",
        "pslauncher_error_title": "Błąd psLaunchera",
        "pslauncher_error_msg": "Nie udało się uruchomić psLaunchera:\n{err}",
        "charmap_btn": "Znaki",
        "charmap_hint": "Wybierak znaków – kliknij znak, aby go skopiować",
        "charmap_error_title": "Błąd wybieraka znaków",
        "charmap_error_msg": "Nie udało się uruchomić wybieraka znaków:\n{err}",
        "apps_btn": "Apps",
        "open_apps_menu": "Otwórz Apps",
    },
}


# ---------------------------------------------------------------------
# Vector logo (mirrors icon.ico artwork) - painted with QPainter so it
# stays crisp at any size and can be re-themed instantly.
# ---------------------------------------------------------------------
def make_logo_pixmap(colors, size):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64.0

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Body (clipboard)
    body_path = QPainterPath()
    body_path.addRoundedRect(QRectF(10 * s, 6 * s, 44 * s, 52 * s), 6 * s, 6 * s)
    painter.fillPath(body_path, QColor(colors["entry_bg"]))
    border_pen = QPen(QColor(colors["entry_border"]))
    border_pen.setWidthF(max(1.0, 2 * s))
    painter.setPen(border_pen)
    painter.drawPath(body_path)

    # Clip
    clip_path = QPainterPath()
    clip_path.addRoundedRect(QRectF(24 * s, 2 * s, 16 * s, 8 * s), 2 * s, 2 * s)
    painter.fillPath(clip_path, QColor(colors["danger"]))

    # Text lines
    line_w = max(2.0, 3 * s)
    pen_fg = QPen(QColor(colors["fg"]))
    pen_fg.setWidthF(line_w)
    pen_fg.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen_fg)
    painter.drawLine(QPointF(20 * s, 24 * s), QPointF(44 * s, 24 * s))
    painter.drawLine(QPointF(20 * s, 34 * s), QPointF(44 * s, 34 * s))

    pen_muted = QPen(QColor(colors["muted"]))
    pen_muted.setWidthF(line_w)
    pen_muted.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen_muted)
    painter.drawLine(QPointF(20 * s, 44 * s), QPointF(34 * s, 44 * s))

    # Paste-arrow accent
    ax = 46 * s
    arrow = QPolygonF([
        QPointF(ax, 38 * s), QPointF(ax, 46 * s), QPointF(ax - 4 * s, 46 * s),
        QPointF(ax + 2 * s, 54 * s), QPointF(ax + 8 * s, 46 * s),
        QPointF(ax + 4 * s, 46 * s), QPointF(ax + 4 * s, 38 * s),
    ])
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colors["success"]))
    painter.drawPolygon(arrow)

    painter.end()
    return pm


def make_desktop_icon(size):
    """Load Desktop.png and return it scaled smoothly to a square `size`
    pixmap (icon for the About button). Returns None if the file is missing."""
    if DESKTOP_PNG_PATH is None:
        return None
    pm = QPixmap(DESKTOP_PNG_PATH)
    if pm.isNull():
        return None
    return pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def make_magnifier_icon(colors, size):
    """Draw a vector magnifying-glass icon with QPainter, matching the
    current theme. Returns a square pixmap of `size` pixels."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64.0

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Lens frame (outer ring)
    lens_outer = 22 * s
    cx, cy = 24 * s, 24 * s
    lens_path = QPainterPath()
    lens_path.addEllipse(QPointF(cx, cy), lens_outer, lens_outer)
    painter.fillPath(lens_path, QColor(colors["entry_bg"]))
    border_pen = QPen(QColor(colors["entry_border"]))
    border_pen.setWidthF(max(1.0, 3 * s))
    painter.setPen(border_pen)
    painter.drawPath(lens_path)

    # Lens glass (inner, lightly tinted with accent)
    lens_inner = 18 * s
    inner_path = QPainterPath()
    inner_path.addEllipse(QPointF(cx, cy), lens_inner, lens_inner)
    glass_color = QColor(colors["accent"])
    glass_color.setAlpha(36)
    painter.fillPath(inner_path, glass_color)
    inner_pen = QPen(QColor(colors["accent"]))
    inner_pen.setWidthF(max(1.0, 1.5 * s))
    painter.setPen(inner_pen)
    painter.drawPath(inner_path)

    # Highlight (glare) on the lens
    highlight = QPainterPath()
    highlight.addEllipse(QPointF(cx - 7 * s, cy - 8 * s), 5 * s, 3.5 * s)
    painter.setPen(Qt.PenStyle.NoPen)
    hl_color = QColor(colors["fg"])
    hl_color.setAlpha(140)
    painter.setBrush(hl_color)
    painter.drawPath(highlight)

    # Handle (diagonal line going down-right)
    handle_start = QPointF(cx + 15 * s, cy + 15 * s)
    handle_end = QPointF(cx + 15 * s + 22 * s, cy + 15 * s + 22 * s)
    handle_pen = QPen(QColor(colors["entry_border"]))
    handle_pen.setWidthF(max(2.0, 5 * s))
    handle_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(handle_pen)
    painter.drawLine(handle_start, handle_end)

    # Accent stripe down the handle
    accent_pen = QPen(QColor(colors["accent"]))
    accent_pen.setWidthF(max(1.0, 2 * s))
    accent_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(accent_pen)
    painter.drawLine(handle_start, handle_end)

    painter.end()
    return pm


# Same terminal ">_" artwork that pslauncher.py embeds (base64 PNG, 64x64)
# - kept here as a fallback in case pslauncher_icon.png is missing.
PSLAUNCHER_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAIAAAAlC+aJAAAAzUlEQVR42u3ZsQ2EMBBEUWogoJor"
    "7IqlGAKkCy5AyAw7O9YfOUXyA9m7NstCCJkq67o1HwAAAAAAAAAAAEbAZ/+eIxLwm73RMA74m73L"
    "IAbUG/SAYoNyDVgMsl1oNkCZQVDIvAZNJTYaZK2Ey6DshSwGcTM3LeA9g76dLja8ch7IBmR/gfg1"
    "kL0LZdeB7Eqc3Qtld6Px54HsE9nY67946np0uZXoDniybPyAh7tWKWD4brQRYOx2uhdA229nAPhD"
    "AwAAAAAAANwFEELCcgAkcpHjlVjypgAAAABJRU5ErkJggg=="
)


def make_charmap_icon(colors, size):
    """Draw a small character-picker icon (rounded tile with a TM-like
    glyph, matching character_picker.py's window icon) in the current theme.
    Returns a square pixmap of `size` pixels."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64.0
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Tile background (circle, like the picker's window icon)
    tile = QPainterPath()
    tile.addEllipse(QPointF(32 * s, 32 * s), 28 * s, 28 * s)
    painter.fillPath(tile, QColor(colors["entry_bg"]))
    border_pen = QPen(QColor(colors["accent"]))
    border_pen.setWidthF(max(1.0, 3 * s))
    painter.setPen(border_pen)
    painter.drawPath(tile)

    # Glyph
    font = QFont()
    font.setPixelSize(max(8, int(40 * s)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(colors["fg"]))
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "\u2122")

    painter.end()
    return pm

def make_desktop_icon_square(colors, size):
    """Desktop Launcher icon for the About list: Desktop.png when it ships,
    otherwise a small monitor glyph drawn in the current theme."""
    pm = QPixmap(DESKTOP_PNG_PATH) if DESKTOP_PNG_PATH else QPixmap()
    if not pm.isNull():
        return pm.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64.0
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    screen = QPainterPath()
    screen.addRoundedRect(QRectF(8 * s, 12 * s, 48 * s, 32 * s), 4 * s, 4 * s)
    painter.fillPath(screen, QColor(colors["entry_bg"]))
    pen = QPen(QColor(colors["accent"]))
    pen.setWidthF(max(1.0, 3 * s))
    painter.setPen(pen)
    painter.drawPath(screen)
    painter.drawLine(QPointF(32 * s, 44 * s), QPointF(32 * s, 52 * s))
    painter.drawLine(QPointF(20 * s, 52 * s), QPointF(44 * s, 52 * s))
    painter.end()
    return pm

def make_sticky_notes_icon(colors, size):
    """Sticky Notes icon for the About list: a note sheet with a folded
    corner and ruled lines, matching the notes button styling."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    s = size / 64.0
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    fold = 18 * s
    sheet = QPainterPath()
    sheet.moveTo(10 * s, 8 * s)
    sheet.lineTo(54 * s - fold, 8 * s)
    sheet.lineTo(54 * s, 8 * s + fold)
    sheet.lineTo(54 * s, 56 * s)
    sheet.lineTo(10 * s, 56 * s)
    sheet.closeSubpath()
    painter.fillPath(sheet, QColor(colors["entry_bg"]))
    pen = QPen(QColor(colors["success"]))
    pen.setWidthF(max(1.0, 3 * s))
    painter.setPen(pen)
    painter.drawPath(sheet)
    corner = QPainterPath()
    corner.moveTo(54 * s - fold, 8 * s)
    corner.lineTo(54 * s - fold, 8 * s + fold)
    corner.lineTo(54 * s, 8 * s + fold)
    painter.drawPath(corner)
    pen_line = QPen(QColor(colors["muted"]))
    pen_line.setWidthF(max(1.0, 3 * s))
    pen_line.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen_line)
    painter.drawLine(QPointF(19 * s, 28 * s), QPointF(45 * s, 28 * s))
    painter.drawLine(QPointF(19 * s, 38 * s), QPointF(45 * s, 38 * s))
    painter.drawLine(QPointF(19 * s, 48 * s), QPointF(35 * s, 48 * s))
    painter.end()
    return pm

def make_pslauncher_icon(size):
    """Return the psLauncher terminal icon (green >_ on dark) as a square
    pixmap of `size` pixels. Prefers pslauncher_icon.png shipped next to the
    script (and bundled into the .exe); falls back to the base64 image that
    pslauncher.py itself embeds, so the icon always shows. Returns None if
    both sources fail."""
    import base64

    # PSLAUNCHER_PNG_PATH is None when the asset was not found at startup; the
    # empty QPixmap below then fails isNull() and the embedded base64 is used.
    pm = QPixmap(PSLAUNCHER_PNG_PATH) if PSLAUNCHER_PNG_PATH else QPixmap()
    if pm.isNull():
        pm = QPixmap()
        pm.loadFromData(base64.b64decode(PSLAUNCHER_ICON_B64))
    if pm.isNull():
        return None
    return pm.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def draw_icon(painter, make_pixmap, size, colors, scale=0.5):
    """Paint a square `size` box with the icon returned by
    make_pixmap(colors, max(1, int(size * scale))) centred inside it.

    The app icons are drawn for ~20 px; handing them a plain rect makes six
    versions come out at six different visual sizes.  Scaling each artwork to
    a common fraction of the box (scale) lines them up, so the About list
    reads as one column of icons instead of a ragged row."""
    inner = max(1, int(size * scale))
    painter.drawPixmap(
        int((size - inner) / 2), int((size - inner) / 2), inner, inner,
        make_pixmap(colors, inner),
    )


def build_stylesheet(c):
    """Build the app-wide QSS from the current theme's color dict."""
    return f"""
        QWidget#root {{
            background-color: {c['bg']};
            background-image: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {c['bg']}, stop:1 {c['entry_bg']});
        }}
        QLabel {{ color: {c['fg']}; background: transparent; }}
        QLabel#titleLabel {{
            color: {c['accent']};
            font-size: 15px; font-weight: bold;
            letter-spacing: 1px;
        }}
        QLabel#statusLabel {{
            color: {c['muted']}; font-size: 11px;
            background-color: {c['entry_bg']};
            border: 1px solid {c['entry_border']};
            border-radius: 8px;
            padding: 2px 8px;
        }}
        QLabel#statusLabel[state="saved"] {{ color: {c['success']}; border-color: {c['success']}; }}
        QLabel#statusLabel[state="error"] {{ color: {c['danger']}; border-color: {c['danger']}; }}
        QLabel#numLabel {{ color: {c['muted']}; font-size: 11px; font-weight: bold; }}

        QFrame#divider1 {{
            background-image: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.5 {c['accent']}, stop:1 transparent);
            max-height: 2px; min-height: 2px; border: none; border-radius: 1px;
        }}
        QFrame#divider2 {{
            background-image: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 transparent, stop:0.5 {c['entry_border']}, stop:1 transparent);
            max-height: 1px; min-height: 1px; border: none;
        }}

        QLineEdit, QTextEdit {{
            background-color: {c['entry_bg']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
            border-radius: 6px;
            padding: 4px 8px;
            selection-background-color: {c['accent']};
            selection-color: {c['accent_fg']};
        }}
        QLineEdit:hover, QTextEdit:hover {{
            border: 1px solid {c['muted']};
        }}
        QLineEdit:focus, QTextEdit:focus {{
            border: 1px solid {c['accent']};
        }}

        QPushButton {{
            border: none;
            border-radius: 6px;
            padding: 6px 10px;
            font-weight: bold;
        }}
        QPushButton#neutralBtn {{
            background-color: {c['btn_neutral']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
        }}
        QPushButton#neutralBtn:hover {{
            background-color: {c['btn_neutral_hover']};
            border: 1px solid {c['accent']};
        }}
        QPushButton#neutralBtn:pressed {{
            background-color: {c['accent_dark']};
            color: {c['accent_fg']};
        }}

        QPushButton#accentBtn, QPushButton#copyBtn {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {c['accent']}, stop:1 {c['accent_dark']});
            color: {c['accent_fg']};
            border: 1px solid {c['accent_dark']};
        }}
        QPushButton#accentBtn:hover, QPushButton#copyBtn:hover {{
            background-color: {c['accent_dark']};
        }}
        QPushButton#accentBtn:pressed, QPushButton#copyBtn:pressed {{
            background-color: {c['accent']};
        }}
        QPushButton#copyBtn[state="success"] {{
            background-color: {c['success']};
            color: {c['accent_fg']};
            border: 1px solid {c['success']};
        }}

        QPushButton#copyAllBtn {{
            background-color: {c['btn_neutral']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
        }}
        QPushButton#copyAllBtn:hover {{
            background-color: {c['btn_neutral_hover']};
            border: 1px solid {c['accent']};
        }}
        QPushButton#copyAllBtn[state="success"] {{
            background-color: {c['success']}; color: {c['accent_fg']};
            border: 1px solid {c['success']};
        }}

        QPushButton#rowClearBtn {{
            background: transparent;
            color: {c['danger']};
            font-weight: bold;
            border: none;
            border-radius: 6px;
        }}
        QPushButton#rowClearBtn:hover {{ background-color: {c['danger']}; color: {c['bg']}; }}

        /* pin / always-on-top, compact, settings and about buttons -
           identical square look */
        QPushButton#ontopBtn, QPushButton#compactBtn,
        QPushButton#settingsBtn, QPushButton#aboutBtn {{
            background-color: {c['btn_neutral']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
            border-radius: 8px;
            padding: 2px;
        }}
        QPushButton#ontopBtn:hover, QPushButton#compactBtn:hover,
        QPushButton#settingsBtn:hover, QPushButton#aboutBtn:hover {{
            background-color: {c['btn_neutral_hover']};
            border: 1px solid {c['accent']};
        }}
        QPushButton#ontopBtn:pressed, QPushButton#compactBtn:pressed,
        QPushButton#settingsBtn:pressed, QPushButton#aboutBtn:pressed {{
            background-color: {c['accent_dark']};
            color: {c['accent_fg']};
        }}
        QPushButton#ontopBtn[active="true"] {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {c['accent']}, stop:1 {c['accent_dark']});
            color: {c['accent_fg']};
            border: 1px solid {c['accent_dark']};
            font-weight: bold;
        }}
        QPushButton#ontopBtn[active="true"]:hover {{ background-color: {c['accent_dark']}; }}

        QPushButton[icon="true"] {{
            font-size: 14px;
            font-weight: normal;
            padding: 2px;
            border-radius: 8px;
            border: 1px solid transparent;
        }}
        QPushButton[icon="true"]:hover {{
            border: 1px solid {c['accent']};
            background-color: {c['btn_neutral_hover']};
        }}
        QPushButton[icon="true"]:pressed {{
            background-color: {c['accent_dark']};
            border: 1px solid {c['accent_dark']};
        }}

        /* danger-ish hover for the trash button */
        QPushButton[role="clear"]:hover {{
            background-color: {c['danger']};
            border: 1px solid {c['danger']};
            color: {c['bg']};
        }}
        QPushButton[role="notes"]:hover {{
            background-color: {c['success']};
            border: 1px solid {c['success']};
            color: {c['accent_fg']};
        }}
        QPushButton[role="export"]:hover {{
            background-color: {c['accent']};
            border: 1px solid {c['accent']};
            color: {c['accent_fg']};
        }}
        QPushButton[role="info"]:hover {{
            background-color: {c['accent']};
            color: {c['accent_fg']};
        }}

        QDialog {{ background-color: {c['bg']}; }}

        /* ---- About dialog: header card + grouped app list ---- */
        QFrame#aboutHeader {{
            background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {c['entry_bg']}, stop:1 {c['bg']});
            border: 1px solid {c['entry_border']};
            border-radius: 10px;
        }}
        QFrame#aboutAppsCard {{
            background-color: {c['entry_bg']};
            border: 1px solid {c['entry_border']};
            border-radius: 10px;
        }}
        QFrame#aboutAppRow {{
            background: transparent;
            border: none;
            border-radius: 6px;
        }}
        QFrame#aboutAppRow:hover {{ background-color: {c['btn_neutral']}; }}
        QLabel#aboutAppIcon {{
            background-color: {c['btn_neutral']};
            border: 1px solid {c['entry_border']};
            border-radius: 7px;
        }}
        QLabel#aboutTitle {{
            color: {c['fg']};
            font-size: 17px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
        QLabel#aboutVersion {{
            color: {c['accent_fg']};
            background-color: {c['accent']};
            border-radius: 8px;
            padding: 1px 8px;
            font-size: 10px;
            font-weight: bold;
        }}
        QLabel#aboutLink {{ color: {c['accent']}; text-decoration: underline; }}
        QLabel#aboutLink:hover {{ color: {c['accent_dark']}; }}
        QLabel#aboutGroup {{ color: {c['muted']}; }}
        QLabel#aboutLicense {{ color: {c['success']}; font-weight: bold; }}
        QLabel#aboutAppsHeader {{
            color: {c['muted']};
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        QLabel#aboutAppName {{ color: {c['fg']}; font-weight: bold; }}
        QLabel#aboutAppDesc {{ color: {c['muted']}; font-size: 11px; }}

        QComboBox {{
            background-color: {c['entry_bg']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
            border-radius: 6px;
            padding: 3px 8px;
        }}
        QComboBox:hover {{ border: 1px solid {c['accent']}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox QAbstractItemView {{
            background-color: {c['entry_bg']};
            color: {c['fg']};
            border: 1px solid {c['entry_border']};
            selection-background-color: {c['accent']};
            selection-color: {c['accent_fg']};
        }}

        QToolTip {{
            background-color: {c['entry_bg']};
            color: {c['fg']};
            border: 1px solid {c['accent']};
            border-radius: 4px;
            padding: 4px;
        }}

        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px 2px 2px 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c['btn_neutral']};
            border-radius: 4px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background-color: {c['accent']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px 2px 2px 2px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {c['btn_neutral']};
            border-radius: 4px;
            min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{ background-color: {c['accent']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


class ClickableLabel(QLabel):
    """A QLabel that copies its assigned text to the clipboard when clicked
    (used for the GitHub/email 'links' in the About dialog)."""

    def __init__(self, text, copy_value, parent=None):
        super().__init__(text, parent)
        self._copy_value = copy_value
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        QApplication.clipboard().setText(self._copy_value)
        super().mousePressEvent(event)


class ShortcutEdit(QLineEdit):
    """A read-only field that records a key combination or a mouse gesture.

    Click it and press the keys you want (or double-click a mouse button); the
    field stays read-only so the shortcut can never be typed in as text."""

    captured = pyqtSignal(object)   # Shortcut or None

    def __init__(self, shortcut=None, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._shortcut = shortcut
        self._capturing = False

    def shortcut(self):
        return self._shortcut

    def set_shortcut(self, shortcut, describe=None):
        self._shortcut = shortcut
        if describe is None:
            self.setText("" if shortcut is None else "?")
        else:
            self.setText(describe(shortcut))

    def set_capture_hint(self, text):
        self._hint = text

    # -- capture -------------------------------------------------------
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._capturing = True
        if getattr(self, "_hint", None):
            self.setText(self._hint)

    def focusOutEvent(self, event):
        self._capturing = False
        super().focusOutEvent(event)
        self.captured.emit(self._shortcut)

    def keyPressEvent(self, event):
        if not self._capturing:
            return super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            return
        shortcut = Shortcut.from_key_event(event)
        if shortcut is None:
            # only modifiers pressed so far - keep waiting, show the prefix
            return
        self._shortcut = shortcut
        self.setText(shortcut.describe(self._translate))
        self.captured.emit(shortcut)

    def _translate(self, key):
        """Translate a STRINGS key; falls back to the key itself in isolation."""
        tr = getattr(self, "_tr", None)
        return tr(key) if tr else key

    def _describe(self, shortcut):
        return shortcut.describe(self._translate)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if not self._capturing:
            return
        shortcut = Shortcut.from_mouse_event(event)
        if shortcut is not None:
            self._shortcut = shortcut
            self.setText(self._describe(shortcut))
            self.captured.emit(shortcut)

    def mouseDoubleClickEvent(self, event):
        if not self._capturing:
            return
        shortcut = Shortcut.from_mouse_event(event)
        if shortcut is not None:
            shortcut.double = True
            self._shortcut = shortcut
            self.setText(self._describe(shortcut))
            self.captured.emit(shortcut)


class CompactIcon(QWidget):
    """Small always-on-top floating icon shown while the main window is
    collapsed into compact mode. Draggable; double-click restores the app."""

    def __init__(self, colors, on_restore, hint_text="", on_open_launcher=None,
                 open_launcher_label="Open Apps"):
        super().__init__()
        self._on_restore = on_restore
        self._on_open_launcher = on_open_launcher
        self._open_launcher_label = open_launcher_label
        self._drag_pos = None
        self._context_menu = None
        if hint_text:
            self.setToolTip(hint_text)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        size, pad = 48, 4
        self.setFixedSize(size + pad * 2, size + pad * 2)
        self.setStyleSheet(f"background-color: {colors['accent']}; border-radius: 8px;")

        logo = QLabel(self)
        desktop_icon = make_desktop_icon(size)   # Launcher icon (Desktop.png)
        if desktop_icon is not None:
            logo.setPixmap(desktop_icon)
        else:
            logo.setPixmap(make_logo_pixmap(colors, size))
        logo.setGeometry(pad, pad, size, size)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - size - pad * 2 - 40, 60)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseDoubleClickEvent(self, event):
        self._on_restore()

    def _show_context_menu(self, position):
        # Show launcher entries directly from the compact icon."
        menu = QMenu(self)
        menu.addAction(QAction("Przywróć okno", menu, triggered=self._on_restore))
        if self._on_open_launcher is not None:
            menu.addAction(QAction(self._open_launcher_label, menu, triggered=self._on_open_launcher))
        menu.addSeparator()

        entries = load_launcher_entries()
        if entries:
            for entry in entries:
                action = QAction(native_file_icon(entry["path"]), entry["name"], menu)
                action.setToolTip(entry["path"])
                action.triggered.connect(lambda checked=False, path=entry["path"]: launch_path(path))
                menu.addAction(action)
        else:
            empty_action = QAction("Brak dodanych aplikacji i skryptów", menu)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)

        self._context_menu = menu
        menu.exec(self.mapToGlobal(position))
        self._context_menu = None
class MouseShortcutFilter(QObject, QAbstractNativeEventFilter):
    """Watches the mouse system-wide so a mouse shortcut also fires when the
    application does not have focus."""

    _WM_LBUTTONDOWN = 0x0201
    _WM_RBUTTONDOWN = 0x0204
    _WM_MBUTTONDOWN = 0x0207
    _BUTTONS = {
        _WM_LBUTTONDOWN: Qt.MouseButton.LeftButton,
        _WM_RBUTTONDOWN: Qt.MouseButton.RightButton,
        _WM_MBUTTONDOWN: Qt.MouseButton.MiddleButton,
    }
    _DOUBLECLICK_MS = 400

    def __init__(self, hotkey_manager, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._hotkeys = hotkey_manager
        self._last = {}          # button -> timestamp of the previous press
        self._fired_at = {}      # button -> timestamp of the last fired shortcut

    def nativeEventFilter(self, event_type, message):
        if not _WINDOWS or event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = ctypes.cast(int(message.__int__()), ctypes.POINTER(wintypes.MSG)).contents
        except Exception:
            return False, 0
        button = self._BUTTONS.get(msg.message)
        if button is None:
            return False, 0
        if not self._hotkeys.mouse_owners():
            return False, 0

        now = _now_ms()
        previous = self._last.get(button, 0)
        is_double = (now - previous) <= self._DOUBLECLICK_MS
        self._last[button] = now
        if is_double:
            # the double click consumed this press, do not count a triple click
            self._last[button] = 0

        # a single click must not also fire when the same button is configured
        # as a double click; only fire once we know the click can not double up
        if is_double:
            matched = self._fire(button, True)
            self._fired_at[button] = now if matched else 0
            return (matched, 0) if matched else (False, 0)

        QTimer.singleShot(self._DOUBLECLICK_MS + 10, lambda: self._maybe_single(button, now))
        return False, 0

    def _maybe_single(self, button, press_time):
        if self._last.get(button) == 0:
            return                       # it turned into a double click
        if self._fired_at.get(button, 0) >= press_time:
            return
        self._fire(button, False)

    def _fire(self, button, double):
        for shortcut, signal in (
            (self._hotkeys.window_shortcut, self._hotkeys.triggered_window),
            (self._hotkeys.notes_shortcut, self._hotkeys.triggered_notes),
        ):
            if shortcut.kind == "mouse" and shortcut.button == button \
                    and shortcut.double == double:
                signal.emit()
                return True
        return False


def _now_ms():
    import time
    return int(time.monotonic() * 1000)


class TextListApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("root")
        self.lang = "en"          # English as default language
        self.theme_name = "light"  # Visual Studio style as default theme
        self.always_on_top = False
        self.compact_window = None
        self.notes_manager = None
        self.notes_data_path = None
        self._magnifier_proc = None
        self._pslauncher_proc = None
        self._charmap_proc = None
        # One shared save file for the whole list of tables (empty = ask on save)
        self.tables_save_path = ""
        self.window_hotkey, self.notes_hotkey = default_hotkeys()

        self.entries = []
        self.copy_buttons = []
        self.row_clear_buttons = []
        self.num_labels = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save_data)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._revert_status)
        self._settings_open = False
        self._settings_loaded = False

        self._load_settings()   # restore lang/theme/always_on_top/hotkeys before building UI
        self.hotkeys = HotkeyManager(self)
        self.hotkeys.triggered_window.connect(self.toggle_window_visibility)
        self.hotkeys.triggered_notes.connect(self.toggle_sticky_notes)
        self.notes_manager = StickyNotesManager(lang=self.lang, data_path=self.notes_data_path)
        self._build_ui()
        self._apply_language()
        self._apply_theme()
        self._set_window_icon()
        self.load_data()
        self._update_status()

        self.setFixedSize(self.sizeHint())
        self.hotkeys_failed = self.hotkeys.apply(self.window_hotkey, self.notes_hotkey)
        QApplication.instance().installNativeEventFilter(self.hotkeys)
        # a mouse shortcut should also work when another window has focus
        self._mouse_shortcut_filter = MouseShortcutFilter(self.hotkeys, self)
        QApplication.instance().installNativeEventFilter(self._mouse_shortcut_filter)

    @property
    def colors(self):
        return THEMES[self.theme_name]

    def t(self, key):
        return STRINGS[self.lang][key]

    def _set_window_icon(self):
        if ICON_ICO_PATH:
            self.setWindowIcon(QIcon(ICON_ICO_PATH))
        else:
            self.setWindowIcon(QIcon(make_logo_pixmap(THEMES["dark"], 64)))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(0)

        # --- Buttons row ---
        root.addSpacing(4)
        top_bar = QHBoxLayout()

        self.desktop_btn = QPushButton()
        self.desktop_btn.setObjectName("neutralBtn")
        self.desktop_btn.setProperty("icon", "true")
        self.desktop_btn.setFixedWidth(32)
        self.desktop_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        desktop_icon = make_desktop_icon(20)
        if desktop_icon is not None:
            self.desktop_btn.setIcon(QIcon(desktop_icon))
            self.desktop_btn.setIconSize(desktop_icon.size())
        else:
            self.desktop_btn.setText("🖥")
        self.desktop_btn.clicked.connect(self.show_desktop_popup)
        top_bar.addWidget(self.desktop_btn)

        self.magnifier_btn = QPushButton()
        self.magnifier_btn.setObjectName("neutralBtn")
        self.magnifier_btn.setProperty("icon", "true")
        self.magnifier_btn.setFixedWidth(32)
        self.magnifier_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        mag_icon = make_magnifier_icon(self.colors, 20)
        self.magnifier_btn.setIcon(QIcon(mag_icon))
        self.magnifier_btn.setIconSize(mag_icon.size())
        self.magnifier_btn.clicked.connect(self.toggle_magnifier)
        top_bar.addWidget(self.magnifier_btn)

        self.pslauncher_btn = QPushButton()
        self.pslauncher_btn.setObjectName("neutralBtn")
        self.pslauncher_btn.setProperty("icon", "true")
        self.pslauncher_btn.setFixedWidth(32)
        self.pslauncher_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ps_icon = make_pslauncher_icon(20)
        if ps_icon is not None:
            self.pslauncher_btn.setIcon(QIcon(ps_icon))
            self.pslauncher_btn.setIconSize(ps_icon.size())
        else:
            self.pslauncher_btn.setText(">_")
        self.pslauncher_btn.clicked.connect(self.toggle_pslauncher)
        top_bar.addWidget(self.pslauncher_btn)

        self.charmap_btn = QPushButton()
        self.charmap_btn.setObjectName("neutralBtn")
        self.charmap_btn.setProperty("icon", "true")
        self.charmap_btn.setFixedWidth(32)
        self.charmap_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        charmap_icon = make_charmap_icon(self.colors, 20)
        self.charmap_btn.setIcon(QIcon(charmap_icon))
        self.charmap_btn.setIconSize(charmap_icon.size())
        self.charmap_btn.clicked.connect(self.toggle_character_picker)
        top_bar.addWidget(self.charmap_btn)

        top_bar.addStretch(1)

        self.compact_btn = QPushButton("🗕")
        self.compact_btn.setObjectName("compactBtn")
        self.compact_btn.setProperty("icon", "true")
        self.compact_btn.setFixedWidth(32)
        self.compact_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.compact_btn.clicked.connect(self.enter_compact_mode)
        top_bar.addWidget(self.compact_btn)

        self.ontop_btn = QPushButton("📌")
        self.ontop_btn.setObjectName("ontopBtn")
        self.ontop_btn.setProperty("icon", "true")
        self.ontop_btn.setFixedWidth(32)
        self.ontop_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ontop_btn.clicked.connect(self.toggle_always_on_top)
        if self.always_on_top:
            self.ontop_btn.setProperty("active", "true")
        top_bar.addWidget(self.ontop_btn)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setProperty("icon", "true")
        self.settings_btn.setFixedWidth(32)
        self.settings_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.settings_btn.setProperty("role", "info")
        self.settings_btn.clicked.connect(self.show_settings)
        top_bar.addWidget(self.settings_btn)

        self.about_btn = QPushButton("ℹ")
        self.about_btn.setObjectName("aboutBtn")
        self.about_btn.setProperty("icon", "true")
        self.about_btn.setFixedWidth(32)
        self.about_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.about_btn.setProperty("role", "info")
        self.about_btn.clicked.connect(self.show_about)
        top_bar.addWidget(self.about_btn)

        root.addLayout(top_bar)
        root.addSpacing(10)

        self.divider1 = QFrame()
        self.divider1.setObjectName("divider1")
        root.addWidget(self.divider1)
        root.addSpacing(10)

        # --- Paste area ---
        paste_row = QHBoxLayout()
        self.bulk_text = QTextEdit()
        self.bulk_text.setFixedHeight(90)
        self.bulk_text.textChanged.connect(self._on_bulk_change)
        paste_row.addWidget(self.bulk_text, 1)

        self.split_btn = QPushButton("⬇")
        self.split_btn.setObjectName("accentBtn")
        self.split_btn.setProperty("icon", "true")
        self.split_btn.setFixedWidth(40)
        self.split_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.split_btn.clicked.connect(self.split_to_list)
        paste_row.addWidget(self.split_btn)
        root.addLayout(paste_row)
        root.addSpacing(10)

        # --- Toolbar ---
        toolbar = QHBoxLayout()
        self.clear_btn = QPushButton("🗑")
        self.clear_btn.setObjectName("neutralBtn")
        self.clear_btn.setProperty("icon", "true")
        self.clear_btn.setFixedWidth(34)
        self.clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.clear_btn.setProperty("role", "clear")
        self.clear_btn.clicked.connect(self.clear_all)
        toolbar.addWidget(self.clear_btn)

        self.copy_all_btn = QPushButton("📋")
        self.copy_all_btn.setObjectName("copyAllBtn")
        self.copy_all_btn.setProperty("icon", "true")
        self.copy_all_btn.setFixedWidth(34)
        self.copy_all_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_all_btn.clicked.connect(self.copy_all)
        toolbar.addWidget(self.copy_all_btn)

        self.export_btn = QPushButton("💾")
        self.export_btn.setObjectName("neutralBtn")
        self.export_btn.setProperty("icon", "true")
        self.export_btn.setFixedWidth(34)
        self.export_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.export_btn.setProperty("role", "export")
        self.export_btn.clicked.connect(self.export_to_file)
        toolbar.addWidget(self.export_btn)

        self.import_btn = QPushButton("📂")
        self.import_btn.setObjectName("neutralBtn")
        self.import_btn.setProperty("icon", "true")
        self.import_btn.setFixedWidth(34)
        self.import_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.import_btn.clicked.connect(self.import_from_file)
        toolbar.addWidget(self.import_btn)

        self.notes_btn = QPushButton("📝")
        self.notes_btn.setObjectName("neutralBtn")
        self.notes_btn.setProperty("icon", "true")
        self.notes_btn.setProperty("role", "notes")
        self.notes_btn.setFixedWidth(34)
        self.notes_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.notes_btn.clicked.connect(self.toggle_sticky_notes)
        toolbar.addWidget(self.notes_btn)

        toolbar.addStretch(1)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        toolbar.addWidget(self.status_label)
        root.addLayout(toolbar)
        root.addSpacing(10)

        self.divider2 = QFrame()
        self.divider2.setObjectName("divider2")
        root.addWidget(self.divider2)
        root.addSpacing(12)

        # --- 15 item list ---
        for i in range(1, NUM_ITEMS + 1):
            row = QHBoxLayout()
            row.setSpacing(6)

            num_label = QLabel(f"{i}.")
            num_label.setObjectName("numLabel")
            num_label.setFixedWidth(22)
            num_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(num_label)
            self.num_labels.append(num_label)

            entry = QLineEdit()
            entry.textChanged.connect(self._on_entry_change)
            idx = i - 1
            entry.returnPressed.connect(lambda idx=idx: self._focus_next_entry(idx))
            row.addWidget(entry, 1)
            self.entries.append(entry)

            row_clear_btn = QPushButton("✕")
            row_clear_btn.setObjectName("rowClearBtn")
            row_clear_btn.setFixedWidth(28)
            row_clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            row_clear_btn.clicked.connect(lambda checked, idx=idx: self.clear_item(idx))
            row.addWidget(row_clear_btn)
            self.row_clear_buttons.append(row_clear_btn)

            copy_btn = QPushButton("📋")
            copy_btn.setObjectName("copyBtn")
            copy_btn.setProperty("icon", "true")
            copy_btn.setFixedWidth(30)
            copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            copy_btn.clicked.connect(lambda checked=False, idx=idx: self.copy_item(idx))
            row.addWidget(copy_btn)
            self.copy_buttons.append(copy_btn)

            root.addLayout(row)
            root.addSpacing(3)

    def _focus_next_entry(self, idx):
        if idx + 1 < NUM_ITEMS:
            self.entries[idx + 1].setFocus()
            self.entries[idx + 1].selectAll()

    # ------------------------------------------------------------------
    # Language / theme
    # ------------------------------------------------------------------
    def _apply_language(self):
        self.setWindowTitle(self.t("window_title"))
        self.split_btn.setToolTip(self.t("split_btn"))
        self.clear_btn.setToolTip(self.t("clear_btn"))
        self.copy_all_btn.setToolTip(self.t("copy_all_btn"))
        self.export_btn.setToolTip(self.t("export_btn"))
        if self.tables_save_path:
            self.export_btn.setToolTip(self.t("export_btn") + ":\n" + self.tables_save_path)
        self.import_btn.setToolTip(self.t("import_btn"))
        self.notes_btn.setToolTip(self.t("notes_btn"))
        self.settings_btn.setToolTip(self.t("settings_btn"))
        self.ontop_btn.setToolTip(self.t("ontop_on") if self.always_on_top else self.t("ontop_off"))
        self.compact_btn.setToolTip(self.t("compact_btn"))
        self.about_btn.setToolTip(self.t("about_btn"))
        self.desktop_btn.setToolTip(self.t("apps_btn"))
        self.magnifier_btn.setToolTip(self.t("magnifier_hint"))
        self.pslauncher_btn.setToolTip(self.t("pslauncher_hint"))
        self.charmap_btn.setToolTip(self.t("charmap_hint"))
        for btn in self.copy_buttons:
            btn.setToolTip(self.t("copy_btn"))
        self._update_status()

    def set_language(self, lang):
        """Switch the interface language (used by Settings)."""
        if lang not in STRINGS or lang == self.lang:
            return
        self.lang = lang
        self._apply_language()
        if self.notes_manager is not None:
            self.notes_manager.set_language(self.lang)
        self.save_data()

    def _apply_theme(self):
        c = self.colors
        self.setStyleSheet(build_stylesheet(c))

    def set_theme(self, theme_name):
        """Switch the colour theme (used by Settings)."""
        if theme_name not in THEMES or theme_name == self.theme_name:
            return
        self.theme_name = theme_name
        self._apply_theme()
        mag_icon = make_magnifier_icon(self.colors, 20)
        self.magnifier_btn.setIcon(QIcon(mag_icon))
        self.magnifier_btn.setIconSize(mag_icon.size())
        charmap_icon = make_charmap_icon(self.colors, 20)
        self.charmap_btn.setIcon(QIcon(charmap_icon))
        self.charmap_btn.setIconSize(charmap_icon.size())
        self.save_data()

    def toggle_always_on_top(self):
        self.always_on_top = not self.always_on_top
        self.ontop_btn.setToolTip(self.t("ontop_on") if self.always_on_top else self.t("ontop_off"))
        self.ontop_btn.setProperty("active", "true" if self.always_on_top else "false")
        self.ontop_btn.style().unpolish(self.ontop_btn)
        self.ontop_btn.style().polish(self.ontop_btn)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.always_on_top)
        self.show()
        self.save_data()

    def enter_compact_mode(self):
        self.hide()

        def restore():
            self.compact_window.close()
            self.compact_window = None
            self.show()
            self.raise_()
            self.activateWindow()

        self.compact_window = CompactIcon(
            self.colors, restore, self.t("compact_hint"), self.show_desktop_popup,
            self.t("open_apps_menu"),
        )
        self.compact_window.show()

    def _apply_hotkeys(self, announce=False, parent=None):
        """(Re)register the shortcuts and tell the user about OS refusals."""
        failed = self.hotkeys.apply(self.window_hotkey, self.notes_hotkey)
        self.hotkeys_failed = failed
        if announce and failed:
            QMessageBox.information(
                parent or self,
                self.t("hotkey_failed_title"),
                self.t("hotkey_failed"),
            )
        return failed

    def closeEvent(self, event):
        if self._magnifier_proc is not None and self._magnifier_proc.poll() is None:
            self._stop_helper(self._magnifier_proc)
            self._magnifier_proc = None
        if self._pslauncher_proc is not None and self._pslauncher_proc.poll() is None:
            self._stop_helper(self._pslauncher_proc)
            self._pslauncher_proc = None
        if self._charmap_proc is not None and self._charmap_proc.poll() is None:
            self._stop_helper(self._charmap_proc)
            self._charmap_proc = None
        super().closeEvent(event)

    def toggle_window_visibility(self):
        """Show the window if it is hidden, hide it when it is in front."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
            return
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_sticky_notes(self):
        if self.notes_manager is None:
            self.notes_manager = StickyNotesManager(lang=self.lang, data_path=self.notes_data_path)
        self.notes_manager.toggle_visibility()

    # ------------------------------------------------------------------
    # Hotkey events (also used while the app does not have focus)
    # ------------------------------------------------------------------
    def keyPressEvent(self, event):
        if self.hotkeys.handle_key_event(event):
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.hotkeys.handle_mouse_event(event, double=False):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.hotkeys.handle_mouse_event(event, double=True):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def show_settings(self):
        if self._settings_open:
            return
        self._settings_open = True
        c = self.colors
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("about_title"))
        dlg.setWindowTitle(self.t("settings_title"))
        dlg.setStyleSheet(build_stylesheet(c))
        dlg.setFixedSize(620, 470)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # --- Section 0: language and theme ---
        appearance_header = QLabel(self.t("settings_appearance_section"))
        appearance_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(appearance_header)

        appearance_row = QHBoxLayout()
        appearance_row.setSpacing(6)

        appearance_row.addWidget(QLabel(self.t("settings_language")))
        lang_box = QComboBox()
        lang_box.addItem(self.t("settings_language_en"), "en")
        lang_box.addItem(self.t("settings_language_pl"), "pl")
        lang_box.setCurrentIndex(0 if self.lang == "en" else 1)
        lang_box.setFixedWidth(140)
        appearance_row.addWidget(lang_box)

        appearance_row.addSpacing(16)
        appearance_row.addWidget(QLabel(self.t("settings_theme")))
        theme_box = QComboBox()
        theme_box.addItem(self.t("settings_theme_dark"), "dark")
        theme_box.addItem(self.t("settings_theme_light"), "light")
        theme_box.setCurrentIndex(0 if self.theme_name == "dark" else 1)
        theme_box.setFixedWidth(140)
        appearance_row.addWidget(theme_box)
        appearance_row.addStretch(1)

        layout.addLayout(appearance_row)

        # --- Section 1: sticky notes data file ---
        notes_label = QLabel(self.t("settings_notes_path"))
        notes_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(notes_label)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)

        current_path = self.notes_manager.get_data_path() if self.notes_manager else (self.notes_data_path or default_notes_data_path())
        path_edit = QLineEdit(current_path)
        path_edit.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        path_row.addWidget(path_edit, 1)

        def browse_notes():
            start_dir = os.path.dirname(path_edit.text()) if path_edit.text() else get_app_dir()
            folder = QFileDialog.getExistingDirectory(self, self.t("settings_folder_dialog"), start_dir)
            if folder:
                path_edit.setText(os.path.join(folder, "sticky_notes_data.json"))

        browse_btn = QPushButton(self.t("settings_browse"))
        browse_btn.setObjectName("neutralBtn")
        browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        browse_btn.clicked.connect(browse_notes)
        path_row.addWidget(browse_btn)

        reset_btn = QPushButton(self.t("settings_reset"))
        reset_btn.setObjectName("neutralBtn")
        reset_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        reset_btn.clicked.connect(lambda: path_edit.setText(default_notes_data_path()))
        path_row.addWidget(reset_btn)

        layout.addLayout(path_row)

        # --- Section 2: one shared save file for the whole list ---
        table_header = QLabel(self.t("settings_table_section"))
        table_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(table_header)

        table_hint = QLabel(self.t("settings_table_hint"))
        table_hint.setWordWrap(True)
        table_hint.setStyleSheet(f"color: {c['muted']}; font-size: 10px;")
        layout.addWidget(table_hint)

        table_row = QHBoxLayout()
        table_row.setSpacing(6)

        table_label = QLabel(self.t("settings_table_path"))
        table_row.addWidget(table_label)

        table_edit = QLineEdit(self.tables_save_path)
        table_edit.setCursor(QCursor(Qt.CursorShape.IBeamCursor))
        table_row.addWidget(table_edit, 1)

        def browse_tables():
            default_dir = LAST_SAVE_DIR["dir"] or get_app_dir()
            start = table_edit.text().strip() or os.path.join(
                default_dir, self.t("settings_table_file")
            )
            path, _ = QFileDialog.getSaveFileName(
                dlg, self.t("settings_table_dialog"), start, self.t("file_filter_txt")
            )
            if path:
                table_edit.setText(path)
                LAST_SAVE_DIR["dir"] = os.path.dirname(path)

        table_browse_btn = QPushButton(self.t("settings_browse"))
        table_browse_btn.setObjectName("neutralBtn")
        table_browse_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        table_browse_btn.clicked.connect(browse_tables)
        table_row.addWidget(table_browse_btn)

        table_clear_btn = QPushButton("✕")
        table_clear_btn.setObjectName("rowClearBtn")
        table_clear_btn.setFixedWidth(28)
        table_clear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        table_clear_btn.clicked.connect(lambda: table_edit.setText(""))
        table_row.addWidget(table_clear_btn)

        layout.addLayout(table_row)

        # --- Section 3: keyboard / mouse shortcuts ---
        hotkey_header = QLabel(self.t("hotkeys_section"))
        hotkey_header.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(hotkey_header)

        hotkey_hint = QLabel(self.t("hotkeys_hint"))
        hotkey_hint.setWordWrap(True)
        hotkey_hint.setStyleSheet(f"color: {c['muted']}; font-size: 10px;")
        layout.addWidget(hotkey_hint)

        def translate(key):
            return self.t(key)

        window_edit = ShortcutEdit()
        window_edit._tr = translate
        window_edit.set_shortcut(self.window_hotkey, lambda s: s.describe(translate))
        window_edit.set_capture_hint(self.t("hotkey_press"))
        notes_edit = ShortcutEdit()
        notes_edit._tr = translate
        notes_edit.set_shortcut(self.notes_hotkey, lambda s: s.describe(translate))
        notes_edit.set_capture_hint(self.t("hotkey_press"))

        def add_hotkey_row(label_key, edit):
            row = QHBoxLayout()
            row.setSpacing(6)
            label = QLabel(self.t(label_key))
            label.setFixedWidth(230)
            row.addWidget(label)
            edit.setFixedWidth(200)
            row.addWidget(edit)
            clear = QPushButton(self.t("hotkey_clear"))
            clear.setObjectName("neutralBtn")
            clear.setFixedWidth(90)
            clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            clear.clicked.connect(lambda: (
                edit.set_shortcut(Shortcut(kind="none"), lambda s: s.describe(translate)),
                edit.captured.emit(Shortcut(kind="none")),
            ))
            row.addWidget(clear)
            row.addStretch(1)
            layout.addLayout(row)

        add_hotkey_row("hotkey_toggle_window", window_edit)
        add_hotkey_row("hotkey_toggle_notes", notes_edit)

        last_conflict = [None]

        def make_conflict_checker(this, other, owner_key):
            def on_captured(shortcut):
                if shortcut is None or not shortcut.is_set():
                    last_conflict[0] = None
                    return
                if other.shortcut() is not None and other.shortcut().is_set() \
                        and shortcut.same_as(other.shortcut()):
                    last_conflict[0] = self.t("hotkey_conflict").format(
                        owner=self.t(owner_key)
                    )
                    QMessageBox.warning(dlg, self.t("hotkey_conflict_title"), last_conflict[0])
                    # drop the duplicate: neither field may keep the same combo
                    this.set_shortcut(Shortcut(kind="none"), lambda s: s.describe(translate))
                else:
                    last_conflict[0] = None
            return on_captured

        window_edit.captured.connect(
            make_conflict_checker(window_edit, notes_edit, "hotkey_owner_notes"))
        notes_edit.captured.connect(
            make_conflict_checker(notes_edit, window_edit, "hotkey_owner_window"))

        layout.addStretch(1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        cancel_btn = QPushButton(self.t("settings_cancel"))
        cancel_btn.setObjectName("neutralBtn")
        cancel_btn.setFixedWidth(90)
        cancel_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton(self.t("settings_ok"))
        ok_btn.setObjectName("accentBtn")
        ok_btn.setFixedWidth(90)
        ok_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        def on_ok():
            new_path_raw = path_edit.text().strip()
            if not new_path_raw:
                new_path = None
            else:
                if os.path.isdir(new_path_raw):
                    new_path = os.path.join(new_path_raw, "sticky_notes_data.json")
                else:
                    new_path = new_path_raw
            if new_path != self.notes_data_path:
                self.notes_data_path = new_path if new_path != default_notes_data_path() else None
                if self.notes_manager is not None:
                    target = new_path or default_notes_data_path()
                    self.notes_manager.migrate_and_reload(target)

            new_tables_path = table_edit.text().strip()
            if new_tables_path != self.tables_save_path:
                self.tables_save_path = new_tables_path
                # notes follow the folder of the shared list file
                if new_tables_path and self.notes_manager is not None:
                    target = os.path.join(
                        os.path.dirname(new_tables_path), "sticky_notes_data.json"
                    )
                    if target != self.notes_manager.get_data_path():
                        self.notes_manager.switch_table_path(target)

            new_window_hotkey = window_edit.shortcut() or Shortcut(kind="none")
            new_notes_hotkey = notes_edit.shortcut() or Shortcut(kind="none")
            changed = (not new_window_hotkey.same_as(self.window_hotkey)
                       or not new_notes_hotkey.same_as(self.notes_hotkey))
            if changed:
                self.window_hotkey = new_window_hotkey
                self.notes_hotkey = new_notes_hotkey

            new_lang = lang_box.currentData()
            new_theme = theme_box.currentData()
            if new_lang != self.lang:
                self.set_language(new_lang)   # also updates the notes language
            self._apply_language()
            self.save_data()
            if new_theme != self.theme_name:
                self.set_theme(new_theme)
                # the dialog was styled for the old theme, redraw it in the new one
                dlg.setStyleSheet(build_stylesheet(self.colors))
            if changed:
                self._apply_hotkeys(announce=True, parent=dlg)
            dlg.accept()
        ok_btn.clicked.connect(on_ok)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)
        try:
            dlg.exec()
        finally:
            self._settings_open = False

    def show_desktop_popup(self):
        """Desktop launcher window (left-hand 🖥 / Desktop.png button)."""
        show_desktop_launcher(stylesheet=build_stylesheet(self.colors), parent=self)

    def _launch_helper(self, script_name, run_arg):
        """Start a helper tool (magnifier / psLauncher) as a separate process.

        Development: runs the .py file with the current Python interpreter.
        Frozen (.exe): the scripts are bundled INSIDE the executable, so the
        app re-runs itself with a --run-... switch and the child executes the
        bundled script instead of showing the main window. Returns the new
        Popen handle or None when the script cannot be found.
        """
        if getattr(sys, "frozen", False):
            if not os.path.exists(resource_path(script_name)):
                return None
            return subprocess.Popen(
                [sys.executable, run_arg],
                cwd=os.path.dirname(sys.executable),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        script_path = os.path.join(get_app_dir(), script_name)
        if not os.path.exists(script_path):
            return None
        return subprocess.Popen(
            [sys.executable, script_path],
            cwd=get_app_dir(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _stop_helper(self, proc):
        """Terminate a helper process and its whole child tree.

        The PyInstaller onefile bootloader runs the app in a second process,
        so killing only proc.pid would leave the actual helper window running.
        taskkill /T takes care of the full tree (also fine in development,
        where the process is the plain python.exe).
        """
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    capture_output=True,
                    timeout=5,
                )
                return
            except Exception:
                pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    def toggle_magnifier(self):
        """Start or stop the screen magnifier (magnifier.py).

        If no process is running, start it (bundled in the .exe when frozen,
        or via the Python interpreter in development). If it is already
        running, kill it and clear the handle.
        """
        if self._magnifier_proc is not None and self._magnifier_proc.poll() is None:
            self._stop_helper(self._magnifier_proc)
            self._magnifier_proc = None
            self.magnifier_btn.setProperty("active", "false")
        else:
            self._magnifier_proc = self._launch_helper("magnifier.py", "--run-magnifier")
            if self._magnifier_proc is None:
                QMessageBox.critical(
                    self,
                    self.t("magnifier_error_title"),
                    self.t("magnifier_error_msg").format(err="magnifier.py"),
                )
                return
            self.magnifier_btn.setProperty("active", "true")

        self.magnifier_btn.style().unpolish(self.magnifier_btn)
        self.magnifier_btn.style().polish(self.magnifier_btn)
    def toggle_pslauncher(self):
        """Start or stop psLauncher (pslauncher.py).

        If no process is running, start it (bundled in the .exe when frozen,
        or via the Python interpreter in development). If it is already
        running, terminate it (same toggle behaviour as the magnifier) and
        clear the handle.
        """
        if self._pslauncher_proc is not None and self._pslauncher_proc.poll() is None:
            self._stop_helper(self._pslauncher_proc)
            self._pslauncher_proc = None
            self.pslauncher_btn.setProperty("active", "false")
        else:
            self._pslauncher_proc = self._launch_helper("pslauncher.py", "--run-pslauncher")
            if self._pslauncher_proc is None:
                QMessageBox.critical(
                    self,
                    self.t("pslauncher_error_title"),
                    self.t("pslauncher_error_msg").format(err="pslauncher.py"),
                )
                return
            self.pslauncher_btn.setProperty("active", "true")

        self.pslauncher_btn.style().unpolish(self.pslauncher_btn)
        self.pslauncher_btn.style().polish(self.pslauncher_btn)

    def toggle_character_picker(self):
        """Start or stop the Character Picker (character_picker.py).

        Same toggle behaviour as the magnifier / psLauncher buttons: the
        first click starts the helper (bundled in the .exe when frozen), the
        next one stops it and clears the handle.
        """
        if self._charmap_proc is not None and self._charmap_proc.poll() is None:
            self._stop_helper(self._charmap_proc)
            self._charmap_proc = None
            self.charmap_btn.setProperty("active", "false")
        else:
            self._charmap_proc = self._launch_helper(
                "character_picker.py", "--run-character-picker"
            )
            if self._charmap_proc is None:
                QMessageBox.critical(
                    self,
                    self.t("charmap_error_title"),
                    self.t("charmap_error_msg").format(err="character_picker.py"),
                )
                return
            self.charmap_btn.setProperty("active", "true")

        self.charmap_btn.style().unpolish(self.charmap_btn)
        self.charmap_btn.style().polish(self.charmap_btn)

    def _about_app_icons(self):
        """Icon painters for the apps listed in About, keyed by app name.

        Reuses the exact artwork of the toolbar buttons, so the About list
        and the top bar show the same icons.  Each painter takes
        (colors, size) and returns a QPixmap."""
        return {
            "Character Picker": make_charmap_icon,
            "Desktop Launcher": make_desktop_icon_square,
            "Lupa": make_magnifier_icon,
            # make_pslauncher_icon only takes a size, so ignore the colours
            "psLauncher (mod)": lambda colors, size: make_pslauncher_icon(size),
            "Sticky Notes": make_sticky_notes_icon,
        }

    def show_about(self):
        c = self.colors
        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("about_title"))
        dlg.setStyleSheet(build_stylesheet(c))
        dlg.setFixedSize(420, 500)

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)

        # ---- Header card: logo, name, version pill, author, links ----
        header = QFrame()
        header.setObjectName("aboutHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(18, 16, 18, 14)
        head.setSpacing(3)

        logo = QLabel()
        logo.setPixmap(make_logo_pixmap(c, 52))
        head.addWidget(logo, alignment=Qt.AlignmentFlag.AlignHCenter)

        title = QLabel(ABOUT_INFO["name"])
        title.setObjectName("aboutTitle")
        head.addWidget(title, alignment=Qt.AlignmentFlag.AlignHCenter)

        version = QLabel(ABOUT_INFO["version"])
        version.setObjectName("aboutVersion")
        head.addWidget(version, alignment=Qt.AlignmentFlag.AlignHCenter)
        head.addSpacing(4)

        author = QLabel(ABOUT_INFO["author"])
        head.addWidget(author, alignment=Qt.AlignmentFlag.AlignHCenter)

        group = QLabel(ABOUT_INFO["group"])
        group.setObjectName("aboutGroup")
        head.addWidget(group, alignment=Qt.AlignmentFlag.AlignHCenter)
        head.addSpacing(6)

        github = ClickableLabel(ABOUT_INFO["github"], ABOUT_INFO["github"])
        github.setObjectName("aboutLink")
        head.addWidget(github, alignment=Qt.AlignmentFlag.AlignHCenter)

        email = ClickableLabel(ABOUT_INFO["email"], ABOUT_INFO["email"])
        email.setObjectName("aboutLink")
        head.addWidget(email, alignment=Qt.AlignmentFlag.AlignHCenter)

        outer.addWidget(header)

        # ---- Apps card: one row per tool (icon + name + description) ----
        apps_card = QFrame()
        apps_card.setObjectName("aboutAppsCard")
        card = QVBoxLayout(apps_card)
        card.setContentsMargins(10, 10, 10, 10)
        card.setSpacing(2)

        apps_header = QLabel(self.t("about_apps"))
        apps_header.setObjectName("aboutAppsHeader")
        apps_header.setContentsMargins(6, 0, 0, 4)
        card.addWidget(apps_header)

        painters = self._about_app_icons()
        for app_name, app_desc in ABOUT_APPS:
            name_lbl = QLabel(app_name)
            name_lbl.setObjectName("aboutAppName")
            desc_lbl = QLabel(app_desc)
            desc_lbl.setObjectName("aboutAppDesc")

            icon_lbl = QLabel()
            icon_lbl.setObjectName("aboutAppIcon")
            icon_lbl.setFixedSize(30, 30)
            make_icon = painters.get(app_name)
            if make_icon is not None:
                pm = QPixmap(30, 30)
                pm.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pm)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                draw_icon(painter, make_icon, 30, c, scale=0.62)
                painter.end()
                icon_lbl.setPixmap(pm)
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            row = QFrame()
            row.setObjectName("aboutAppRow")
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(4, 3, 4, 3)
            row_l.setSpacing(10)
            row_l.addWidget(icon_lbl)

            text_box = QVBoxLayout()
            text_box.setSpacing(0)
            text_box.addWidget(name_lbl)
            text_box.addWidget(desc_lbl)
            row_l.addLayout(text_box, 1)

            row.setToolTip(f"{app_name} – {app_desc}")
            card.addWidget(row)

        outer.addWidget(apps_card)

        # ---- Footer: licence + OK ----
        footer = QHBoxLayout()
        license_label = QLabel(ABOUT_INFO["license"])
        license_label.setObjectName("aboutLicense")
        footer.addWidget(license_label)
        footer.addStretch(1)

        close_btn = QPushButton("OK")
        close_btn.setObjectName("accentBtn")
        close_btn.setFixedWidth(96)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(dlg.accept)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

        dlg.exec()

    # ------------------------------------------------------------------
    # Intelligent split helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_bullet_prefix(line: str) -> str:
        # remove common bullet / numbering prefixes: "-", "•", "*", "1.", "1)"
        line = line.lstrip()
        bullet_patterns = [
            r"^[-•*]\s+",
            r"^\d+\.\s+",
            r"^\d+\)\s+",
        ]
        for pat in bullet_patterns:
            line = re.sub(pat, "", line)
        return line.strip()

    def _smart_split_text(self, text: str) -> list[str]:
        # normalize whitespace
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)

        # if there are many semicolons or commas, treat them as separators
        sep_candidates = []
        if text.count(";") >= 3:
            sep_candidates.append(";")
        if text.count(",") >= 3:
            sep_candidates.append(",")

        if sep_candidates:
            # split on chosen separators + newlines
            pattern = r"[\n" + "".join(re.escape(s) for s in sep_candidates) + r"]+"
            raw_parts = re.split(pattern, text)
        else:
            # default: split by newlines
            raw_parts = text.split("\n")

        lines = []
        for ln in raw_parts:
            ln = self._strip_bullet_prefix(ln)
            if ln:
                lines.append(ln)
        return lines

    # ------------------------------------------------------------------
    # Core actions
    # ------------------------------------------------------------------
    def split_to_list(self):
        text = self.bulk_text.toPlainText()
        lines = self._smart_split_text(text)
        for i in range(NUM_ITEMS):
            self.entries[i].blockSignals(True)
            self.entries[i].setText(lines[i] if i < len(lines) else "")
            self.entries[i].blockSignals(False)
        self._update_status()
        self.save_data()

    def copy_item(self, idx):
        value = self.entries[idx].text()
        if not value:
            return
        QApplication.clipboard().setText(value)

        btn = self.copy_buttons[idx]
        btn.setText("✓")
        btn.setToolTip(self.t("copied_btn"))
        btn.setProperty("state", "success")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        QTimer.singleShot(1000, lambda: self._restore_copy_btn(idx))

    def _restore_copy_btn(self, idx):
        btn = self.copy_buttons[idx]
        btn.setText("📋")
        btn.setToolTip(self.t("copy_btn"))
        btn.setProperty("state", "")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def copy_all(self):
        values = [e.text() for e in self.entries if e.text().strip() != ""]
        if not values:
            return
        QApplication.clipboard().setText("\n".join(values))

        self.copy_all_btn.setText("✓")
        self.copy_all_btn.setToolTip(self.t("copied_all_btn"))
        self.copy_all_btn.setProperty("state", "success")
        self.copy_all_btn.style().unpolish(self.copy_all_btn)
        self.copy_all_btn.style().polish(self.copy_all_btn)
        QTimer.singleShot(1000, self._restore_copy_all_btn)

    def _restore_copy_all_btn(self):
        self.copy_all_btn.setText("📋")
        self.copy_all_btn.setToolTip(self.t("copy_all_btn"))
        self.copy_all_btn.setProperty("state", "")
        self.copy_all_btn.style().unpolish(self.copy_all_btn)
        self.copy_all_btn.style().polish(self.copy_all_btn)

    def clear_item(self, idx):
        self.entries[idx].clear()
        self._update_status()
        self.save_data()

    def clear_all(self):
        self.bulk_text.clear()
        for entry in self.entries:
            entry.clear()
        self._update_status()
        self.save_data()

    def export_to_file(self):
        """Save the 15 tables to the file set in Settings.

        With a location configured it is used after a confirmation; with an
        empty location the file dialog is shown on every save and opens in the
        last location that was used."""
        values = [e.text() for e in self.entries if e.text().strip() != ""]
        if not values:
            return

        path = ""
        if self.tables_save_path:
            answer = QMessageBox.question(
                self,
                self.t("save_confirm_title"),
                self.t("save_confirm_msg").format(path=self.tables_save_path),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                path = self.tables_save_path

        if path:
            # the location is now "the last location used", whether it came from
            # Settings or from a dialog picked earlier
            LAST_SAVE_DIR["dir"] = os.path.dirname(path)

        if not path:
            default_dir = LAST_SAVE_DIR["dir"] or get_app_dir()
            path, _ = QFileDialog.getSaveFileName(
                self,
                self.t("export_dialog_title"),
                os.path.join(default_dir, self.t("settings_table_file")),
                self.t("file_filter_txt"),
            )
            if not path:
                return
            LAST_SAVE_DIR["dir"] = os.path.dirname(path)
            # remember the location so the next save only needs a confirmation
            self.tables_save_path = path
            self._apply_language()
            self.save_data()

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(values))
        except Exception as err:
            QMessageBox.critical(
                self,
                self.t("export_error_title"),
                self.t("export_error_msg").format(err=str(err)),
            )
            return

        self._set_status(self.t("status_exported"), "saved", 1500)

    def import_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, self.t("import_dialog_title"), "", self.t("file_filter_txt")
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as err:
            QMessageBox.critical(
                self,
                self.t("import_error_title"),
                self.t("import_error_msg").format(err=str(err)),
            )
            return

        self.bulk_text.blockSignals(True)
        self.bulk_text.setPlainText(content)
        self.bulk_text.blockSignals(False)
        self.split_to_list()
        self._set_status(self.t("status_imported"), "saved", 1500)

    # ------------------------------------------------------------------
    # Data persistence
    # ------------------------------------------------------------------
    def _set_status(self, text, state="", timeout=0):
        """Central place for status label updates.

        Sets the text, applies the style property, repolishes the widget so the
        new state takes effect, and optionally starts the revert timer.
        """
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        if timeout:
            self._status_timer.start(timeout)

    def _on_entry_change(self):
        self._update_status()
        self._schedule_save()

    def _on_bulk_change(self):
        self._schedule_save()

    def _schedule_save(self):
        self._save_timer.start(500)

    def _update_status(self):
        filled = sum(1 for e in self.entries if e.text().strip() != "")
        self._set_status(self.t("status_filled").format(n=filled, total=NUM_ITEMS))

    def _revert_status(self):
        self._update_status()

    def save_data(self):
        data = {
            "lang": self.lang,
            "theme": self.theme_name,
            "always_on_top": self.always_on_top,
            "notes_data_path": self.notes_data_path,
            "tables_save_path": self.tables_save_path,
            "window_hotkey": self.window_hotkey.to_dict(),
            "notes_hotkey": self.notes_hotkey.to_dict(),
            "last_save_dir": LAST_SAVE_DIR["dir"],
            "bulk_text": self.bulk_text.toPlainText(),
            "items": [e.text() for e in self.entries],
        }
        try:
            with open(DATA_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as err:
            self._show_status_error(self.t("status_save_error").format(err=err))
            return
        self._set_status(self.t("status_saved"), "saved", 1500)

    def _show_status_error(self, message):
        """Surface a persistence/load failure on the status label instead of
        failing silently, then fall back to the normal item-count text."""
        self._set_status(message, "error", 6000)

    def _read_data_file(self):
        """Read and parse text_list_data.json.

        Returns the parsed dict, or None when the file is missing or cannot be
        read/parsed. Any failure is surfaced on the status label so it never
        goes unnoticed.
        """
        if not os.path.exists(DATA_PATH):
            return None
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            self._show_status_error(self.t("status_load_error").format(err=err))
            return None
        if not isinstance(data, dict):
            self._show_status_error(self.t("status_load_error").format(err="invalid data"))
            return None
        return data

    def load_data(self):
        data = self._read_data_file()
        if data is None:
            return

        bulk = data.get("bulk_text", "")
        if not isinstance(bulk, str):
            bulk = ""
        self.bulk_text.blockSignals(True)
        self.bulk_text.setPlainText(bulk)
        self.bulk_text.blockSignals(False)

        items = data.get("items", [])
        if not isinstance(items, list):
            items = []
        for i in range(NUM_ITEMS):
            value = items[i] if i < len(items) else ""
            # a hand-edited file may hold numbers/None where strings belong;
            # coerce so setText can never raise on a malformed entry
            self.entries[i].blockSignals(True)
            self.entries[i].setText(value if isinstance(value, str) else str(value))
            self.entries[i].blockSignals(False)

        self._update_status()

    def _load_settings(self):
        data = self._read_data_file()
        if data is None:
            return

        # validate against what the program actually supports, so a hand-edited
        # or truncated json file can never leave the UI in a broken state
        lang = data.get("lang")
        if lang in STRINGS:
            self.lang = lang
        theme = data.get("theme")
        if theme in THEMES:
            self.theme_name = theme
        self.always_on_top = bool(data.get("always_on_top", self.always_on_top))
        notes_path = data.get("notes_data_path", self.notes_data_path)
        if isinstance(notes_path, str) or notes_path is None:
            self.notes_data_path = notes_path
        if not self._settings_loaded:
            tables_path = data.get("tables_save_path", "")
            self.tables_save_path = tables_path if isinstance(tables_path, str) else ""
            window_default, notes_default = default_hotkeys()
            self.window_hotkey = _load_hotkey(data.get("window_hotkey"), window_default)
            self.notes_hotkey = _load_hotkey(data.get("notes_hotkey"), notes_default)
            # only seed the remembered folder on startup - a later save_data()
            # must not overwrite the location the user just picked
            LAST_SAVE_DIR["dir"] = data.get("last_save_dir", "")
        self._settings_loaded = True
        if self.always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)


def main():
    # Helper dispatch: DesktopMate.exe --run-magnifier / --run-pslauncher /
    # --run-character-picker executes the script bundled inside the exe instead
    # of the main window (used by the magnifier / psLauncher / character picker
    # buttons when frozen).
    for arg in sys.argv[1:]:
        script = HELPER_RUN_ARGS.get(arg)
        if script is None:
            continue
        script_path = resource_path(script)
        if not os.path.exists(script_path):
            # A stripped/incomplete build may ship without the bundled helper.
            # Report it and exit non-zero instead of letting runpy raise.
            message = "Helper script not found:\n{}\n\nReinstall DeskMate or \nrun it from the source folder.".format(script_path)
            print(message, file=sys.stderr)
            if QApplication.instance() is None:
                app = QApplication(sys.argv)
            QMessageBox.critical(None, "DeskMate", message)
            sys.exit(2)
        if getattr(sys, "frozen", False):
            base = getattr(sys, "_MEIPASS", None)
            if base and base not in sys.path:
                sys.path.insert(0, base)   # so e.g. "import sandbox" works
        runpy.run_path(script_path, run_name="__main__")
        return

    app = QApplication(sys.argv)
    win = TextListApp()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
