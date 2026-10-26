"""
Keyboard and mouse shortcuts for Text List Tool - polsoft.ITS

Two independent shortcuts can be configured:
  * show / hide the main window
  * show / hide the sticky notes

A shortcut may be a key combination (optionally registered system-wide through
the Windows RegisterHotKey API, so it also works when another app has focus) or
a mouse gesture (a click / double click with optional modifier keys).

Author: Sebastian Januchowski / polsoft.ITS Group
"""

import ctypes
import ctypes.wintypes as wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, QObject, Qt, pyqtSignal

# Modifier bits used by the Windows RegisterHotKey API
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Qt.Key -> Windows virtual-key code (only the ranges that matter here)
_VK_SPECIAL = {
    Qt.Key.Key_Space: 0x20,
    Qt.Key.Key_Tab: 0x09,
    Qt.Key.Key_Backspace: 0x08,
    Qt.Key.Key_Return: 0x0D,
    Qt.Key.Key_Enter: 0x0D,
    Qt.Key.Key_Escape: 0x1B,
    Qt.Key.Key_Insert: 0x2D,
    Qt.Key.Key_Delete: 0x2E,
    Qt.Key.Key_Home: 0x24,
    Qt.Key.Key_End: 0x23,
    Qt.Key.Key_PageUp: 0x21,
    Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_Left: 0x25,
    Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27,
    Qt.Key.Key_Down: 0x28,
    Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_Print: 0x2C,
}
# VK codes for the function keys
for _i in range(1, 25):
    _VK_SPECIAL[getattr(Qt.Key, f"Key_F{_i}")] = 0x6F + _i  # F1 -> 0x70

# Modifier keys that are never the "main" key of a shortcut
_MODIFIER_KEYS = (
    Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt,
    Qt.Key.Key_Meta, Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
    Qt.Key.Key_unknown,
)

MOUSE_NAMES = {
    Qt.MouseButton.LeftButton: "left",
    Qt.MouseButton.MiddleButton: "middle",
    Qt.MouseButton.RightButton: "right",
}
MOUSE_BUTTONS = {name: button for button, name in MOUSE_NAMES.items()}


def _mods_to_int(mods):
    return sorted(int(m.value) for m in mods)


def _mods_from_int(values):
    out = set()
    for value in values or []:
        try:
            out.add(Qt.KeyboardModifier(value))
        except ValueError:
            continue
    return out


def qt_key_to_vk(key):
    """Return the Windows virtual-key code for a Qt key, or None."""
    key = int(key)
    if key in _VK_SPECIAL:
        return _VK_SPECIAL[key]
    # letters and digits map 1:1 onto their ASCII value
    if (0x41 <= key <= 0x5A) or (0x30 <= key <= 0x39):
        return key
    if 0x60 <= key <= 0x69:      # numeric keypad 0-9
        return key - 0x60 + 0x60
    return None


