"""
Graphical interface for my-hards using PySide6.

Buttons:
- Start Server
- Start Client (enter IP)
- Generate Config
- Stop

The server/client are launched as subprocesses so the GUI stays responsive.
"""

import sys
import os
import subprocess
import signal
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QMessageBox, QTextEdit
)
from PySide6.QtCore import Qt

ROOT = Path(__file__).parent


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("my-hards — Share keyboard & mouse")
        self.setMinimumSize(560, 360)

        self.server_proc = None
        self.client_proc = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        title = QLabel("my-hards")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px; font-weight:600;")
        layout.addWidget(title)

        # Controls
        controls = QHBoxLayout()

        self.start_server_btn = QPushButton("Start Server")
        self.start_server_btn.clicked.connect(self.start_server)
        controls.addWidget(self.start_server_btn)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Server IP (for Client)")
        controls.addWidget(self.ip_input)

        self.start_client_btn = QPushButton("Start Client")
        self.start_client_btn.clicked.connect(self.start_client)
        controls.addWidget(self.start_client_btn)

        layout.addLayout(controls)

        # Second row
        row2 = QHBoxLayout()
        self.gen_cfg_btn = QPushButton("Generate config.json")
        self.gen_cfg_btn.clicked.connect(self.generate_config)
        row2.addWidget(self.gen_cfg_btn)

        self.stop_btn = QPushButton("Stop All")
        self.stop_btn.clicked.connect(self.stop_all)
        row2.addWidget(self.stop_btn)

        layout.addLayout(row2)

        # Log
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.setLayout(layout)

    def append_log(self, text: str):
        self.log.append(text)

    def start_server(self):
        if self.server_proc and self.server_proc.poll() is None:
            QMessageBox.information(self, "Server", "Server already running")
            return
        cmd = [sys.executable, str(ROOT / "server.py")]
        self.append_log("Starting server: %s" % " ".join(cmd))
        self.server_proc = subprocess.Popen(cmd, cwd=str(ROOT))

    def start_client(self):
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Client", "Enter server IP first")
            return
        if self.client_proc and self.client_proc.poll() is None:
            QMessageBox.information(self, "Client", "Client already running")
            return
        cmd = [sys.executable, str(ROOT / "client.py"), ip]
        self.append_log("Starting client: %s" % " ".join(cmd))
        self.client_proc = subprocess.Popen(cmd, cwd=str(ROOT))

    def generate_config(self):
        try:
            from config import save_config, DEFAULT_CONFIG
            save_config(DEFAULT_CONFIG)
            QMessageBox.information(self, "Config", "config.json generated")
            self.append_log("config.json created")
        except Exception as e:
            QMessageBox.critical(self, "Config", f"Failed: {e}")
            self.append_log(f"Config generation failed: {e}")

    def stop_all(self):
        self.append_log("Stopping processes...")
        for p, name in ((self.client_proc, "client"), (self.server_proc, "server")):
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self.append_log("Stop signal sent")

    def closeEvent(self, event):
        self.stop_all()
        event.accept()


def main():
    app = QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
