import html

from PySide6.QtCore import QEvent, QPoint, Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextDocumentFragment
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
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
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(380, 300)
        self.resize(460, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("card")
        root.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedWidth(28)
        self.close_button.clicked.connect(self.hide)
        title_row.addWidget(self.close_button)
        card_layout.addLayout(title_row)

        selected_label = QLabel("Selected")
        selected_label.setObjectName("sectionTitle")
        card_layout.addWidget(selected_label)

        self.selection_view = QLineEdit()
        self.selection_view.setObjectName("selectionBox")
        self.selection_view.setReadOnly(True)
        self.selection_view.setFixedHeight(30)
        card_layout.addWidget(self.selection_view)

        chat_label = QLabel("Conversation")
        chat_label.setObjectName("sectionTitle")
        card_layout.addWidget(chat_label)

        self.chat_view = QTextBrowser()
        self.chat_view.setObjectName("chatBox")
        self.chat_view.setReadOnly(True)
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.document().setDefaultStyleSheet(
            "p, ul, ol { margin-top: 2px; margin-bottom: 2px; }"
            "li { margin-top: 0px; margin-bottom: 0px; }"
            "pre { margin-top: 4px; margin-bottom: 4px; }"
        )
        card_layout.addWidget(self.chat_view, 1)

        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("promptInput")
        self.input.setPlaceholderText("Ask about the selected text...")
        self.input.returnPressed.connect(self._submit)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)
        card_layout.addLayout(input_row)

        self.setStyleSheet(
            """
            QWidget {
                color: #f5f7fb;
                font-family: 'Segoe UI';
            }
            QFrame#card {
                background-color: rgba(18, 24, 38, 215);
                border: 1px solid rgba(130, 154, 196, 110);
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 11px;
                font-weight: 700;
                color: #b9c7e6;
            }
            QLineEdit#selectionBox, QTextBrowser#chatBox {
                background-color: rgba(8, 14, 28, 145);
                border: 1px solid rgba(109, 135, 180, 100);
                border-radius: 8px;
                padding: 6px 8px;
                selection-background-color: rgba(90, 155, 255, 120);
            }
            QLineEdit#promptInput {
                background-color: rgba(8, 14, 28, 170);
                border: 1px solid rgba(109, 135, 180, 120);
                border-radius: 8px;
                padding: 7px 10px;
                color: #f5f7fb;
            }
            QPushButton#sendButton {
                background-color: rgba(71, 134, 255, 210);
                border: 1px solid rgba(148, 186, 255, 180);
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 700;
            }
            QPushButton#sendButton:hover {
                background-color: rgba(98, 154, 255, 230);
            }
            QPushButton#closeButton {
                background-color: rgba(255, 255, 255, 30);
                border: 1px solid rgba(255, 255, 255, 60);
                border-radius: 8px;
                color: #dbe8ff;
                font-weight: 700;
            }
            QPushButton#closeButton:hover {
                background-color: rgba(255, 99, 99, 160);
                border-color: rgba(255, 140, 140, 220);
            }
            """
        )

    def show_for_selection(self, text: str, x: int, y: int) -> None:
        self.current_selection = text
        single_line = " ".join(text.splitlines()).strip()
        self.selection_view.setText(single_line)
        self.selection_view.setCursorPosition(0)
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
        safe = html.escape(text).replace("\n", "<br>")
        self._append_html("You", f"<p>{safe}</p>")

    def add_ai_message(self, text: str) -> None:
        self._append_html("AI", self._markdown_to_html(text))

    def add_error(self, text: str) -> None:
        safe = html.escape(text).replace("\n", "<br>")
        self._append_html("Error", f"<p>{safe}</p>")

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

    def _append_html(self, role: str, content_html: str) -> None:
        if self.chat_view.toPlainText().strip():
            self.chat_view.append("<div style='height:3px'></div>")
        role_html = (
            "<div style='font-weight:700; color:#b7caf7; letter-spacing:0.2px; margin-bottom:2px;'>"
            + html.escape(role)
            + "</div>"
        )
        bubble = (
            "<div style='background:rgba(7,14,30,0.55); border:1px solid rgba(110,140,190,0.35);"
            " border-radius:8px; padding:6px 8px; color:#eef4ff;'>"
            + content_html
            + "</div>"
        )
        self.chat_view.append(role_html + bubble)
        self.chat_view.verticalScrollBar().setValue(
            self.chat_view.verticalScrollBar().maximum()
        )

    @staticmethod
    def _markdown_to_html(markdown_text: str) -> str:
        return QTextDocumentFragment.fromMarkdown(markdown_text).toHtml()

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
