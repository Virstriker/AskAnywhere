import time

import pyperclip
from PySide6.QtCore import QObject, Signal
from pynput import keyboard, mouse


class GlobalSelectionWatcher(QObject):
    selection_captured = Signal(str, int, int)
    listening_toggled = Signal(bool)
    _capture_requested = Signal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self._keyboard = keyboard.Controller()
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._hotkey_listener = keyboard.GlobalHotKeys(
            {
                "<ctrl>+<shift>+z": self._toggle_listening,
            }
        )
        self._capture_requested.connect(self._capture_selected_text)
        self._last_capture_at = 0.0
        self._press_pos: tuple[int, int] | None = None
        self._drag_threshold = 4
        self.enabled = True

    def start(self) -> None:
        self._log("Listeners started (toggle: Ctrl+Shift+Z)")
        self._mouse_listener.start()
        self._hotkey_listener.start()
        self.listening_toggled.emit(self.enabled)

    def stop(self) -> None:
        self._mouse_listener.stop()
        self._hotkey_listener.stop()

    def _toggle_listening(self) -> None:
        self.enabled = not self.enabled
        self._log(f"Listening {'ENABLED' if self.enabled else 'DISABLED'}")
        self.listening_toggled.emit(self.enabled)

    def _on_click(self, x: float, y: float, button: mouse.Button, pressed: bool) -> None:
        if not self.enabled:
            return
        if button != mouse.Button.left:
            return

        ix, iy = int(x), int(y)
        if pressed:
            self._press_pos = (ix, iy)
            return

        if not self._press_pos:
            return

        px, py = self._press_pos
        self._press_pos = None
        dragged = abs(ix - px) >= self._drag_threshold or abs(iy - py) >= self._drag_threshold
        if not dragged:
            self._log("Ignoring click without drag selection")
            return

        self._log(f"Mouse selection trigger at cursor=({ix}, {iy})")
        self._capture_requested.emit(ix, iy)

    def _capture_selected_text(self, x: int, y: int) -> None:
        now = time.monotonic()
        if now - self._last_capture_at < 0.6:
            self._log("Trigger ignored due to debounce")
            return
        self._last_capture_at = now
        self._log(f"Capture requested at cursor=({x}, {y})")

        try:
            self._copy_selection()
            self._log("Sent Ctrl+C to active window")
            time.sleep(0.08)
            selected = (pyperclip.paste() or "").strip()
        except Exception as ex:
            self._log(f"Capture failed: {ex}")
            return

        if selected:
            self._log(f"Selection captured (len={len(selected)})")
            self.selection_captured.emit(selected, x, y)
            return

        self._log("No selected text captured")

    def _copy_selection(self) -> None:
        with self._keyboard.pressed(keyboard.Key.ctrl):
            self._keyboard.press("c")
            self._keyboard.release("c")

    @staticmethod
    def _log(message: str) -> None:
        print(f"[AskAnywhere][SelectionWatcher] {message}", flush=True)
