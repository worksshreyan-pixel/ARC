import sys
import json
import asyncio
import threading
import requests
import math
import websockets

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QLabel, QScrollArea, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QConicalGradient, QBrush, QRadialGradient

SERVER_HTTP = "http://127.0.0.1:8000/api/command"
SERVER_WS = "ws://127.0.0.1:8000/ws/feed"

class Bridge(QObject):
    status_signal = pyqtSignal(str, str)
    log_signal = pyqtSignal(str, str)

class OrbWidget(QWidget):
    """Translates the Siri Orb CSS spec into a 3D-simulated QPainter animation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.state = "idle"
        self.angle = 0.0
        self.pulse_phase = 0.0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(16) 
        
    def set_state(self, new_state):
        self.state = new_state.lower()
        
    def animate(self):
        if self.state == "thinking":
            self.angle = (self.angle + 4.5) % 360
            self.pulse_phase = 0
        elif self.state in ["speaking", "streaming"]:
            self.angle = (self.angle + 2.0) % 360
            self.pulse_phase += 0.12
        elif self.state == "error":
            self.angle = (self.angle + 0.5) % 360
        else: 
            self.angle = (self.angle + 1.2) % 360
            self.pulse_phase = 0
        self.update()

    def get_palette(self):
        if self.state == "listening":
            return [(0.0, "#00e5ff"), (0.33, "#ec4899"), (0.66, "#3b82f6"), (1.0, "#00e5ff")]
        elif self.state == "thinking":
            return [(0.0, "#bfdbfe"), (0.33, "#fbcfe8"), (0.66, "#e0e7ff"), (1.0, "#bfdbfe")]
        elif self.state in ["speaking", "streaming"]:
            return [(0.0, "#06b6d4"), (0.33, "#f472b6"), (0.66, "#a855f7"), (1.0, "#06b6d4")]
        elif self.state == "error":
            return [(0.0, "#94a3b8"), (0.33, "#a8a29e"), (0.66, "#64748b"), (1.0, "#94a3b8")]
        else: 
            return [(0.0, "#e83e8c"), (0.33, "#3b82f6"), (0.66, "#c084fc"), (1.0, "#e83e8c")]
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = QRectF(2, 2, self.width()-4, self.height()-4)
        
        scale = 1.0
        if self.state in ["speaking", "streaming"]:
            scale = 1.0 + 0.08 * math.sin(self.pulse_phase)
            
        center = rect.center()
        painter.translate(center)
        painter.scale(scale, scale)
        painter.translate(-center)
        
        conical = QConicalGradient(center, self.angle)
        for pos, hex_color in self.get_palette():
            conical.setColorAt(pos, QColor(hex_color))
            
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(conical))
        painter.drawEllipse(rect)

        radial = QRadialGradient(center, rect.width() / 2)
        radial.setColorAt(0.0, QColor(255, 255, 255, 140)) 
        radial.setColorAt(0.5, QColor(255, 255, 255, 40))
        radial.setColorAt(1.0, QColor(255, 255, 255, 0))
        
        painter.setBrush(QBrush(radial))
        painter.drawEllipse(rect)


class ArcWidget(QWidget):
    def __init__(self, bridge):
        super().__init__()
        self.bridge = bridge
        self.bridge.status_signal.connect(self.update_status)
        self.bridge.log_signal.connect(self.add_message)
        
        self.init_ui()
        self.old_pos = None

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.SubWindow)
        self.resize(480, 360) # Made slightly taller for chat bubbles

        self.setStyleSheet("""
            QWidget#MainWindow {
                background-color: #121622;
                border: 2px solid #005577;
                border-radius: 12px;
            }
        """)
        self.setObjectName("MainWindow")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 12, 18, 12)
        main_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel("PROJECT ARC // AVA")
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title.setStyleSheet("color: #798da8; letter-spacing: 1.5px; border: none; background: transparent;")

        self.orb = OrbWidget()
        self.status_label = QLabel("IDLE")
        self.status_label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #00e5ff; letter-spacing: 1px; border: none; background: transparent;")
        
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.orb)
        header.addWidget(self.status_label)
        main_layout.addLayout(header)

        # AI Conversation Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 8px; background: transparent; }
            QScrollBar::handle:vertical { background: #3b4252; border-radius: 4px; }
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll_layout.setSpacing(14) # Space between messages
        
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)

        # Jump to latest Pill
        self.jump_button = QPushButton("↓ Jump to latest")
        self.jump_button.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self.jump_button.setStyleSheet("""
            QPushButton {
                background-color: #005577; color: white;
                border-radius: 12px; padding: 4px 12px;
            }
            QPushButton:hover { background-color: #007799; }
        """)
        self.jump_button.setParent(self)
        self.jump_button.hide()
        self.jump_button.clicked.connect(self.scroll_to_bottom)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self.check_scroll_position)

        # Input Bar
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask Ava or give an instruction...")
        self.input_field.setFont(QFont("Segoe UI", 10))
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: #1e2438; border: 1px solid #3b4252;
                border-radius: 8px; color: #ffffff; padding: 8px 12px;
            }
            QLineEdit:focus { border: 1px solid #00e5ff; }
        """)
        self.input_field.returnPressed.connect(self.send_command)
        main_layout.addWidget(self.input_field)
        
        self.add_message("System online. Awaiting commands...", "system")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.jump_button.move(
            int((self.width() - self.jump_button.width()) / 2),
            self.height() - 75 
        )

    def check_scroll_position(self):
        bar = self.scroll_area.verticalScrollBar()
        if bar.value() >= bar.maximum() - 48:
            self.jump_button.hide()

    def scroll_to_bottom(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.maximum())
        self.jump_button.hide()

    def add_message(self, text, role="ava"):
        bar = self.scroll_area.verticalScrollBar()
        was_at_bottom = bar.value() >= bar.maximum() - 48

        # Container for the entire message row
        msg_container = QWidget()
        msg_layout = QHBoxLayout(msg_container)
        msg_layout.setContentsMargins(0, 0, 0, 0)

        msg_label = QLabel(text)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 9))
        msg_label.setMaximumWidth(340) # Restrict width to create bubble shape
        
        if role == "user":
            msg_label.setStyleSheet("""
                background-color: #000000; 
                color: #ffffff; 
                border-radius: 14px; 
                padding: 10px 14px;
            """)
            msg_layout.addStretch() # Pushes bubble to the right
            msg_layout.addWidget(msg_label)

        elif role == "system":
            msg_label.setStyleSheet("color: #6b7280; font-style: italic;")
            msg_label.setMaximumWidth(400)
            msg_layout.addWidget(msg_label)
            msg_layout.addStretch()

        else: # Ava
            msg_label.setStyleSheet("""
                background-color: #1c2130; 
                color: #d1d5db; 
                border-radius: 14px; 
                padding: 12px 16px;
                border: 1px solid #2a3143;
            """)
            
            # Mini Avatar next to AI messages
            avatar = QWidget()
            avatar.setFixedSize(20, 20)
            avatar.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #06b6d4, stop:0.5 #a855f7, stop:1 #ec4899);
                border-radius: 10px;
            """)
            v_avatar_layout = QVBoxLayout()
            v_avatar_layout.addWidget(avatar)
            v_avatar_layout.addStretch() # Pins avatar to the top left of the message
            v_avatar_layout.setContentsMargins(0, 4, 4, 0)
            
            msg_layout.addLayout(v_avatar_layout)
            msg_layout.addWidget(msg_label)
            msg_layout.addStretch() # Pushes bubble to the left

        self.scroll_layout.addWidget(msg_container)
        QApplication.processEvents()

        if was_at_bottom:
            bar.setValue(bar.maximum())
        else:
            self.jump_button.show()
            self.jump_button.raise_()

    def update_status(self, text, color):
        self.orb.set_state(text)
        self.status_label.setText(text.upper())
        self.status_label.setStyleSheet(f"color: {color}; letter-spacing: 1px; border: none; background: transparent;")

    def send_command(self):
        query = self.input_field.text().strip()
        if not query:
            return
        
        self.input_field.clear()
        self.update_status("THINKING", "#f59e0b")
        # Stripped "You: " prefix since we now have visual chat bubbles
        self.add_message(query, "user")

        def worker():
            try:
                response = requests.post(SERVER_HTTP, json={"prompt": query}, timeout=60)
                if response.status_code == 200:
                    reply_text = response.json().get("reply", "Action completed.")
                    # Stripped "Ava: " prefix
                    self.bridge.log_signal.emit(reply_text, "ava")
                else:
                    self.bridge.log_signal.emit(f"Server Error: {response.status_code}", "system")
                self.bridge.status_signal.emit("IDLE", "#00e5ff")
            except Exception as e:
                self.bridge.log_signal.emit(f"Error: {e}", "system")
                self.bridge.status_signal.emit("ERROR", "#ef4444")

        threading.Thread(target=worker, daemon=True).start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None

async def ws_listener(bridge):
    while True:
        try:
            async with websockets.connect(SERVER_WS) as ws:
                bridge.status_signal.emit("ONLINE", "#00e5ff")
                while True:
                    raw = await ws.recv()
                    payload = json.loads(raw)
                    event_type = payload.get("event")
                    if event_type == "speak":
                        bridge.status_signal.emit("SPEAKING", "#10b981")
                    elif event_type == "idle":
                        bridge.status_signal.emit("IDLE", "#00e5ff")
        except Exception:
            bridge.status_signal.emit("OFFLINE", "#6b7280")
            await asyncio.sleep(3)

def start_async_loop(bridge):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ws_listener(bridge))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    bridge = Bridge()
    widget = ArcWidget(bridge)
    widget.show()
    t = threading.Thread(target=start_async_loop, args=(bridge,), daemon=True)
    t.start()
    sys.exit(app.exec())