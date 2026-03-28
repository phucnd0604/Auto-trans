from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from autotrans.config import AppConfig
from autotrans.models import Frame, Rect

try:
    import win32con
    import win32gui
    import win32ui
    from ctypes import windll
except ImportError:  # pragma: no cover
    win32con = None
    win32gui = None
    win32ui = None
    windll = None

try:
    from mss import mss
except ImportError:  # pragma: no cover
    mss = None


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    title: str
    rect: Rect


class CaptureService(Protocol):
    def list_windows(self) -> list[WindowInfo]:
        ...

    def capture_window(self, hwnd: int) -> Frame | None:
        ...


class WindowsWindowCapture:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()

    def list_windows(self) -> list[WindowInfo]:
        if win32gui is None:
            return []

        windows: list[WindowInfo] = []

        def callback(hwnd: int, _: int) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = win32gui.GetWindowText(hwnd)
            if not title:
                return
            if "autotrans" in title.lower():
                return
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            if ex_style & win32con.WS_EX_TOOLWINDOW:
                return
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            rect = Rect(x=left, y=top, width=right - left, height=bottom - top)
            if rect.width < 120 or rect.height < 120:
                return
            windows.append(WindowInfo(hwnd=hwnd, title=title, rect=rect))

        win32gui.EnumWindows(callback, 0)
        return sorted(windows, key=lambda item: item.title.lower())

    def _capture_with_printwindow(self, hwnd: int, rect: Rect) -> np.ndarray | None:
        if win32gui is None or win32ui is None or windll is None:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        if not hwnd_dc:
            return None

        mfc_dc = save_dc = bitmap = None
        try:
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()
            bitmap = win32ui.CreateBitmap()
            bitmap.CreateCompatibleBitmap(mfc_dc, rect.width, rect.height)
            save_dc.SelectObject(bitmap)

            flags = 0x00000002
            result = windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), flags)
            if result != 1:
                return None

            bmpinfo = bitmap.GetInfo()
            bmpstr = bitmap.GetBitmapBits(True)
            image = np.frombuffer(bmpstr, dtype=np.uint8)
            image = image.reshape((bmpinfo["bmHeight"], bmpinfo["bmWidth"], 4))
            image = image[:, :, :3]
            return np.ascontiguousarray(image)
        finally:
            if bitmap is not None:
                win32gui.DeleteObject(bitmap.GetHandle())
            if save_dc is not None:
                save_dc.DeleteDC()
            if mfc_dc is not None:
                mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hwnd_dc)

    def _capture_with_mss(self, rect: Rect) -> np.ndarray | None:
        if mss is None:
            return None
        with mss() as sct:
            grabbed = sct.grab(
                {
                    "left": rect.x,
                    "top": rect.y,
                    "width": rect.width,
                    "height": rect.height,
                }
            )
            return np.asarray(grabbed)[..., :3]

    def capture_window(self, hwnd: int) -> Frame | None:
        if win32gui is None:
            return None

        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        rect = Rect(x=left, y=top, width=right - left, height=bottom - top)
        if rect.width <= 0 or rect.height <= 0:
            return None

        image = None
        if self._config.capture_backend == "printwindow":
            image = self._capture_with_printwindow(hwnd, rect)
            if image is None:
                image = self._capture_with_mss(rect)
        else:
            image = self._capture_with_mss(rect)
            if image is None:
                image = self._capture_with_printwindow(hwnd, rect)

        if image is None:
            return None

        return Frame(
            image=image,
            timestamp=time.time(),
            window_rect=rect,
        )
