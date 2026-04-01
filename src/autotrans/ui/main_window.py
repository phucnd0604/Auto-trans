from __future__ import annotations

import ctypes
import threading
import time

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from autotrans.config import AppConfig
from autotrans.models import OverlayItem, OverlayStyle, Rect, VisibilityState
from autotrans.services.capture import WindowInfo, WindowsWindowCapture
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.ui.global_hotkeys import GlobalHotkeyManager
from autotrans.ui.overlay import OverlayWindow


class MainWindow(QMainWindow):
    pipeline_result = Signal(list)
    pipeline_error = Signal(str)
    deep_translation_preview = Signal(int, object, list)
    deep_translation_result = Signal(int, list)
    deep_translation_error = Signal(int, str)
    _VK_CONTROL = 0x11
    _VK_SHIFT = 0x10
    _VK_INSERT = 0x2D
    _VK_O = 0x4F
    _VK_P = 0x50

    def __init__(
        self,
        config: AppConfig,
        capture_service: WindowsWindowCapture,
        orchestrator: PipelineOrchestrator,
        overlay: OverlayWindow,
        global_hotkeys: GlobalHotkeyManager | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.capture_service = capture_service
        self.orchestrator = orchestrator
        self.overlay = overlay
        self.global_hotkeys = global_hotkeys
        self._selected_hwnd: int | None = None
        self._windows: list[WindowInfo] = []
        self._running = False
        self._processing = False
        self._rerun_requested = False
        self._overlay_enabled = True
        self._overlay_temporarily_hidden = False
        self._deep_translation_active = False
        self._deep_translation_visible = False
        self._deep_translation_processing = False
        self._deep_translation_job_id = 0
        self._deep_translation_started_at = 0.0
        self._deep_translation_stage = ""
        self._hotkey_poll_state = {"pause": False, "overlay": False, "deep": False}
        self._user32 = getattr(ctypes, "windll", None)

        self.setWindowTitle("AutoTrans MVP")
        self.resize(700, 450)

        self.window_list = QListWidget()
        self.refresh_button = QPushButton("Refresh Windows")
        self.start_button = QPushButton("Start")
        self.overlay_button = QPushButton("Hide Overlay")
        self.deep_translate_button = QPushButton("Deep Translate")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["fast", "balanced", "high_quality"])
        self.mode_combo.setCurrentText(config.mode)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 48)
        self.font_size_spin.setValue(config.font_size)
        self.status_label = QLabel("Select a game window, then click Start.")
        self.stats_label = QLabel("Idle")
        self.hotkey_label = QLabel(
            "Hotkeys: Ctrl+Shift+P pause/resume, Ctrl+Shift+O overlay, Insert deep translate"
        )

        controls_layout = QFormLayout()
        controls_layout.addRow("Mode", self.mode_combo)
        controls_layout.addRow("Font Size", self.font_size_spin)

        button_row = QHBoxLayout()
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.overlay_button)
        button_row.addWidget(self.deep_translate_button)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Detected windows"))
        layout.addWidget(self.window_list)
        layout.addLayout(controls_layout)
        layout.addLayout(button_row)
        layout.addWidget(self.hotkey_label)
        layout.addWidget(QLabel("Status"))
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("Pipeline stats"))
        layout.addWidget(self.stats_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.refresh_button.clicked.connect(self.refresh_windows)
        self.start_button.clicked.connect(self.toggle_pipeline)
        self.overlay_button.clicked.connect(self.toggle_overlay)
        self.deep_translate_button.clicked.connect(self.toggle_deep_translation)
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self.window_list.itemSelectionChanged.connect(self._on_window_selected)
        self.pipeline_result.connect(self._apply_pipeline_result)
        self.pipeline_error.connect(self._apply_pipeline_error)
        self.deep_translation_preview.connect(self._apply_deep_translation_preview)
        self.deep_translation_result.connect(self._apply_deep_translation_result)
        self.deep_translation_error.connect(self._apply_deep_translation_error)

        self.capture_timer = QTimer(self)
        capture_interval_ms = max(int(round(1000.0 / max(config.capture_fps, 0.01))), 200)
        self.capture_timer.setInterval(capture_interval_ms)
        self.capture_timer.timeout.connect(self._tick_pipeline)

        self.follow_timer = QTimer(self)
        self.follow_timer.setInterval(100)
        self.follow_timer.timeout.connect(self._sync_overlay_geometry)

        self.deep_translation_watchdog = QTimer(self)
        self.deep_translation_watchdog.setInterval(500)
        self.deep_translation_watchdog.timeout.connect(self._check_deep_translation_timeout)

        self.hotkey_poll_timer = QTimer(self)
        self.hotkey_poll_timer.setInterval(75)
        self.hotkey_poll_timer.timeout.connect(self._poll_global_hotkeys)
        self.hotkey_poll_timer.start()

        self.pause_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.pause_shortcut.activated.connect(self.toggle_pipeline)
        self.overlay_shortcut = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        self.overlay_shortcut.activated.connect(self.toggle_overlay)
        self.deep_translate_shortcut = QShortcut(QKeySequence("Insert"), self)
        self.deep_translate_shortcut.activated.connect(self.toggle_deep_translation)
        self._register_global_hotkeys()

        self.refresh_windows()

    def _register_global_hotkeys(self) -> None:
        if self.global_hotkeys is None:
            return
        self.global_hotkeys.hotkey_pressed.connect(self._handle_global_hotkey)
        results = {
            "pause": self.global_hotkeys.register_hotkey(1, "Ctrl+Shift+P", "pause"),
            "overlay": self.global_hotkeys.register_hotkey(2, "Ctrl+Shift+O", "overlay"),
            "deep": self.global_hotkeys.register_hotkey(3, "Insert", "deep"),
        }
        failed = [name for name, ok in results.items() if not ok]
        if failed:
            self.status_label.setText(f"Global hotkey unavailable: {', '.join(failed)}")

    def _handle_global_hotkey(self, action_name: str) -> None:
        print(f"[AutoTrans] Global hotkey pressed: {action_name}", flush=True)
        if action_name == "pause":
            self.toggle_pipeline()
        elif action_name == "overlay":
            self.toggle_overlay()
        elif action_name == "deep":
            self.toggle_deep_translation()

    def _is_virtual_key_pressed(self, key_code: int) -> bool:
        if self._user32 is None:
            return False
        return bool(self._user32.user32.GetAsyncKeyState(key_code) & 0x8000)

    def _poll_global_hotkeys(self) -> None:
        if self._user32 is None:
            return
        ctrl_down = self._is_virtual_key_pressed(self._VK_CONTROL)
        shift_down = self._is_virtual_key_pressed(self._VK_SHIFT)
        combos = {
            "pause": ctrl_down and shift_down and self._is_virtual_key_pressed(self._VK_P),
            "overlay": ctrl_down and shift_down and self._is_virtual_key_pressed(self._VK_O),
            "deep": self._is_virtual_key_pressed(self._VK_INSERT),
        }
        for action_name, is_down in combos.items():
            was_down = self._hotkey_poll_state.get(action_name, False)
            if is_down and not was_down:
                print(f"[AutoTrans] Polled hotkey pressed: {action_name}", flush=True)
                self._handle_global_hotkey(action_name)
            self._hotkey_poll_state[action_name] = is_down

    @staticmethod
    def _looks_like_non_game_window(title: str) -> bool:
        lowered = title.lower()
        markers = ["screenshot", "photos", "file explorer", "explorer", "snipping tool"]
        return any(marker in lowered for marker in markers)

    def _suggested_game_window(self) -> WindowInfo | None:
        game_like = [
            window
            for window in self._windows
            if not self._looks_like_non_game_window(window.title) and "codex" not in window.title.lower()
        ]
        if not game_like:
            return None
        return max(game_like, key=lambda window: window.rect.width * window.rect.height)

    def refresh_windows(self) -> None:
        self._windows = self.capture_service.list_windows()
        self.window_list.clear()
        selected_index = -1
        for window in self._windows:
            item = QListWidgetItem(f"{window.title} [{window.rect.width}x{window.rect.height}]")
            item.setData(Qt.UserRole, window.hwnd)
            self.window_list.addItem(item)
            if self._selected_hwnd is not None and window.hwnd == self._selected_hwnd:
                selected_index = self.window_list.count() - 1

        if selected_index >= 0:
            self.window_list.setCurrentRow(selected_index)
        elif self._selected_hwnd is None:
            suggestion = self._suggested_game_window()
            if suggestion is not None:
                for index in range(self.window_list.count()):
                    item = self.window_list.item(index)
                    if item.data(Qt.UserRole) == suggestion.hwnd:
                        self.window_list.setCurrentRow(index)
                        self._selected_hwnd = suggestion.hwnd
                        break
        self.status_label.setText(f"Detected {len(self._windows)} candidate windows.")

    def _ensure_selected_window(self) -> int | None:
        if self._selected_hwnd is not None:
            return self._selected_hwnd

        self.refresh_windows()
        if self._selected_hwnd is not None:
            return self._selected_hwnd

        suggestion = self._suggested_game_window()
        if suggestion is None:
            self.status_label.setText("No game window detected. Open the game, then refresh windows.")
            return None

        self._selected_hwnd = suggestion.hwnd
        self.status_label.setText(f"Auto-selected: {suggestion.title}")
        self._sync_overlay_geometry()
        return self._selected_hwnd

    def _configure_cache_for_selected_window(self) -> None:
        if self._selected_hwnd is None:
            print("[AutoTrans] Cache skipped: no window selected", flush=True)
            return
        db_path = self.capture_service.get_cache_db_path(self._selected_hwnd)
        if db_path is None:
            selected_window = next((window for window in self._windows if window.hwnd == self._selected_hwnd), None)
            title = selected_window.title if selected_window is not None else str(self._selected_hwnd)
            print(f"[AutoTrans] Cache unavailable for window: {title}", flush=True)
            return
        print(f"[AutoTrans] Attaching cache for hwnd {self._selected_hwnd}: {db_path}", flush=True)
        self.orchestrator.cache.set_persistent_path(db_path)

    def toggle_pipeline(self) -> None:
        if self._running:
            self.capture_timer.stop()
            self.follow_timer.stop()
            self._running = False
            self._processing = False
            self._rerun_requested = False
            self._overlay_temporarily_hidden = False
            self.start_button.setText("Start")
            self.status_label.setText("Paused")
            self.stats_label.setText("Paused")
            return

        if self._selected_hwnd is None:
            self.status_label.setText("Select a window first.")
            return

        selected_window = next((window for window in self._windows if window.hwnd == self._selected_hwnd), None)
        if selected_window is not None and self._looks_like_non_game_window(selected_window.title):
            suggestion = self._suggested_game_window()
            if suggestion is not None:
                self.status_label.setText(
                    f"Selected window looks wrong for OCR. Try: {suggestion.title}"
                )
                return

        self._configure_cache_for_selected_window()
        self.capture_timer.start()
        self.follow_timer.start()
        if self._overlay_enabled:
            self.overlay.show()
        self._running = True
        self.start_button.setText("Stop")
        self.status_label.setText("Running OCR + overlay...")

    def toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self._overlay_enabled = False
            self.overlay.hide()
            self.overlay_button.setText("Show Overlay")
            self.status_label.setText("Overlay hidden")
        else:
            self._overlay_enabled = True
            self.overlay.show()
            self.overlay_button.setText("Hide Overlay")
            self.status_label.setText("Overlay visible")

    def _current_deep_translation_timeout_ms(self) -> int:
        return max(self.config.deep_translation_timeout_ms + 5000, 15000)

    def _cancel_deep_translation(self) -> None:
        self._deep_translation_processing = False
        self._deep_translation_active = False
        self._deep_translation_visible = False
        self._deep_translation_job_id += 1
        self.deep_translation_watchdog.stop()

    def _build_deep_translation_message_overlay(self, message: str) -> list[OverlayItem]:
        width = max(self.overlay.width(), 640)
        height = max(self.overlay.height(), 360)
        box_width = max(min(width - 48, 900), 320)
        box_height = max(min(height // 4, 160), 72)
        box_x = max((width - box_width) // 2, 24)
        box_y = max((height - box_height) // 2, 24)
        return [
            OverlayItem(
                bbox=Rect(x=box_x, y=box_y, width=box_width, height=box_height),
                translated_text=message,
                style=OverlayStyle(font_size=max(self.config.font_size, 18), background_opacity=0.9),
                visibility_state=VisibilityState.PENDING,
                tracking_key="deep-translation-status",
                linger_seconds=0.0,
                region="deep-ui",
            )
        ]

    def _show_deep_translation_message(self, message: str) -> None:
        self.overlay.clear_overlay_items()
        self.overlay.set_persistent_overlay_items(self._build_deep_translation_message_overlay(message))
        if self._overlay_enabled and not self.overlay.isVisible():
            self.overlay.show()

    def _check_deep_translation_timeout(self) -> None:
        if not self._deep_translation_processing:
            self.deep_translation_watchdog.stop()
            return
        elapsed_ms = (time.monotonic() - self._deep_translation_started_at) * 1000.0
        timeout_ms = self._current_deep_translation_timeout_ms()
        if elapsed_ms < timeout_ms:
            return
        stage = self._deep_translation_stage or "request"
        self._cancel_deep_translation()
        self.deep_translate_button.setText("Deep Translate")
        message = (
            f"Deep translation timeout sau {int(elapsed_ms)}ms ở bước {stage}. "
            "Kiểm tra Gemini API key, mạng và log."
        )
        print(f"[AutoTrans] {message}", flush=True)
        self.status_label.setText(message)
        self._show_deep_translation_message(message)

    def toggle_deep_translation(self) -> None:
        if self._deep_translation_active:
            self._cancel_deep_translation()
            self.overlay.clear_persistent_overlay_items()
            self.deep_translate_button.setText("Deep Translate")
            self.status_label.setText("Deep translation hidden")
            return

        if self._deep_translation_processing:
            self.status_label.setText("Deep translation is still running...")
            return

        if self._selected_hwnd is None:
            if self._ensure_selected_window() is None:
                return

        self._deep_translation_active = True
        self._deep_translation_processing = True
        self._deep_translation_job_id += 1
        self._deep_translation_started_at = time.monotonic()
        self._deep_translation_stage = "prepare"
        self.deep_translate_button.setText("Translating...")
        self.status_label.setText("Running deep translation for the full game screen...")
        self._show_deep_translation_message("Đang phân tích màn hình để dịch chuyên sâu...")
        self.deep_translation_watchdog.start()
        if self._overlay_enabled and not self.overlay.isVisible():
            self.overlay.show()
        print(f"[AutoTrans] Starting deep translation for hwnd {self._selected_hwnd}", flush=True)
        worker = threading.Thread(
            target=self._prepare_deep_translation_background,
            args=(self._deep_translation_job_id, self._selected_hwnd),
            daemon=True,
        )
        worker.start()

    def _on_window_selected(self) -> None:
        items = self.window_list.selectedItems()
        self._selected_hwnd = items[0].data(Qt.UserRole) if items else None
        if items:
            selected_text = items[0].text()
            if self._looks_like_non_game_window(selected_text):
                suggestion = self._suggested_game_window()
                if suggestion is not None:
                    self.status_label.setText(
                        f"Selected screenshot/file window. Recommended: {suggestion.title}"
                    )
                else:
                    self.status_label.setText(f"Selected: {selected_text}")
            else:
                self.status_label.setText(f"Selected: {selected_text}")
        self._sync_overlay_geometry()

    def _on_mode_changed(self, mode: str) -> None:
        self.config.mode = mode

    def _on_font_size_changed(self, value: int) -> None:
        self.config.font_size = value

    def _sync_overlay_geometry(self) -> None:
        if self._selected_hwnd is None:
            return
        self._windows = self.capture_service.list_windows()
        match = next((window for window in self._windows if window.hwnd == self._selected_hwnd), None)
        if match is not None:
            self.overlay.sync_window_rect(match.rect)

    def _tick_pipeline(self) -> None:
        if self._selected_hwnd is None:
            return
        if self._processing:
            self._rerun_requested = True
            return

        self._start_pipeline_worker(self._selected_hwnd)

    def _start_pipeline_worker(self, hwnd: int) -> None:
        if (
            not self._deep_translation_active
            and self._overlay_enabled
            and self.config.capture_backend in {"bettercam", "mss"}
            and self.overlay.isVisible()
        ):
            self.overlay.hide()
            self._overlay_temporarily_hidden = True
        self._processing = True
        self._rerun_requested = False
        worker = threading.Thread(target=self._process_window_background, args=(hwnd,), daemon=True)
        worker.start()

    def _process_window_background(self, hwnd: int) -> None:
        try:
            overlay_items = self.orchestrator.process_window(hwnd)
            self.pipeline_result.emit(overlay_items)
        except Exception as exc:
            self.pipeline_error.emit(str(exc))

    def _prepare_deep_translation_background(self, job_id: int, hwnd: int) -> None:
        try:
            grouped_boxes, preview_items = self.orchestrator.prepare_deep_translation(hwnd)
            self.deep_translation_preview.emit(job_id, grouped_boxes, preview_items)
        except Exception as exc:
            self.deep_translation_error.emit(job_id, str(exc))

    def _translate_deep_translation_background(self, job_id: int, grouped_boxes) -> None:
        try:
            overlay_items = self.orchestrator.translate_deep_boxes(grouped_boxes)
            self.deep_translation_result.emit(job_id, overlay_items)
        except Exception as exc:
            self.deep_translation_error.emit(job_id, str(exc))

    def _apply_deep_translation_preview(self, job_id: int, grouped_boxes, overlay_items) -> None:
        if job_id != self._deep_translation_job_id:
            return
        self._deep_translation_stage = "translate"
        self.overlay.clear_overlay_items()
        self.overlay.set_persistent_overlay_items(overlay_items)
        if self._overlay_enabled and not self.overlay.isVisible():
            self.overlay.show()
        if overlay_items:
            self.status_label.setText(f"Detected {len(overlay_items)} deep text block(s), translating...")
            worker = threading.Thread(
                target=self._translate_deep_translation_background,
                args=(job_id, grouped_boxes),
                daemon=True,
            )
            worker.start()
        else:
            self._deep_translation_processing = False
            self.deep_translation_watchdog.stop()
            self.deep_translate_button.setText("Deep Translate")
            self.status_label.setText("Deep translation found no usable text blocks.")

    def _apply_pipeline_result(self, overlay_items) -> None:
        self._processing = False
        if self._overlay_temporarily_hidden and self._overlay_enabled and not self._deep_translation_active:
            self.overlay.show()
        self._overlay_temporarily_hidden = False
        if not self._deep_translation_active:
            self.overlay.set_overlay_items(overlay_items)
            if overlay_items:
                self.status_label.setText(f"Overlay updated with {len(overlay_items)} translated boxes.")
            else:
                self.status_label.setText("No subtitle detected yet. Use the actual game window and wait for dialogue.")
        self.stats_label.setText(
            "Boxes: {boxes} | Capture FPS: {cap:.1f} | Translation: {lat:.0f}ms | Cache hits: {hits}".format(
                boxes=len(overlay_items),
                cap=self.orchestrator.stats.capture_fps,
                lat=self.orchestrator.stats.translation_latency_ms,
                hits=self.orchestrator.stats.cache_hits,
            )
        )
        if self._running and self._rerun_requested and self._selected_hwnd is not None:
            self._start_pipeline_worker(self._selected_hwnd)

    def _apply_pipeline_error(self, message: str) -> None:
        self._processing = False
        if self._overlay_temporarily_hidden and self._overlay_enabled and not self._deep_translation_active:
            self.overlay.show()
        self._overlay_temporarily_hidden = False
        self.status_label.setText(f"Pipeline error: {message}")
        if self._running and self._rerun_requested and self._selected_hwnd is not None:
            self._start_pipeline_worker(self._selected_hwnd)

    def _apply_deep_translation_result(self, job_id: int, overlay_items) -> None:
        if job_id != self._deep_translation_job_id:
            return
        self._deep_translation_processing = False
        self.deep_translation_watchdog.stop()
        self.overlay.clear_overlay_items()
        self.overlay.set_persistent_overlay_items(overlay_items)
        self._deep_translation_visible = bool(overlay_items)
        if not overlay_items:
            self._deep_translation_active = False
        self.deep_translate_button.setText("Hide Deep" if overlay_items else "Deep Translate")
        if self._overlay_enabled and not self.overlay.isVisible():
            self.overlay.show()
        print(f"[AutoTrans] Deep translation result items={len(overlay_items)}", flush=True)
        if overlay_items:
            self.status_label.setText(f"Deep translation ready with {len(overlay_items)} text block(s).")
        else:
            self.status_label.setText("Deep translation found no usable text blocks.")

    def _apply_deep_translation_error(self, job_id: int, message: str) -> None:
        if job_id != self._deep_translation_job_id:
            return
        self._cancel_deep_translation()
        self.deep_translate_button.setText("Deep Translate")
        print(f"[AutoTrans] Deep translation error: {message}", flush=True)
        error_message = f"Deep translation error: {message}"
        self.status_label.setText(error_message)
        self._show_deep_translation_message(error_message)