class Shortcut:
    """One configurable shortcut: a key combo or a mouse gesture."""

    def __init__(self, kind="key", key=None, mods=None,
                 button=None, double=False, mmods=None):
        self.kind = kind                  # "key" | "mouse" | "none"
        self.key = key                    # Qt.Key value
        self.mods = set(mods or ())       # Qt.KeyboardModifier values
        self.button = button              # Qt.MouseButton value
        self.double = bool(double)
        self.mmods = set(mmods or ())     # Qt.KeyboardModifier values

    # -- serialisation -------------------------------------------------
    def to_dict(self):
        return {
            "kind": self.kind,
            "key": int(self.key) if self.key is not None else None,
            "mods": _mods_to_int(self.mods),
            "button": self.button.value if self.button is not None else None,
            "double": self.double,
            "mmods": _mods_to_int(self.mmods),
        }

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls(kind="none")
        kind = data.get("kind")
        if kind not in ("key", "mouse"):
            return cls(kind="none")
        button = data.get("button")
        try:
            button = Qt.MouseButton(button) if button is not None else None
        except ValueError:
            button = None
        key = data.get("key")
        try:
            key = int(key) if key is not None else None
        except (TypeError, ValueError):
            key = None
        return cls(
            kind=kind,
            key=key,
            mods=_mods_from_int(data.get("mods")),
            button=button,
            double=bool(data.get("double", False)),
            mmods=_mods_from_int(data.get("mmods")),
        )

    def is_set(self):
        if self.kind == "key":
            return self.key is not None
        if self.kind == "mouse":
            return self.button is not None
        return False

    # -- building ------------------------------------------------------
    @classmethod
    def from_key_event(cls, event):
        """Build a key shortcut from a key press; None if it is only modifiers."""
        key = event.key()
        if key in _MODIFIER_KEYS or qt_key_to_vk(key) is None:
            return None
        return cls(kind="key", key=int(key), mods=set(event.modifiers()))

    @classmethod
    def from_mouse_event(cls, event):
        button = event.button()
        if button not in MOUSE_NAMES:
            return None
        return cls(
            kind="mouse",
            button=button,
            double=False,
            mmods=set(event.modifiers()),
        )

    # -- matching ------------------------------------------------------
    def matches_key_event(self, event):
        if self.kind != "key" or self.key is None:
            return False
        return int(event.key()) == int(self.key) and set(event.modifiers()) == set(self.mods)

    def matches_mouse_event(self, event, double):
        if self.kind != "mouse" or self.button is None:
            return False
        return (
            event.button() == self.button
            and bool(double) == self.double
            and set(event.modifiers()) == set(self.mmods)
        )

    # -- display -------------------------------------------------------
    def describe(self, tr):
        """Human readable form; `tr` is a callable translating a string key."""
        if not self.is_set():
            return tr("hotkey_none")
        parts = []
        if self.kind == "mouse":
            for mod, name in (
                (Qt.KeyboardModifier.ControlModifier, "hotkey_ctrl"),
                (Qt.KeyboardModifier.AltModifier, "hotkey_alt"),
                (Qt.KeyboardModifier.ShiftModifier, "hotkey_shift"),
                (Qt.KeyboardModifier.MetaModifier, "hotkey_win"),
            ):
                if mod in self.mmods:
                    parts.append(tr(name))
            label = tr("mouse_" + MOUSE_NAMES.get(self.button, "left"))
            if self.double:
                label = f"{tr('mouse_double')} {label}".strip()
            parts.append(label)
            return tr("hotkey_mouse").format(buttons=" + ".join(parts))
        for mod, name in (
            (Qt.KeyboardModifier.ControlModifier, "hotkey_ctrl"),
            (Qt.KeyboardModifier.AltModifier, "hotkey_alt"),
            (Qt.KeyboardModifier.ShiftModifier, "hotkey_shift"),
            (Qt.KeyboardModifier.MetaModifier, "hotkey_win"),
        ):
            if mod in self.mods:
                parts.append(tr(name))
        parts.append(_key_name(self.key))
        return " + ".join(parts)

    def same_as(self, other):
        return self.to_dict() == other.to_dict()


def _key_name(key):
    if key is None:
        return ""
    try:
        text = Qt.Key(int(key)).name  # e.g. "Key_Space"
    except (ValueError, TypeError):
        return "?"
    if text.startswith("Key_"):
        text = text[4:]
    if text.startswith("F") and text[1:].isdigit():
        return text
    if len(text) == 1:
        return text.upper()
    # split CamelCase so "PageUp" reads as "Page Up"
    out, prev = "", ""
    for ch in text:
        if prev.islower() and ch.isupper():
            out += " "
        out += ch
        prev = ch
    return out


