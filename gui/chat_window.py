import os
import re
import tempfile
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTextBrowser,
    QLineEdit, QPushButton, QLabel, QListWidget, QSplitter,
    QFileDialog, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QSize, QPointF, QRectF, QDateTime, QUrl
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPixmap
from PyQt6.QtMultimedia import (
    QMediaPlayer, QAudioOutput, QMediaRecorder, QMediaFormat,
    QAudioInput, QMediaCaptureSession, QMediaDevices
)
from gui.signals import event_bus
from network.client import send_chat_message, send_file_attachment
from storage.database import get_history, save_message, get_all_chat_peers, get_unread_count, mark_as_read
import config


class PeerChatLogo(QWidget):
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

        pen_dim = QPen(dim_line, 1.2, Qt.PenStyle.DashLine)
        p.setPen(pen_dim)
        satellites = [(-52, -18), (-52, 18), (52, -18), (52, 18)]
        anchors = [(-26, 0), (-26, 0), (26, 0), (26, 0)]
        for (sx, sy), (ax, ay) in zip(satellites, anchors):
            p.drawLine(int(cx + ax), int(cy + ay), int(cx + sx), int(cy + sy))

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(dim))
        for sx, sy in satellites:
            p.drawEllipse(QPointF(cx + sx, cy + sy), 3.5, 3.5)

        p.drawEllipse(QPointF(cx, cy), 3.5, 3.5)
        pen_solid = QPen(blue, 1.5)
        p.setPen(pen_solid)
        p.drawLine(int(cx - 26), int(cy), int(cx - 14), int(cy))
        p.drawLine(int(cx + 14), int(cy), int(cx + 26), int(cy))

        pen_gap = QPen(dim_line, 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen_gap)
        p.drawLine(int(cx - 14), int(cy), int(cx + 14), int(cy))

        pen_ring = QPen(blue, 1.8)
        p.setPen(pen_ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for nx in (-26, 26):
            p.drawEllipse(QPointF(cx + nx, cy), 10, 10)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(blue))
        for nx in (-26, 26):
            p.drawEllipse(QPointF(cx + nx, cy), 4, 4)

        p.setFont(QFont("Segoe UI", 15, QFont.Weight.ExtraBold))
        p.setPen(QPen(text_main))
        p.drawText(QRectF(0, 40, 108, 26), Qt.AlignmentFlag.AlignRight, "Peer")
        p.setPen(QPen(blue))
        p.drawText(QRectF(108, 40, 108, 26), Qt.AlignmentFlag.AlignLeft, "Chat")
        p.end()


