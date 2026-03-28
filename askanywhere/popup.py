import html
from collections import deque

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication, QTextDocumentFragment
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def _md_to_html(text: str) -> str:
    """Convert markdown text to HTML using Qt's built-in renderer."""
    return QTextDocumentFragment.fromMarkdown(text).toHtml()


class AutoSizeTextBrowser(QTextBrowser):
    """QTextBrowser that auto-sizes its height to fit wrapped content."""

    def sizeHint(self) -> QSize:
        # Measure height using the real viewport width so word-wrap is correct.
        # Return width=0 so the parent layout controls horizontal sizing.
        vw = self.viewport().width()
        if vw < 10:
            vw = 400
        self.document().setTextWidth(vw)
        h = int(self.document().size().height())
        return QSize(0, max(20, h + 6))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Notify the parent layout that our preferred height has changed.
        self.updateGeometry()


class ResizeGrip(QWidget):
    """Translucent corner grip that constrains the resize cursor to its own area."""

    SIZE = 18

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.SizeFDiagCursor)   # cursor scoped ONLY to this widget
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._reposition()

    def _reposition(self) -> None:
        p = self.parent()
        if p:
            self.move(p.width() - self.SIZE, p.height() - self.SIZE)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self.parent().windowHandle()
            if handle:
                handle.startSystemResize(Qt.Edges(Qt.RightEdge | Qt.BottomEdge))
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        """Draw three subtle dots as a grip indicator."""
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(180, 200, 255, 80))
        painter.setPen(Qt.NoPen)
        r = 2
        for dx, dy in [(12, 16), (16, 12), (16, 16)]:
            painter.drawEllipse(dx - r, dy - r, r * 2, r * 2)


class BubbleWidget(QFrame):
    """A single chat message bubble with optional copy button for AI responses."""

    def __init__(self, role: str, content_html: str, plain_text: str, parent=None) -> None:
        super().__init__(parent)
        self._plain_text = plain_text
        self.setObjectName("bubble")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Header: role label + copy button (AI only)
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        role_label = QLabel(role)
        role_label.setObjectName("roleLabel")
        header_row.addWidget(role_label)
        header_row.addStretch()

        if role == "AI":
            copy_btn = QPushButton("⧉")
            copy_btn.setObjectName("copyButton")
            copy_btn.setFixedSize(22, 22)
            copy_btn.setToolTip("Copy response")
            copy_btn.clicked.connect(self._copy_text)
            header_row.addWidget(copy_btn)

        layout.addLayout(header_row)

        # Content — uses AutoSizeTextBrowser so height adapts to text width
        self._content = AutoSizeTextBrowser()
        self._content.setObjectName("bubbleContent")
        self._content.setReadOnly(True)
        self._content.setOpenExternalLinks(True)
        self._content.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._content.document().setDefaultStyleSheet(
            "body { color: #eef4ff; }"
            "p, ul, ol { margin-top: 2px; margin-bottom: 2px; }"
            "li { margin-top: 0px; margin-bottom: 0px; }"
            "pre { margin-top: 4px; margin-bottom: 4px; }"
        )
        self._content.setHtml(content_html)
        layout.addWidget(self._content)

    def _copy_text(self) -> None:
        QApplication.clipboard().setText(self._plain_text)

    # ── Streaming support ───────────────────────────────────────────

    def update_stream(self, chunk: str) -> None:
        """Append a chunk and re-render with a blinking-cursor indicator."""
        self._plain_text += chunk
        self._content.setHtml(_md_to_html(self._plain_text + " ▌"))
        self._content.updateGeometry()

    def finalize_stream(self) -> None:
        """Remove cursor indicator and render final markdown."""
        self._content.setHtml(_md_to_html(self._plain_text))
        self._content.updateGeometry()