def _mods_to_winapi(mods):
    """Translate Qt modifier flags into the bits RegisterHotKey expects.

    The two enums share names but not values, so they must be mapped explicitly.
    """
    out = MOD_NOREPEAT
    if Qt.KeyboardModifier.AltModifier in mods:
        out |= MOD_ALT
    if Qt.KeyboardModifier.ControlModifier in mods:
        out |= MOD_CONTROL
    if Qt.KeyboardModifier.ShiftModifier in mods:
        out |= MOD_SHIFT
    if Qt.KeyboardModifier.MetaModifier in mods:
        out |= MOD_WIN
    return out


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """Registers the shortcuts, system-wide where possible, and fires signals."""

    triggered_window = pyqtSignal()
    triggered_notes = pyqtSignal()

    #: id -> (shortcut, signal) for the currently registered global hotkeys
    _ID_WINDOW = 0xA51
    _ID_NOTES = 0xA52

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.window_shortcut = Shortcut(kind="none")
        self.notes_shortcut = Shortcut(kind="none")
        self._registered = {}     # id -> Shortcut
        self._failed = []         # shortcuts the OS refused

    # -- registration --------------------------------------------------
    def apply(self, window_shortcut, notes_shortcut):
        """Replace both shortcuts and (re)register the global ones.

        Returns the list of shortcuts the OS refused to register; they keep
        working while the application has focus."""
        self.unregister_all()
        self.window_shortcut = window_shortcut or Shortcut(kind="none")
        self.notes_shortcut = notes_shortcut or Shortcut(kind="none")
        self._failed = []
        for hotkey_id, shortcut in (
            (self._ID_WINDOW, self.window_shortcut),
            (self._ID_NOTES, self.notes_shortcut),
        ):
            if not shortcut.is_set() or shortcut.kind != "key":
                continue
            if self._register(hotkey_id, shortcut):
                self._registered[hotkey_id] = shortcut
            else:
                self._failed.append(shortcut)
        return list(self._failed)

    def unregister_all(self):
        if not _WINDOWS:
            self._registered.clear()
            return
        user32 = ctypes.windll.user32
        for hotkey_id in list(self._registered):
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
        self._registered.clear()

    def _register(self, hotkey_id, shortcut):
        if not _WINDOWS:
            return False
        vk = qt_key_to_vk(shortcut.key)
        if vk is None:
            return False
        mods = _mods_to_winapi(shortcut.mods)
        user32 = ctypes.windll.user32
        try:
            user32.RegisterHotKey.restype = wintypes.BOOL
            user32.RegisterHotKey.argtypes = [
                wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
            ]
            return bool(user32.RegisterHotKey(None, hotkey_id, mods, vk))
        except Exception as exc:
            self._last_error = "%s: %s" % (type(exc).__name__, exc)
            return False

    # -- event handling ------------------------------------------------
    def handle_key_event(self, event):
        """True when the event matched one of the shortcuts (and was consumed)."""
        for shortcut, signal in (
            (self.window_shortcut, self.triggered_window),
            (self.notes_shortcut, self.triggered_notes),
        ):
            if shortcut.kind == "key" and shortcut.matches_key_event(event):
                signal.emit()
                return True
        return False

    def handle_mouse_event(self, event, double=False, owners=None):
        """`owners` maps an owner key to a label, used only for reporting."""
        for shortcut, signal in (
            (self.window_shortcut, self.triggered_window),
            (self.notes_shortcut, self.triggered_notes),
        ):
            if shortcut.kind == "mouse" and shortcut.matches_mouse_event(event, double):
                signal.emit()
                return True
        return False

    def mouse_owners(self):
        """Mouse shortcuts are filtered system-wide, so expose their signatures."""
        out = []
        if self.window_shortcut.kind == "mouse" and self.window_shortcut.is_set():
            out.append(self.window_shortcut)
        if self.notes_shortcut.kind == "mouse" and self.notes_shortcut.is_set():
            out.append(self.notes_shortcut)
        return out

    # -- native event filter -------------------------------------------
    def nativeEventFilter(self, event_type, message):
        """Catch WM_HOTKEY; returns (handled, result)."""
        if event_type != b"windows_generic_MSG" or not _WINDOWS:
            return False, 0
        try:
            msg = ctypes.cast(
                int(message.__int__()), ctypes.POINTER(wintypes.MSG)
            ).contents
        except Exception:
            return False, 0
        if msg.message != 0x0312:  # WM_HOTKEY
            return False, 0
        if msg.wParam == self._ID_WINDOW:
            self.triggered_window.emit()
        elif msg.wParam == self._ID_NOTES:
            self.triggered_notes.emit()
        else:
            return False, 0
        return True, 0


_WINDOWS = ctypes.windll is not None and hasattr(ctypes, "windll") and \
    __import__("sys").platform.startswith("win")