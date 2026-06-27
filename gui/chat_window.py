from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QListWidget, QSplitter,
    QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPointF, QRectF, QDateTime
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPixmap
from gui.signals import event_bus
from network.client import send_chat_message, send_file_attachment
from storage.database import get_history, save_message, get_all_chat_peers, get_unread_count, mark_as_read
import config


# ── Inline logo widget ─────────────────────────────────────────────────────────
class PeerChatLogo(QWidget):
    """Draws the PeerChat logo inline using QPainter — no image file required."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(216, 68)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        blue = QColor("#89b4fa")
        dim = QColor("#313244")
        dim_line = QColor("#2a2a3d")
        text_main = QColor("#cdd6f4")

        cx, cy = 108, 28

        # ── satellite nodes (dim, dashed) ─────────────────────────
        pen_dim = QPen(dim_line, 1.2, Qt.PenStyle.DashLine)
        p.setPen(pen_dim)
        p.setBrush(Qt.BrushStyle.NoBrush)

        satellites = [(-52, -18), (-52, 18), (52, -18), (52, 18)]
        anchors = [(-26, 0), (-26, 0), (26, 0), (26, 0)]
        for (sx, sy), (ax, ay) in zip(satellites, anchors):
            p.drawLine(
                int(cx + ax), int(cy + ay),
                int(cx + sx), int(cy + sy)
            )

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dim))
        for sx, sy in satellites:
            p.drawEllipse(QPointF(cx + sx, cy + sy), 3.5, 3.5)

        # ── center dim node ────────────────────────────────────────
        p.setBrush(QBrush(dim))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)

        # ── connector lines ────────────────────────────────────────
        pen_solid = QPen(blue, 1.5)
        p.setPen(pen_solid)
        p.drawLine(int(cx - 26), int(cy), int(cx - 14), int(cy))
        p.drawLine(int(cx + 14), int(cy), int(cx + 26), int(cy))

        # dim centre gap
        pen_gap = QPen(dim_line, 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen_gap)
        p.drawLine(int(cx - 14), int(cy), int(cx + 14), int(cy))

        # ── primary nodes (ringed) ─────────────────────────────────
        pen_ring = QPen(blue, 1.8)
        p.setPen(pen_ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for nx in (-26, 26):
            p.drawEllipse(QPointF(cx + nx, cy), 10, 10)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(blue))
        for nx in (-26, 26):
            p.drawEllipse(QPointF(cx + nx, cy), 4, 4)

        # ── wordmark ───────────────────────────────────────────────
        font_peer = QFont("Segoe UI", 15, QFont.Weight.ExtraBold)
        font_chat = QFont("Segoe UI", 15, QFont.Weight.ExtraBold)

        p.setFont(font_peer)
        p.setPen(QPen(text_main))
        p.drawText(QRectF(0, 40, 108, 26), Qt.AlignmentFlag.AlignRight, "Peer")

        p.setFont(font_chat)
        p.setPen(QPen(blue))
        p.drawText(QRectF(108, 40, 108, 26), Qt.AlignmentFlag.AlignLeft, "Chat")

        p.end()


# ── Main chat window ───────────────────────────────────────────────────────────
class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeerChat")
        self.setMinimumSize(860, 580)
        self.showMaximized()

        self.current_chat_target = "Global Chat"
        self.recent_rendered_messages = set()

        self.init_ui()

        event_bus.message_received.connect(self.handle_incoming_signal)
        event_bus.message_status_updated.connect(self.handle_status_update)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_peer_list)
        self.refresh_timer.start(2000)

        self.load_history_from_db()

    def init_ui(self):
        self.setStyleSheet("""
            /* ── BASE ─────────────────────────────────────────────── */
            QWidget {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            }

            /* ── SPLITTER ─────────────────────────────────────────── */
            QSplitter::handle {
                background-color: #2a2a3d;
                width: 1px;
            }

            /* ── SIDEBAR LIST ─────────────────────────────────────── */
            QListWidget {
                background-color: transparent;
                border: none;
                padding: 4px 0px;
                outline: none;
            }
            QListWidget::item {
                padding: 13px 18px;
                margin: 3px 6px;
                border-radius: 10px;
                color: #7f849c;
                font-size: 13px;
                font-weight: 500;
            }
            QListWidget::item:hover {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QListWidget::item:selected {
                background-color: #1e3a5f;
                color: #89b4fa;
                font-weight: 700;
            }

            /* ── CHAT DISPLAY ─────────────────────────────────────── */
            QTextEdit {
                background-color: #11111b;
                border-radius: 16px;
                border: 1px solid #2a2a3d;
                padding: 18px 20px;
                font-size: 13px;
                line-height: 1.6;
                color: #cdd6f4;
            }
            QTextEdit QScrollBar:vertical {
                background: transparent;
                width: 6px;
                margin: 4px 0;
            }
            QTextEdit QScrollBar::handle:vertical {
                background: #313244;
                border-radius: 3px;
                min-height: 20px;
            }
            QTextEdit QScrollBar::add-line:vertical,
            QTextEdit QScrollBar::sub-line:vertical {
                height: 0px;
            }

            /* ── INPUT ────────────────────────────────────────────── */
            QLineEdit {
                background-color: #11111b;
                border-radius: 14px;
                padding: 12px 18px;
                border: 1.5px solid #2a2a3d;
                font-size: 13px;
                color: #cdd6f4;
                font-weight: 400;
            }
            QLineEdit:focus {
                border: 1.5px solid #89b4fa;
                background-color: #13131f;
            }
            QLineEdit::placeholder {
                color: #45475a;
            }

            /* ── BUTTONS ──────────────────────────────────────────── */
            QPushButton#SendButton {
                background-color: #89b4fa;
                color: #11111b;
                border-radius: 14px;
                padding: 12px 26px;
                font-weight: 800;
                font-size: 13px;
                border: none;
            }
            QPushButton#SendButton:hover  { background-color: #a6c8ff; }
            QPushButton#SendButton:pressed { background-color: #74a8f8; }

            QPushButton#AttachButton {
                background-color: #181825;
                color: #6c7086;
                font-size: 16px;
                border-radius: 14px;
                padding: 10px 16px;
                border: 1.5px solid #2a2a3d;
            }
            QPushButton#AttachButton:hover {
                background-color: #1e1e2e;
                color: #89b4fa;
                border-color: #89b4fa;
            }

            /* ── LABELS ───────────────────────────────────────────── */
            QLabel#MyIDLabel {
                color: #6c7086;
                font-size: 12px;
                font-weight: 400;
            }
            QLabel#ChatStatus {
                font-size: 15px;
                font-weight: 700;
                color: #cdd6f4;
            }
            QLabel#ChatStatusSub {
                font-size: 12px;
                color: #7f849c;
                font-weight: 400;
            }
            QLabel#SidebarHeader {
                font-weight: 700;
                color: #6c7086;
                font-size: 10px;
                letter-spacing: 1.2px;
                padding-left: 6px;
            }
            QLabel#OnlineIndicator {
                color: #a6e3a1;
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.3px;
            }

            /* ── DIVIDER ──────────────────────────────────────────── */
            QFrame#Divider {
                background-color: #2a2a3d;
                max-height: 1px;
            }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        # ── SIDEBAR ────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(252)
        sidebar.setStyleSheet("background-color: #11111b;")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 22, 16, 20)
        sl.setSpacing(10)

        # Logo
        logo = PeerChatLogo()
        logo_row = QHBoxLayout()
        logo_row.addWidget(logo)
        logo_row.addStretch()

        my_id = QLabel(f"@{config.PEER_ID}")
        my_id.setObjectName("MyIDLabel")

        divider_top = QFrame()
        divider_top.setObjectName("Divider")
        divider_top.setFrameShape(QFrame.Shape.HLine)

        ch_header = QLabel("CHANNELS & PEERS")
        ch_header.setObjectName("SidebarHeader")

        self.peer_list_widget = QListWidget()
        self.peer_list_widget.addItem("Global Chat")
        self.peer_list_widget.setCurrentRow(0)
        self.peer_list_widget.itemClicked.connect(self.switch_chat_context)

        sl.addLayout(logo_row)
        sl.addWidget(my_id)
        sl.addSpacing(6)
        sl.addWidget(divider_top)
        sl.addSpacing(6)
        sl.addWidget(ch_header)
        sl.addWidget(self.peer_list_widget)

        # ── MAIN CHAT AREA ─────────────────────────────────────────
        chat_area = QWidget()
        cl = QVBoxLayout(chat_area)
        cl.setContentsMargins(20, 20, 20, 20)
        cl.setSpacing(14)

        # Chat header
        chat_header_row = QHBoxLayout()
        chat_header_row.setSpacing(10)

        chat_header_left = QVBoxLayout()
        chat_header_left.setSpacing(2)

        self.chat_status_label = QLabel("Global Chat")
        self.chat_status_label.setObjectName("ChatStatus")

        self.chat_status_sub = QLabel("Public channel · all peers")
        self.chat_status_sub.setObjectName("ChatStatusSub")

        chat_header_left.addWidget(self.chat_status_label)
        chat_header_left.addWidget(self.chat_status_sub)

        self.online_indicator = QLabel("")
        self.online_indicator.setObjectName("OnlineIndicator")
        self.online_indicator.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        chat_header_row.addLayout(chat_header_left)
        chat_header_row.addStretch()
        chat_header_row.addWidget(self.online_indicator)

        divider_chat = QFrame()
        divider_chat.setObjectName("Divider")
        divider_chat.setFrameShape(QFrame.Shape.HLine)

        # Message display
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.attach_button = QPushButton("📎")
        self.attach_button.setObjectName("AttachButton")
        self.attach_button.setFixedSize(46, 46)
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.clicked.connect(self.attach_file)

        self.input_box = QLineEdit()
        self.input_box.setMinimumHeight(46)
        self.input_box.setPlaceholderText("Message your peers...")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setMinimumHeight(46)
        self.send_button.setFixedWidth(90)
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_message)

        input_row.addWidget(self.attach_button)
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)

        cl.addLayout(chat_header_row)
        cl.addWidget(divider_chat)
        cl.addWidget(self.chat_box)
        cl.addLayout(input_row)

        splitter.addWidget(sidebar)
        splitter.addWidget(chat_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

    # ── Logic ──────────────────────────────────────────────────────

    def attach_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if not file_path:
            return
        recipient = None if self.current_chat_target == "Global Chat" else self.current_chat_target
        file_name, msg_id = send_file_attachment(file_path, recipient)
        if file_name and msg_id:
            display_msg = f"📎 Sent a file: {file_name}"
            save_message(config.PEER_ID, display_msg, recipient)

            timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
            self.append_to_ui(config.PEER_ID, f"[{display_msg} {timestamp}]", msg_id=msg_id, initial_status="✓")

    def update_peer_list(self):
        from network.discover import peer_ids
        current_item = self.peer_list_widget.currentItem()
        selected_name = (
            current_item.text()
            if current_item and current_item.text() != "Global Chat"
            else "Global Chat"
        )
        self.peer_list_widget.clear()

        global_unread = get_unread_count("Global Chat")
        global_text = "Global Chat"
        if global_unread > 0:
            global_text = f"Global Chat ({global_unread})"
        self.peer_list_widget.addItem(global_text)

        online_peers = {
            str(pid) for pid in peer_ids.values() if str(pid) != str(config.PEER_ID)
        }
        historical_peers = set(get_all_chat_peers())
        for peer in sorted(historical_peers | online_peers):
            unread = get_unread_count(peer)
            peer_text = peer
            if unread > 0:
                peer_text = f"{peer} ({unread})"
            self.peer_list_widget.addItem(peer_text)

        if self.current_chat_target != "Global Chat":
            self.online_indicator.setText(
                "● online" if self.current_chat_target in online_peers else ""
            )

        items = (
            self.peer_list_widget.findItems("Global Chat", Qt.MatchFlag.MatchContains)
            if selected_name == "Global Chat"
            else self.peer_list_widget.findItems(selected_name, Qt.MatchFlag.MatchContains)
        )
        if items:
            self.peer_list_widget.setCurrentItem(items[0])

    def switch_chat_context(self, item):
        text = item.text()
        peer_name = text.split(" (")[0] if " (" in text else text

        if peer_name == "Global Chat":
            self.current_chat_target = "Global Chat"
            self.chat_status_label.setText("Global Chat")
            self.chat_status_sub.setText("Public channel · all peers")
            self.online_indicator.setText("")
        else:
            from network.discover import peer_ids
            online_peers = {str(pid) for pid in peer_ids.values() if str(pid) != str(config.PEER_ID)}
            self.current_chat_target = peer_name
            self.chat_status_label.setText(peer_name)
            self.chat_status_sub.setText("Private conversation · end-to-end")
            self.online_indicator.setText("● online" if peer_name in online_peers else "")

        mark_as_read(self.current_chat_target)
        self.load_history_from_db()
        self.update_peer_list()

    def load_history_from_db(self):
        self.chat_box.clear()
        target = None if self.current_chat_target == "Global Chat" else self.current_chat_target
        for sender, message, timestamp, is_read in get_history(target):
            self.append_to_ui(sender, f"[{timestamp}] {message}",
                              initial_status="✓✓" if sender == config.PEER_ID else "")

    def send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        recipient = None if self.current_chat_target == "Global Chat" else self.current_chat_target
        msg_id = send_chat_message(text, recipient)
        save_message(config.PEER_ID, text, recipient)

        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.append_to_ui(config.PEER_ID, f"{text} [{timestamp}]", msg_id=msg_id, initial_status="✓")
        self.input_box.clear()

    def handle_incoming_signal(self, sender, message, recipient):
        sig = f"{sender}:{recipient}:{message}"
        if sig in self.recent_rendered_messages:
            return
        self.recent_rendered_messages.add(sig)
        QTimer.singleShot(3000, lambda: self.recent_rendered_messages.discard(sig))
        if sender == config.PEER_ID:
            return
        show = (
                (recipient is None and self.current_chat_target == "Global Chat") or
                (recipient == config.PEER_ID and sender == self.current_chat_target) or
                (sender == config.PEER_ID and recipient == self.current_chat_target)
        )
        if show:
            timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
            self.append_to_ui(sender, f"{message} [{timestamp}]")
        else:
            self.update_peer_list()

    def handle_status_update(self, msg_id, status):
        if status == "delivered":
            current_html = self.chat_box.toHtml()
            target_id_string = f'id="{msg_id}"'
            if target_id_string in current_html:
                updated_html = current_html.replace(f'id="{msg_id}">✓', f'id="{msg_id}">✓✓')
                scrollbar_pos = self.chat_box.verticalScrollBar().value()
                self.chat_box.setHtml(updated_html)
                self.chat_box.verticalScrollBar().setValue(scrollbar_pos)

    def get_peer_color(self, username: str) -> str:
        colors = [
            "#f5e0dc", "#f2cdcd", "#f5bde6", "#cba6f7", "#f38ba8",
            "#eba0ac", "#fab387", "#f9e2af", "#a6e3a1", "#94e2d5",
            "#89dceb", "#74c7ec", "#b4befe"
        ]
        hash_value = abs(hash(username))
        return colors[hash_value % len(colors)]

    def append_to_ui(self, sender, message, msg_id="", initial_status=""):
        is_me = sender == config.PEER_ID

        # Generate configuration metrics based on ownership
        if is_me:
            color = "#b4befe"
            label = "You"
            align = "left"
            bg_color = "transparent"  # Removed background color
            text_color = "#cdd6f4"
            border_style = ""
        else:
            color = self.get_peer_color(sender)
            label = sender
            align = "right"
            bg_color = "transparent"  # Removed background color
            text_color = "#cdd6f4"
            border_style = ""

        if "📎" in message:
            bg_color = "#1a2535"  # Keeps the attachment background if desired, or change to "transparent"
            text_color = "#a6e3a1"
            border_style = "border-left: 3px solid #a6e3a1;"

        status_span = f"&nbsp;<span id='{msg_id}' style='color: #a6e3a1; font-weight: bold;'>{initial_status}</span>" if (
                is_me and initial_status) else ""

        # Use an absolute table structure to pin username tightly on top of the bubble element
        formatted_table = (
            f"<table width='100%' border='0' cellspacing='0' cellpadding='0' style='margin: 4px 0;'>"
            f"  <tr>"
            f"    <td align='{align}'>"
            f"      <table border='0' cellspacing='0' cellpadding='0' style='max-width: 75%;'>"
            f"        <tr>"
            f"          <td align='{align}' style='padding-bottom: 2px;'>"
            f"            <span style='color: {color}; font-weight: 700; font-size: 12px;'>{label}</span>"
            f"          </td>"
            f"        </tr>"
            f"        <tr>"
            f"          <td align='left' style='background-color: {bg_color}; padding: 8px 14px; border-radius: 10px; {border_style}'>"
            f"            <span style='color: {text_color}; font-size: 14px;'>{message}</span>{status_span}"
            f"          </td>"
            f"        </tr>"
            f"      </table>"
        )

        cursor = self.chat_box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertHtml(formatted_table)
        cursor.insertBlock()

        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())