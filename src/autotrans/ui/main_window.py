from __future__ import annotations

import threading

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
from autotrans.services.capture import WindowInfo, WindowsWindowCapture
from autotrans.services.orchestrator import PipelineOrchestrator
from autotrans.ui.overlay import OverlayWindow


class MainWindow(QMainWindow):
    pipeline_result = Signal(list)
    pipeline_error = Signal(str)

    def __init__(
        self,
        config: AppConfig,
        capture_service: WindowsWindowCapture,
        orchestrator: PipelineOrchestrator,
        overlay: OverlayWindow,
    ) -> None:
        super().__init__()
        self.config = config
        self.capture_service = capture_service
        self.orchestrator = orchestrator
        self.overlay = overlay
        self._selected_hwnd: int | None = None
        self._windows: list[WindowInfo] = []
        self._running = False
        self._processing = False
        self._rerun_requested = False
        self._overlay_enabled = True
        self._overlay_temporarily_hidden = False

        self.setWindowTitle("AutoTrans MVP")
        self.resize(700, 450)

        self.window_list = QListWidget()
        self.refresh_button = QPushButton("Refresh Windows")
        self.start_button = QPushButton("Start")
        self.overlay_button = QPushButton("Hide Overlay")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["fast", "balanced", "high_quality"])
        self.mode_combo.setCurrentText(config.mode)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 48)
        self.font_size_spin.setValue(config.font_size)
        self.status_label = QLabel("Select a game window, then click Start.")
        self.stats_label = QLabel("Idle")
        self.hotkey_label = QLabel("Hotkeys: Ctrl+Shift+P pause/resume, Ctrl+Shift+O overlay")

        controls_layout = QFormLayout()
        controls_layout.addRow("Mode", self.mode_combo)
        controls_layout.addRow("Font Size", self.font_size_spin)

        button_row = QHBoxLayout()
        button_row.addWidget(self.refresh_button)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.overlay_button)

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
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        self.window_list.itemSelectionChanged.connect(self._on_window_selected)
        self.pipeline_result.connect(self._apply_pipeline_result)
        self.pipeline_error.connect(self._apply_pipeline_error)

        self.capture_timer = QTimer(self)
        capture_interval_ms = max(int(round(1000.0 / max(config.capture_fps, 0.01))), 200)
        self.capture_timer.setInterval(capture_interval_ms)
        self.capture_timer.timeout.connect(self._tick_pipeline)

        self.follow_timer = QTimer(self)
        self.follow_timer.setInterval(100)
        self.follow_timer.timeout.connect(self._sync_overlay_geometry)

        self.pause_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.pause_shortcut.activated.connect(self.toggle_pipeline)
        self.overlay_shortcut = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        self.overlay_shortcut.activated.connect(self.toggle_overlay)

        self.refresh_windows()

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
        for window in self._windows:
            item = QListWidgetItem(f"{window.title} [{window.rect.width}x{window.rect.height}]")
            item.setData(Qt.UserRole, window.hwnd)
            self.window_list.addItem(item)
        self.status_label.setText(f"Detected {len(self._windows)} candidate windows.")

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
        if self._overlay_enabled and self.config.capture_backend in {"bettercam", "mss"} and self.overlay.isVisible():
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

    def _apply_pipeline_result(self, overlay_items) -> None:
        self._processing = False
        if self._overlay_temporarily_hidden and self._overlay_enabled:
            self.overlay.show()
        self._overlay_temporarily_hidden = False
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
        if self._overlay_temporarily_hidden and self._overlay_enabled:
            self.overlay.show()
        self._overlay_temporarily_hidden = False
        self.status_label.setText(f"Pipeline error: {message}")
        if self._running and self._rerun_requested and self._selected_hwnd is not None:
            self._start_pipeline_worker(self._selected_hwnd)