class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PeerChat")
        self.setMinimumSize(860, 580)
        self.showMaximized()

        self.current_chat_target = "Global Chat"
        self.recent_rendered_messages = set()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.playbackStateChanged.connect(self.handle_playback_state_change)

        self.session = QMediaCaptureSession()
        self.audio_input = QAudioInput(QMediaDevices.defaultAudioInput())
        self.recorder = QMediaRecorder()

        self.session.setAudioInput(self.audio_input)
        self.session.setRecorder(self.recorder)

        self.init_ui()

        event_bus.message_received.connect(self.handle_incoming_signal)
        event_bus.message_status_updated.connect(self.handle_status_update)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_peer_list)
        self.refresh_timer.start(2000)

        self.load_history_from_db()

    def init_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', system-ui, sans-serif; }
            QSplitter::handle { background-color: #2a2a3d; width: 1px; }
            QListWidget { background-color: transparent; border: none; padding: 4px 0px; outline: none; }
            QListWidget::item { padding: 13px 18px; margin: 3px 6px; border-radius: 10px; color: #7f849c; font-size: 13px; font-weight: 500; }
            QListWidget::item:hover { background-color: #1e1e2e; color: #cdd6f4; }
            QListWidget::item:selected { background-color: #1e3a5f; color: #89b4fa; font-weight: 700; }
            QTextBrowser { background-color: #11111b; border-radius: 16px; border: 1px solid #2a2a3d; padding: 18px 20px; font-size: 13px; line-height: 1.6; color: #cdd6f4; }
            QLineEdit { background-color: #11111b; border-radius: 14px; padding: 12px 18px; border: 1.5px solid #2a2a3d; font-size: 13px; color: #cdd6f4; }
            QLineEdit:focus { border: 1.5px solid #89b4fa; background-color: #13131f; }
            QPushButton#SendButton { background-color: #89b4fa; color: #11111b; border-radius: 14px; padding: 12px 26px; font-weight: 800; font-size: 13px; border: none; }
            QPushButton#SendButton:hover  { background-color: #a6c8ff; }
            QPushButton#AttachButton { background-color: #181825; color: #6c7086; font-size: 16px; border-radius: 14px; padding: 10px 16px; border: 1.5px solid #2a2a3d; }
            QPushButton#AttachButton:hover { background-color: #1e1e2e; color: #89b4fa; border-color: #89b4fa; }
            QLabel#ChatStatus { font-size: 15px; font-weight: 700; color: #cdd6f4; }
            QLabel#ChatStatusSub { font-size: 12px; color: #7f849c; }
            QFrame#Divider { background-color: #2a2a3d; max-height: 1px; }
            QWidget#AudioHUD { background-color: #11111b; border: 1px solid #cba6f7; border-radius: 10px; padding: 6px 12px; }
            QPushButton#StopHUDButton { background-color: #f38ba8; color: #11111b; font-weight: bold; border-radius: 6px; border: none; padding: 4px 10px; }
            QPushButton#StopHUDButton:hover { background-color: #eba0ac; }
        """)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)

        sidebar = QWidget()
        sidebar.setFixedWidth(252)
        sidebar.setStyleSheet("background-color: #11111b;")
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(16, 22, 16, 20)
        sl.setSpacing(10)

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
        ch_header.setStyleSheet("font-weight: 700; color: #6c7086; font-size: 10px; letter-spacing: 1.2px;")

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

        chat_area = QWidget()
        cl = QVBoxLayout(chat_area)
        cl.setContentsMargins(20, 20, 20, 20)
        cl.setSpacing(14)

        chat_header_row = QHBoxLayout()
        chat_header_left = QVBoxLayout()

        self.chat_status_label = QLabel("Global Chat")
        self.chat_status_label.setObjectName("ChatStatus")
        self.chat_status_sub = QLabel("Public channel · all peers")
        self.chat_status_sub.setObjectName("ChatStatusSub")

        chat_header_left.addWidget(self.chat_status_label)
        chat_header_left.addWidget(self.chat_status_sub)
        chat_header_row.addLayout(chat_header_left)
        chat_header_row.addStretch()

        self.online_indicator = QLabel("")
        self.online_indicator.setStyleSheet("color: #a6e3a1; font-weight: 600; font-size: 11px;")
        chat_header_row.addWidget(self.online_indicator)

        divider_chat = QFrame()
        divider_chat.setObjectName("Divider")
        divider_chat.setFrameShape(QFrame.Shape.HLine)

        self.chat_box = QTextBrowser()
        self.chat_box.setReadOnly(True)
        self.chat_box.setOpenLinks(False)
        self.chat_box.anchorClicked.connect(self.handle_link_click)

        self.audio_hud = QWidget()
        self.audio_hud.setObjectName("AudioHUD")
        hud_layout = QHBoxLayout(self.audio_hud)
        hud_layout.setContentsMargins(6, 4, 6, 4)

        self.hud_label = QLabel("🎵 System Idle...")
        self.hud_label.setStyleSheet("font-size: 12px; color: #cba6f7; font-weight: 600;")
        self.stop_hud_btn = QPushButton("Stop 🛑")
        self.stop_hud_btn.setObjectName("StopHUDButton")
        self.stop_hud_btn.clicked.connect(self.stop_audio_playback)

        hud_layout.addWidget(self.hud_label)
        hud_layout.addStretch()
        hud_layout.addWidget(self.stop_hud_btn)
        self.audio_hud.setVisible(False)

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self.attach_button = QPushButton("📎")
        self.attach_button.setObjectName("AttachButton")
        self.attach_button.setFixedSize(46, 46)
        self.attach_button.clicked.connect(self.attach_file)

        self.voice_button = QPushButton("🎤")
        self.voice_button.setObjectName("AttachButton")
        self.voice_button.setFixedSize(46, 46)
        self.voice_button.setCheckable(True)
        self.voice_button.clicked.connect(self.toggle_voice_recording)

        self.input_box = QLineEdit()
        self.input_box.setMinimumHeight(46)
        self.input_box.setPlaceholderText("Message your peers...")
        self.input_box.returnPressed.connect(self.send_message)

        self.send_button = QPushButton("Send")
        self.send_button.setObjectName("SendButton")
        self.send_button.setMinimumHeight(46)
        self.send_button.setFixedWidth(90)
        self.send_button.clicked.connect(self.send_message)

        input_row.addWidget(self.attach_button)
        input_row.addWidget(self.voice_button)
        input_row.addWidget(self.input_box)
        input_row.addWidget(self.send_button)

        cl.addLayout(chat_header_row)
        cl.addWidget(divider_chat)
        cl.addWidget(self.chat_box)
        cl.addWidget(self.audio_hud)
        cl.addLayout(input_row)

        splitter.addWidget(sidebar)
        splitter.addWidget(chat_area)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)

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
            self.append_to_ui(config.PEER_ID, f"[{timestamp}] {display_msg}", initial_status="✓")

    def toggle_voice_recording(self):
        if self.voice_button.isChecked():
            self.voice_button.setText("🛑")
            self.voice_button.setStyleSheet("background-color: #f38ba8; color: #11111b; border-color: #f38ba8;")
            self.current_vn_path = os.path.join(tempfile.gettempdir(),
                                                f"vnote_{QDateTime.currentMSecsSinceEpoch()}.wav")

            fmt = QMediaFormat()
            fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
            fmt.setAudioCodec(QMediaFormat.AudioCodec.Wave)

            self.recorder.setMediaFormat(fmt)
            self.recorder.setOutputLocation(QUrl.fromLocalFile(self.current_vn_path))
            self.recorder.record()
        else:
            self.voice_button.setText("🎤")
            self.voice_button.setStyleSheet("")
            self.recorder.stop()
            QTimer.singleShot(400, self.process_and_send_voice_note)

    def process_and_send_voice_note(self):
        if hasattr(self, 'current_vn_path') and os.path.exists(self.current_vn_path):
            if os.path.getsize(self.current_vn_path) > 0:
                recipient = None if self.current_chat_target == "Global Chat" else self.current_chat_target
                file_name, msg_id = send_file_attachment(self.current_vn_path, recipient)
                if file_name and msg_id:
                    display_msg = f"📎 Sent a file: {file_name}"
                    save_message(config.PEER_ID, display_msg, recipient)
                    timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
                    self.append_to_ui(config.PEER_ID, f"[{timestamp}] {display_msg}", initial_status="✓")

    def handle_link_click(self, url):
        link_str = url.toString()
        if link_str.startswith("file:///"):
            local_path = url.toLocalFile()
            if os.path.exists(local_path):
                self.player.setSource(QUrl.fromLocalFile(local_path))
                self.audio_output.setVolume(1.0)
                self.player.play()
                self.hud_label.setText(f"🔊 Playing Audio Track: {os.path.basename(local_path)}")
                self.audio_hud.setVisible(True)

    def stop_audio_playback(self):
        self.player.stop()
        self.audio_hud.setVisible(False)

    def handle_playback_state_change(self, state):
        if state == QMediaPlayer.PlaybackState.StoppedState:
            self.audio_hud.setVisible(False)

    def update_peer_list(self):
        from network.discover import peer_ids
        current_item = self.peer_list_widget.currentItem()
        selected_name = current_item.text().split(" (")[0] if current_item else "Global Chat"
        self.peer_list_widget.clear()

        global_unread = get_unread_count("Global Chat")
        global_text = f"Global Chat ({global_unread})" if global_unread > 0 else "Global Chat"
        self.peer_list_widget.addItem(global_text)

        online_peers = {str(pid) for pid in peer_ids.values() if str(pid) != str(config.PEER_ID)}
        historical_peers = set(get_all_chat_peers())
        for peer in sorted(historical_peers | online_peers):
            unread = get_unread_count(peer)
            peer_text = f"{peer} ({unread})" if unread > 0 else peer
            self.peer_list_widget.addItem(peer_text)

        if self.current_chat_target != "Global Chat":
            self.online_indicator.setText("● online" if self.current_chat_target in online_peers else "")

        items = self.peer_list_widget.findItems(selected_name, Qt.MatchFlag.MatchContains)
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

        history_records = get_history(target)
        for row in history_records:
            sender = row[0]
            message = row[1]
            timestamp = row[2]
            self.append_to_ui(sender, f"[{timestamp}] {message}",
                              initial_status="✓✓" if sender == config.PEER_ID else "")

    def send_message(self):
        text = self.input_box.text().strip()
        if not text:
            return
        recipient = None if self.current_chat_target == "Global Chat" else self.current_chat_target
        send_chat_message(text, recipient)
        save_message(config.PEER_ID, text, recipient)

        timestamp = QDateTime.currentDateTime().toString("yyyy-MM-dd hh:mm:ss")
        self.append_to_ui(config.PEER_ID, f"[{timestamp}] {text}", initial_status="✓")
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
            self.append_to_ui(sender, f"[{timestamp}] {message}")
        else:
            self.update_peer_list()

    def handle_status_update(self, msg_id, status):
        if status == "delivered":
            current_html = self.chat_box.toHtml()
            if f'id="{msg_id}"' in current_html:
                updated_html = current_html.replace(f'id="{msg_id}">✓', f'id="{msg_id}">✓✓')
                scrollbar_pos = self.chat_box.verticalScrollBar().value()
                self.chat_box.setHtml(updated_html)
                self.chat_box.verticalScrollBar().setValue(scrollbar_pos)

    def get_peer_color(self, username: str) -> str:
        colors = ["#f5e0dc", "#f2cdcd", "#f5bde6", "#cba6f7", "#f38ba8", "#eba0ac", "#fab387", "#f9e2af", "#a6e3a1",
                  "#94e2d5", "#89dceb", "#74c7ec", "#b4befe"]
        return colors[abs(hash(username)) % len(colors)]

    def append_to_ui(self, sender, message, initial_status=""):
        is_me = sender == config.PEER_ID
        color = "#b4befe" if is_me else self.get_peer_color(sender)
        label = "You" if is_me else sender
        align = "left" if is_me else "right"
        bg_color, text_color, border_style = "transparent", "#cdd6f4", ""

        media_preview_html = ""

        if "📎" in message:
            bg_color = "#1a2535"
            text_color = "#a6e3a1"
            border_style = "border-left: 3px solid #a6e3a1;"

            try:
                if "Sent a file: " in message:
                    filename = message.split("Sent a file: ")[1].strip()
                    if filename.endswith("]"):
                        filename = filename.rsplit("]", 1)[0].strip()
                    filename = os.path.basename(filename)
                    file_path = os.path.join("downloads", filename)

                    if os.path.exists(file_path):
                        ext = os.path.splitext(file_path)[1].lower()
                        abs_path = os.path.abspath(file_path).replace("\\", "/")

                        if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']:
                            media_preview_html = f"<br><br><img src='file:///{abs_path}' width='240' style='border-radius: 8px;' />"
                        elif ext in ['.mp3', '.wav', '.m4a', '.ogg']:
                            media_preview_html = f"<br><br>🎵 <a href='file:///{abs_path}' style='color: #89b4fa; font-weight: bold; text-decoration: none;'>▶ Play Track: {filename}</a>"
            except Exception as e:
                print(f"[PREVIEW ERROR] Asset tracing lookup failed: {e}")

        status_span = f"&nbsp;<span style='color: #a6e3a1; font-weight: bold;'>{initial_status}</span>" if (
                    is_me and initial_status) else ""

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
            f"            <span style='color: {text_color}; font-size: 14px;'>{message}</span>{media_preview_html}{status_span}"
            f"          </td>"
            f"        </tr>"
            f"      </table>"
            f"    </td>"
            f"  </tr>"
            f"</table>"
        )

        cursor = self.chat_box.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertHtml(formatted_table)
        cursor.insertBlock()
        self.chat_box.verticalScrollBar().setValue(self.chat_box.verticalScrollBar().maximum())
