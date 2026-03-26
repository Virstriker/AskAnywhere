from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class ChatPopup(QWidget):
    message_submitted = Signal(str)
    closed = Signal()

    def __init__(self, model_name: str) -> None:
        super().__init__()
        self.current_selection = ""
        self._busy = False
        self._drag_offset = QPoint()
        self._dragging = False

        self.setWindowTitle("AskAnywhere")
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setMinimumSize(420, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel(f"AskAnywhere • {model_name}")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        self.close_button = QPushButton("×")
        self.close_button.setFixedWidth(28)
        self.close_button.clicked.connect(self.hide)
        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(self.close_button)
        root.addLayout(title_row)

        selected_label = QLabel("Selected text")
        selected_label.setStyleSheet("font-weight: 600;")
        root.addWidget(selected_label)

        self.selection_view = QTextEdit()
        self.selection_view.setReadOnly(True)
        self.selection_view.setFixedHeight(85)
        root.addWidget(self.selection_view)

        chat_label = QLabel("Conversation")
        chat_label.setStyleSheet("font-weight: 600;")
        root.addWidget(chat_label)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        root.addWidget(self.chat_view)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about the selected text...")
        self.input.returnPressed.connect(self._submit)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)
        root.addLayout(input_row)

    def show_for_selection(self, text: str, x: int, y: int) -> None:
        self.current_selection = text
        self.selection_view.setPlainText(text)
        self._move_near_cursor(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        if busy:
            self.send_button.setText("...")
        else:
            self.send_button.setText("Send")

    def add_user_message(self, text: str) -> None:
        self._append("You", text)

    def add_ai_message(self, text: str) -> None:
        self._append("AI", text)

    def add_error(self, text: str) -> None:
        self._append("Error", text)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.closed.emit()

    def event(self, event) -> bool:
        if event.type() == QEvent.WindowDeactivate and self.isVisible():
            self.hide()
        return super().event(event)

    def _submit(self) -> None:
        text = self.input.text().strip()
        if self._busy or not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def _append(self, role: str, text: str) -> None:
        if self.chat_view.toPlainText():
            self.chat_view.append("")
        self.chat_view.append(f"{role}: {text}")
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            target = event.globalPosition().toPoint() - self._drag_offset
            self.move(target)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def _move_near_cursor(self, x: int, y: int) -> None:
        screen = QGuiApplication.screenAt(QPoint(x, y))
        if not screen:
            screen = QGuiApplication.primaryScreen()
        if not screen:
            self.move(x + 16, y + 20)
            return

        available = screen.availableGeometry()
        target_x = x + 16
        target_y = y + 20

        width = self.width() if self.width() > 0 else self.minimumWidth()
        height = self.height() if self.height() > 0 else self.minimumHeight()

        if target_x + width > available.right():
            target_x = max(available.left(), x - width - 16)
        if target_y + height > available.bottom():
            target_y = max(available.top(), y - height - 16)

        self.move(target_x, target_y)