class ChatPopup(QWidget):
    message_submitted = Signal(str)
    model_changed = Signal(str)   # emits model_id when user switches model
    closed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.current_selection = ""
        self._busy = False
        self._drag_offset = QPoint()
        self._dragging = False
        self._pinned = False
        self._models: list = []          # list[ModelConfig]
        self._active_model_id: str = ""
        self._streaming_bubble = None    # BubbleWidget | None
        # History: deque of (selected_text, [(role, plain, html), ...])
        self._history: deque = deque(maxlen=5)
        self._current_messages: list = []

        self.setWindowTitle("AskAnywhere")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(380, 280)
        self.resize(460, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.card = QFrame()
        self.card.setObjectName("card")
        root.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(10, 10, 10, 8)
        card_layout.setSpacing(6)

        # ── Title row ──
        title_row = QHBoxLayout()
        self.history_button = QPushButton("↑ History")
        self.history_button.setObjectName("historyButton")
        self.history_button.setFixedHeight(24)
        self.history_button.clicked.connect(self._show_history_menu)
        self.history_button.setVisible(False)
        title_row.addWidget(self.history_button)
        title_row.addStretch()
        self.pin_button = QPushButton("📌")
        self.pin_button.setObjectName("pinButton")
        self.pin_button.setFixedWidth(28)
        self.pin_button.setToolTip("Pin — keep open when focus moves away")
        self.pin_button.clicked.connect(self._toggle_pin)
        title_row.addWidget(self.pin_button)
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedWidth(28)
        self.settings_button.setToolTip("Switch model")
        self.settings_button.clicked.connect(self._show_model_picker)
        title_row.addWidget(self.settings_button)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("closeButton")
        self.close_button.setFixedWidth(28)
        self.close_button.clicked.connect(self.hide)
        title_row.addWidget(self.close_button)
        card_layout.addLayout(title_row)

        # ── Selected text ──
        selected_label = QLabel("Selected")
        selected_label.setObjectName("sectionTitle")
        card_layout.addWidget(selected_label)

        self.selection_view = QLineEdit()
        self.selection_view.setObjectName("selectionBox")
        self.selection_view.setReadOnly(True)
        self.selection_view.setFixedHeight(30)
        card_layout.addWidget(self.selection_view)

        # ── Quick action chips ──
        chips_row = QHBoxLayout()
        chips_row.setSpacing(6)
        chips_row.setContentsMargins(0, 0, 0, 0)
        for chip_label in ("Summarize", "Explain", "Fix grammar"):
            btn = QPushButton(chip_label)
            btn.setObjectName("chipButton")
            btn.clicked.connect(
                lambda checked=False, lbl=chip_label: self._on_chip_clicked(lbl)
            )
            chips_row.addWidget(btn)
        chips_row.addStretch()
        self.chips_widget = QWidget()
        self.chips_widget.setLayout(chips_row)
        card_layout.addWidget(self.chips_widget)

        # ── Conversation scroll area ──
        conv_label = QLabel("Conversation")
        conv_label.setObjectName("sectionTitle")
        card_layout.addWidget(conv_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("chatBox")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.viewport().setStyleSheet("background: transparent;")

        self.bubble_container = QWidget()
        self.bubble_container.setObjectName("bubbleContainer")
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(4, 4, 4, 4)
        self.bubble_layout.setSpacing(6)
        self.bubble_layout.addStretch()

        self.scroll_area.setWidget(self.bubble_container)
        card_layout.addWidget(self.scroll_area, 1)

        # ── Input row ──
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("promptInput")
        self.input.setPlaceholderText("Ask about the selected text...")
        self.input.returnPressed.connect(self._submit)
        self.input.textChanged.connect(self._on_input_changed)
        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("sendButton")
        self.send_button.clicked.connect(self._submit)
        input_row.addWidget(self.input)
        input_row.addWidget(self.send_button)
        card_layout.addLayout(input_row)



        self._apply_styles()

        # Resize grip — pinned to bottom-right corner, cursor scoped to its area only
        self._grip = ResizeGrip(self)
        self._grip.raise_()

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def show_for_selection(self, text: str, x: int, y: int) -> None:
        # Archive current session before replacing it
        if self._current_messages:
            self._history.appendleft((self.current_selection, list(self._current_messages)))
            self.history_button.setVisible(True)

        self.current_selection = text
        self.selection_view.setText(" ".join(text.splitlines()).strip())
        self.selection_view.setCursorPosition(0)
        self._clear_chat()
        self.chips_widget.setVisible(True)

        if not self._pinned:
            self._move_near_cursor(x, y)
            self.show()
            self.raise_()
            self.activateWindow()
            self.input.setFocus()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.send_button.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.send_button.setText("..." if busy else "Send")

    def add_user_message(self, text: str) -> None:
        safe_html = f"<p>{html.escape(text).replace(chr(10), '<br>')}</p>"
        self._add_bubble("You", text, safe_html)

    def add_ai_message(self, text: str) -> None:
        self._add_bubble("AI", text, self._markdown_to_html(text))

    def add_error(self, text: str) -> None:
        safe_html = f"<p style='color:#ff8080'>{html.escape(text)}</p>"
        self._add_bubble("Error", text, safe_html)

    # ──────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        if self._pinned:
            self.pin_button.setObjectName("pinButtonActive")
        else:
            self.pin_button.setObjectName("pinButton")
        self._apply_styles()

    def set_models(self, models: list, active_model_id: str) -> None:
        """Called by main to populate the model picker."""
        self._models = models
        self._active_model_id = active_model_id
        self._update_settings_tooltip()

    def _update_settings_tooltip(self) -> None:
        active = next(
            (m for m in self._models if m.model_id == self._active_model_id), None
        )
        if active:
            self.settings_button.setToolTip(f"⚙ Model: {active.display_name}")

    def _show_model_picker(self) -> None:
        if not self._models:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "  background-color: rgba(18,24,38,245);"
            "  border: 1px solid rgba(130,154,196,110);"
            "  border-radius: 8px;"
            "  color: #f5f7fb;"
            "  font-family: 'Segoe UI';"
            "  padding: 4px;"
            "}"
            "QMenu::item { padding: 5px 14px; border-radius: 5px; }"
            "QMenu::item:selected { background-color: rgba(71,134,255,140); }"
            "QMenu::item:disabled { color: rgba(180,200,255,120); font-size: 10px; }"
            "QMenu::separator { height: 1px; background: rgba(130,154,196,60); margin: 3px 8px; }"
        )
        current_provider = None
        for model in self._models:
            if model.provider != current_provider:
                current_provider = model.provider
                header = menu.addAction(f"── {current_provider.title()} ──")
                header.setEnabled(False)
            action = menu.addAction(f"  {model.display_name}")
            action.setCheckable(True)
            action.setChecked(model.model_id == self._active_model_id)
            action.setData(model.model_id)

        chosen = menu.exec(
            self.settings_button.mapToGlobal(self.settings_button.rect().bottomLeft())
        )
        if chosen and chosen.isEnabled() and chosen.data():
            new_id = chosen.data()
            self._active_model_id = new_id
            self._update_settings_tooltip()
            self.model_changed.emit(new_id)

    # ── Streaming ──────────────────────────────────────────────────

    def start_ai_stream(self) -> None:
        """Create a streaming bubble and add it to the chat."""
        bubble = BubbleWidget("AI", "<p>▌</p>", "")
        self._current_messages.append(("AI", "", ""))  # placeholder
        self.bubble_layout.insertWidget(self.bubble_layout.count() - 1, bubble)
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )
        self._streaming_bubble = bubble

    def append_stream_chunk(self, chunk: str) -> None:
        """Called from main on each streamed chunk."""
        if self._streaming_bubble:
            self._streaming_bubble.update_stream(chunk)
            self.scroll_area.verticalScrollBar().setValue(
                self.scroll_area.verticalScrollBar().maximum()
            )

    def finalize_stream_bubble(self) -> None:
        """Finalize the streaming bubble and store final text in history."""
        if self._streaming_bubble:
            self._streaming_bubble.finalize_stream()
            if self._current_messages:
                plain = self._streaming_bubble._plain_text
                content_html = self._streaming_bubble._content.toHtml()
                self._current_messages[-1] = ("AI", plain, content_html)
        self._streaming_bubble = None

    def _add_bubble(self, role: str, plain: str, content_html: str) -> None:
        self._current_messages.append((role, plain, content_html))
        bubble = BubbleWidget(role, content_html, plain)
        # Insert before the trailing stretch
        self.bubble_layout.insertWidget(self.bubble_layout.count() - 1, bubble)
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    def _clear_chat(self) -> None:
        self._current_messages = []
        self._streaming_bubble = None
        while self.bubble_layout.count() > 1:
            item = self.bubble_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _submit(self) -> None:
        text = self.input.text().strip()
        if self._busy or not text:
            return
        self.input.clear()
        self.message_submitted.emit(text)

    def _on_input_changed(self, text: str) -> None:
        self.chips_widget.setVisible(not bool(text))

    def _on_chip_clicked(self, label: str) -> None:
        self.input.setText(label)
        self._submit()

    def _show_history_menu(self) -> None:
        if not self._history:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu {"
            "  background-color: rgba(18,24,38,245);"
            "  border: 1px solid rgba(130,154,196,110);"
            "  border-radius: 8px;"
            "  color: #f5f7fb;"
            "  font-family: 'Segoe UI';"
            "  padding: 4px;"
            "}"
            "QMenu::item { padding: 5px 14px; border-radius: 5px; }"
            "QMenu::item:selected { background-color: rgba(71,134,255,140); }"
        )
        for i, (sel_text, messages) in enumerate(self._history):
            truncated = (sel_text[:44] + "…") if len(sel_text) > 44 else sel_text
            count = len(messages)
            action = menu.addAction(f"{truncated}  ({count} msg{'s' if count != 1 else ''})")
            action.setData(i)

        chosen = menu.exec(
            self.history_button.mapToGlobal(self.history_button.rect().bottomLeft())
        )
        if chosen and chosen.data() is not None:
            self._restore_session(chosen.data())

    def _restore_session(self, index: int) -> None:
        sel_text, messages = self._history[index]
        if self._current_messages:
            self._history.appendleft((self.current_selection, list(self._current_messages)))
            self.history_button.setVisible(True)
        self.current_selection = sel_text
        self.selection_view.setText(" ".join(sel_text.splitlines()).strip())
        self.selection_view.setCursorPosition(0)
        self._clear_chat()
        for role, plain, content_html in messages:
            bubble = BubbleWidget(role, content_html, plain)
            self.bubble_layout.insertWidget(self.bubble_layout.count() - 1, bubble)
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

    # ──────────────────────────────────────────────────────────────
    # Qt overrides
    # ──────────────────────────────────────────────────────────────

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._grip._reposition()
        self._grip.raise_()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.closed.emit()

    def event(self, event) -> bool:
        if event.type() == QEvent.WindowDeactivate and self.isVisible() and not self._pinned:
            self.hide()
        return super().event(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._dragging = False
        super().mouseReleaseEvent(event)

    def _move_near_cursor(self, x: int, y: int) -> None:
        screen = QGuiApplication.screenAt(QPoint(x, y)) or QGuiApplication.primaryScreen()
        if not screen:
            self.move(x + 16, y + 20)
            return
        avail = screen.availableGeometry()
        tx, ty = x + 16, y + 20
        w = self.width() if self.width() > 0 else self.minimumWidth()
        h = self.height() if self.height() > 0 else self.minimumHeight()
        if tx + w > avail.right():
            tx = max(avail.left(), x - w - 16)
        if ty + h > avail.bottom():
            ty = max(avail.top(), y - h - 16)
        self.move(tx, ty)

    @staticmethod
    def _markdown_to_html(markdown_text: str) -> str:
        return _md_to_html(markdown_text)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #f5f7fb; font-family: 'Segoe UI'; }

            QFrame#card {
                background-color: rgba(18, 24, 38, 215);
                border: 1px solid rgba(130, 154, 196, 110);
                border-radius: 12px;
            }
            QLabel#sectionTitle {
                font-size: 11px; font-weight: 700; color: #b9c7e6;
            }

            /* Scroll area */
            QScrollArea#chatBox {
                background-color: rgba(8, 14, 28, 145);
                border: 1px solid rgba(109, 135, 180, 100);
                border-radius: 8px;
            }
            QWidget#bubbleContainer { background: transparent; }

            /* Bubble */
            QFrame#bubble {
                background-color: rgba(7, 14, 30, 140);
                border: 1px solid rgba(110, 140, 190, 90);
                border-radius: 8px;
            }
            QLabel#roleLabel {
                font-weight: 700; color: #b7caf7; font-size: 11px;
            }
            QTextBrowser#bubbleContent {
                background: transparent; border: none; color: #eef4ff; padding: 0px;
            }

            /* Copy button */
            QPushButton#copyButton {
                background-color: rgba(255,255,255,20);
                border: 1px solid rgba(255,255,255,40);
                border-radius: 5px; color: #b9c7e6; font-size: 11px; padding: 0px;
            }
            QPushButton#copyButton:hover {
                background-color: rgba(71,134,255,120);
                border-color: rgba(148,186,255,180);
            }

            /* Chips */
            QPushButton#chipButton {
                background-color: rgba(71,134,255,55);
                border: 1px solid rgba(148,186,255,110);
                border-radius: 10px; padding: 3px 10px;
                font-size: 11px; color: #c8d8ff;
            }
            QPushButton#chipButton:hover { background-color: rgba(71,134,255,130); }

            /* History button */
            QPushButton#historyButton {
                background-color: rgba(255,255,255,20);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 8px; padding: 2px 8px;
                font-size: 11px; color: #b9c7e6;
            }
            QPushButton#historyButton:hover { background-color: rgba(255,255,255,40); }

            /* Fields */
            QLineEdit#selectionBox {
                background-color: rgba(8,14,28,145);
                border: 1px solid rgba(109,135,180,100);
                border-radius: 8px; padding: 6px 8px;
            }
            QLineEdit#promptInput {
                background-color: rgba(8,14,28,170);
                border: 1px solid rgba(109,135,180,120);
                border-radius: 8px; padding: 7px 10px; color: #f5f7fb;
            }

            /* Send button */
            QPushButton#sendButton {
                background-color: rgba(71,134,255,210);
                border: 1px solid rgba(148,186,255,180);
                border-radius: 8px; padding: 6px 12px; font-weight: 700;
            }
            QPushButton#sendButton:hover { background-color: rgba(98,154,255,230); }

            /* Close button */
            QPushButton#closeButton {
                background-color: rgba(255,255,255,30);
                border: 1px solid rgba(255,255,255,60);
                border-radius: 8px; color: #dbe8ff; font-weight: 700;
            }
            QPushButton#closeButton:hover {
                background-color: rgba(255,99,99,160);
                border-color: rgba(255,140,140,220);
            }

            /* Settings button */
            QPushButton#settingsButton {
                background-color: rgba(255,255,255,20);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 8px; color: #dbe8ff; font-weight: 700;
            }
            QPushButton#settingsButton:hover { background-color: rgba(71,134,255,120); }

            /* Pin button */
            QPushButton#pinButton {
                background-color: rgba(255,255,255,20);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 8px; color: #dbe8ff; font-weight: 700;
            }
            QPushButton#pinButton:hover { background-color: rgba(255,255,255,40); }
            QPushButton#pinButtonActive {
                background-color: rgba(71,134,255,180);
                border: 1px solid rgba(148,186,255,200);
                border-radius: 8px; color: #ffffff; font-weight: 700;
            }
            QPushButton#pinButtonActive:hover { background-color: rgba(98,154,255,210); }

            QSizeGrip { background: transparent; border: none; }
            """
        )
