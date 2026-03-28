import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from askanywhere.ai_service import create_service
from askanywhere.config import load_settings, save_active_model
from askanywhere.popup import ChatPopup
from askanywhere.selection_watcher import GlobalSelectionWatcher


# ── Streaming worker ────────────────────────────────────────────────────────

class AskWorker(QThread):
    chunk_received = Signal(str)   # one text chunk at a time
    streaming_done = Signal()      # all chunks delivered
    failure = Signal(str)

    def __init__(self, service, selected_text: str, user_input: str) -> None:
        super().__init__()
        self._service = service
        self._selected_text = selected_text
        self._user_input = user_input

    def run(self) -> None:
        try:
            for chunk in self._service.stream_message(
                self._selected_text, self._user_input
            ):
                if self.isInterruptionRequested():
                    break
                self.chunk_received.emit(chunk)
            self.streaming_done.emit()
        except Exception as ex:
            self.failure.emit(str(ex))


# ── Tray icon ───────────────────────────────────────────────────────────────

def _make_tray_icon(enabled: bool) -> QIcon:
    """Programmatically draw a coloured circle as the tray icon."""
    size = 32
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    color = QColor(71, 134, 255) if enabled else QColor(110, 110, 130)
    painter.setBrush(color)
    painter.setPen(QColor(180, 200, 255, 100))
    painter.drawEllipse(4, 4, size - 8, size - 8)
    painter.end()
    return QIcon(pixmap)


# ── Application ─────────────────────────────────────────────────────────────

class AskAnywhereApp:
    def __init__(self) -> None:
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        try:
            self.settings = load_settings()
        except Exception as ex:
            QMessageBox.critical(None, "Configuration Error", str(ex))
            raise

        active_model = self.settings.get_active_model()
        if not active_model:
            QMessageBox.critical(None, "No Models", "No models configured.")
            raise RuntimeError("No models configured")

        api_key = self.settings.get_api_key(active_model.provider)
        if not api_key:
            QMessageBox.critical(
                None,
                f"Missing API key — {active_model.provider}",
                f"Set api_keys.{active_model.provider} in askanywhere.config.json\n"
                "(or GEMINI_API_KEY in .env for dev mode).",
            )
            raise RuntimeError(f"Missing API key for {active_model.provider}")

        self.service = create_service(
            active_model.provider, api_key, active_model.model_id
        )

        self.popup = ChatPopup()
        self.popup.set_models(self.settings.models, self.settings.active_model)
        self.watcher = GlobalSelectionWatcher()

        self.watcher.selection_captured.connect(self._on_selection_captured)
        self.watcher.listening_toggled.connect(self._on_listening_toggled)
        self.popup.message_submitted.connect(self._on_message_submitted)
        self.popup.model_changed.connect(self._on_model_changed)
        self.popup.closed.connect(self._on_popup_closed)
        self.qt_app.aboutToQuit.connect(self._shutdown)

        # ── System tray ──
        self.tray = QSystemTrayIcon(self.qt_app)
        self.tray.setIcon(_make_tray_icon(True))
        self.tray.setToolTip("AskAnywhere — Listening")
        self._build_tray_menu()
        self.tray.show()

        self._worker: AskWorker | None = None

    def _build_tray_menu(self) -> None:
        menu = QMenu()
        self._toggle_action = menu.addAction("⏸  Pause listening")
        self._toggle_action.triggered.connect(self.watcher.toggle)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self.qt_app.quit)
        self.tray.setContextMenu(menu)

    def run(self) -> int:
        print(
            "AskAnywhere running. Drag-select text to open popup. "
            "Press Ctrl+Shift+Z to toggle listening on/off.",
            flush=True,
        )
        self.watcher.start()
        return self.qt_app.exec()

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_listening_toggled(self, enabled: bool) -> None:
        state = "ENABLED" if enabled else "DISABLED"
        print(f"[AskAnywhere][App] Listening {state}", flush=True)
        self.tray.setIcon(_make_tray_icon(enabled))
        self.tray.setToolTip(f"AskAnywhere — {'Listening' if enabled else 'Paused'}")
        self._toggle_action.setText(
            "⏸  Pause listening" if enabled else "▶  Resume listening"
        )
        if not enabled and self.popup.isVisible():
            self.popup.hide()

    def _on_selection_captured(self, text: str, x: int, y: int) -> None:
        print(
            f"[AskAnywhere][App] selection_captured len={len(text)} cursor=({x}, {y})",
            flush=True,
        )
        if self.popup.isActiveWindow():
            print("[AskAnywhere][App] Popup already active, skipping show", flush=True)
            return
        self.popup.show_for_selection(text, x, y)
        print("[AskAnywhere][App] Popup shown", flush=True)

    def _on_message_submitted(self, user_input: str) -> None:
        print(f"[AskAnywhere][App] User message submitted len={len(user_input)}", flush=True)
        if self._worker and self._worker.isRunning():
            print("[AskAnywhere][App] Worker already running, skipping", flush=True)
            return

        selected_text = self.popup.current_selection
        self.popup.add_user_message(user_input)
        self.popup.start_ai_stream()       # creates streaming bubble
        self.popup.set_busy(True)

        self._worker = AskWorker(self.service, selected_text, user_input)
        self._worker.chunk_received.connect(self.popup.append_stream_chunk)
        self._worker.streaming_done.connect(self._on_stream_done)
        self._worker.failure.connect(self._on_ai_failure)
        self._worker.finished.connect(self._on_ai_finished)
        self._worker.start()

    def _on_stream_done(self) -> None:
        self.popup.finalize_stream_bubble()

    def _on_ai_failure(self, error: str) -> None:
        print(f"[AskAnywhere][App] AI error: {error}", flush=True)
        self.popup.finalize_stream_bubble()   # clear streaming state first
        self.popup.add_error(error)

    def _on_ai_finished(self) -> None:
        self.popup.set_busy(False)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def _on_model_changed(self, model_id: str) -> None:
        print(f"[AskAnywhere][App] Model switched to {model_id}", flush=True)
        self.settings.active_model = model_id
        save_active_model(model_id)          # persist to config.json

        active_model = self.settings.get_active_model()
        if not active_model:
            return
        api_key = self.settings.get_api_key(active_model.provider)
        if not api_key:
            self.popup.add_error(
                f"No API key configured for provider '{active_model.provider}'."
            )
            return
        self.service = create_service(
            active_model.provider, api_key, active_model.model_id
        )
        print(f"[AskAnywhere][App] Service restarted ({active_model.provider})", flush=True)

    def _on_popup_closed(self) -> None:
        self.popup.set_busy(False)

    def _shutdown(self) -> None:
        print("[AskAnywhere][App] Shutting down", flush=True)
        try:
            self.watcher.stop()
        except Exception as ex:
            print(f"[AskAnywhere][App] Watcher stop error: {ex}", flush=True)

        if self._worker and self._worker.isRunning():
            print("[AskAnywhere][App] Waiting for worker thread …", flush=True)
            self._worker.requestInterruption()
            self._worker.wait(8000)


def main() -> None:
    app = AskAnywhereApp()
    exit_code = app.run()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
