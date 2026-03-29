from __future__ import annotations

import ctypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt", _POINT),
        ("lPrivate", ctypes.c_uint),
    ]


class GlobalHotkeyManager(QObject, QAbstractNativeEventFilter):
    hotkey_pressed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._user32 = getattr(ctypes, "windll", None)
        self._registered: dict[int, str] = {}

    @staticmethod
    def _parse_shortcut(shortcut: str) -> tuple[int, int]:
        modifiers = 0
        key = 0
        for chunk in (part.strip().lower() for part in shortcut.split("+") if part.strip()):
            if chunk in {"ctrl", "control"}:
                modifiers |= MOD_CONTROL
            elif chunk == "shift":
                modifiers |= MOD_SHIFT
            elif chunk == "alt":
                modifiers |= MOD_ALT
            elif chunk in {"win", "meta"}:
                modifiers |= MOD_WIN
            elif len(chunk) == 1 and "a" <= chunk <= "z":
                key = ord(chunk.upper())
            elif chunk == "insert":
                key = 0x2D
            elif chunk.startswith("f") and chunk[1:].isdigit():
                key = 0x70 + int(chunk[1:]) - 1
        if key <= 0:
            raise ValueError(f"Unsupported hotkey: {shortcut}")
        return modifiers, key

    def register_hotkey(self, hotkey_id: int, shortcut: str, action_name: str) -> bool:
        if self._user32 is None:
            return False
        modifiers, key = self._parse_shortcut(shortcut)
        ok = bool(self._user32.user32.RegisterHotKey(None, hotkey_id, modifiers, key))
        if ok:
            self._registered[hotkey_id] = action_name
        return ok

    def unregister_all(self) -> None:
        if self._user32 is None:
            return
        for hotkey_id in list(self._registered):
            self._user32.user32.UnregisterHotKey(None, hotkey_id)
        self._registered.clear()

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        if event_type not in {b"windows_generic_MSG", "windows_generic_MSG"} or self._user32 is None:
            return False, 0
        msg = ctypes.cast(message, ctypes.POINTER(_MSG)).contents
        if msg.message != WM_HOTKEY:
            return False, 0
        action_name = self._registered.get(int(msg.wParam))
        if action_name:
            self.hotkey_pressed.emit(action_name)
            return True, 0
        return False, 0

    def __del__(self) -> None:
        self.unregister_all()
