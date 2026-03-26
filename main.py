import sys

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from askanywhere.config import load_settings
from askanywhere.gemini_service import GeminiChatService
from askanywhere.popup import ChatPopup
from askanywhere.selection_watcher import GlobalSelectionWatcher


class AskWorker(QThread):
    success = Signal(str)
    failure = Signal(str)

    def __init__(self, service: GeminiChatService, selected_text: str, user_input: str) -> None:
        super().__init__()
        self._service = service
        self._selected_text = selected_text
        self._user_input = user_input

    def run(self) -> None:
        try:
            answer = self._service.send_message(self._selected_text, self._user_input)
            self.success.emit(answer)
        except Exception as ex:
            self.failure.emit(str(ex))


class AskAnywhereApp:
    def __init__(self) -> None:
        self.settings = load_settings()
        self.qt_app = QApplication(sys.argv)
        self.qt_app.setQuitOnLastWindowClosed(False)

        if not self.settings.gemini_api_key:
            QMessageBox.critical(
                None,
                "Missing GEMINI_API_KEY",
                "Create a .env file with GEMINI_API_KEY before running AskAnywhere.",
            )
            raise RuntimeError("Missing GEMINI_API_KEY")

        self.service = GeminiChatService(
            api_key=self.settings.gemini_api_key,
            model=self.settings.gemini_model,
        )
        self.popup = ChatPopup(model_name=self.settings.gemini_model)
        self.watcher = GlobalSelectionWatcher()

        self.watcher.selection_captured.connect(self._on_selection_captured)
        self.watcher.listening_toggled.connect(self._on_listening_toggled)
        self.popup.message_submitted.connect(self._on_message_submitted)
        self.popup.closed.connect(self._on_popup_closed)
        self.qt_app.aboutToQuit.connect(self._shutdown)

        self._worker: AskWorker | None = None

    def run(self) -> int:
        print(
            "AskAnywhere running. Drag-select text to open popup. "
            "Press Ctrl+Shift+Z to toggle listening on/off.",
            flush=True,
        )
        self.watcher.start()
        return self.qt_app.exec()

    def _on_listening_toggled(self, enabled: bool) -> None:
        state = "ENABLED" if enabled else "DISABLED"
        print(f"[AskAnywhere][App] Listening {state}", flush=True)
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
            print("[AskAnywhere][App] Worker already running, skipping new request", flush=True)
            return

        selected_text = self.popup.current_selection
        self.popup.add_user_message(user_input)
        self.popup.set_busy(True)

        self._worker = AskWorker(self.service, selected_text, user_input)
        self._worker.success.connect(self._on_ai_success)
        self._worker.failure.connect(self._on_ai_failure)
        self._worker.finished.connect(self._on_ai_finished)
        self._worker.start()

    def _on_ai_success(self, answer: str) -> None:
        print(f"[AskAnywhere][App] AI response received len={len(answer)}", flush=True)
        self.popup.add_ai_message(answer)

    def _on_ai_failure(self, error: str) -> None:
        print(f"[AskAnywhere][App] AI error: {error}", flush=True)
        self.popup.add_error(error)

    def _on_ai_finished(self) -> None:
        self.popup.set_busy(False)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    def _on_popup_closed(self) -> None:
        self.popup.set_busy(False)

    def _shutdown(self) -> None:
        print("[AskAnywhere][App] Shutting down", flush=True)
        try:
            self.watcher.stop()
        except Exception as ex:
            print(f"[AskAnywhere][App] Watcher stop error: {ex}", flush=True)

        if self._worker and self._worker.isRunning():
            print("[AskAnywhere][App] Waiting for worker thread to finish", flush=True)
            self._worker.wait(8000)


def main() -> None:
    app = AskAnywhereApp()
    exit_code = app.run()
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
