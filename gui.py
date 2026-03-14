"""
my-hards — Desktop GUI for sharing keyboard & mouse between PCs.
Modern dark-themed interface with PySide6.
"""

import sys
import os
import subprocess
import socket
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QTextEdit, QComboBox,
    QSpinBox, QCheckBox, QGroupBox, QFrame, QTabWidget,
    QGridLayout, QSizePolicy, QStatusBar,
)
from PySide6.QtCore import Qt, QTimer, QProcess
from PySide6.QtGui import QFont, QIcon, QColor

ROOT = Path(__file__).parent

# ── Stylesheet ──────────────────────────────────────────────────────

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif;
    font-size: 13px;
}
QGroupBox {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 10px;
    margin-top: 14px;
    padding: 18px 14px 14px 14px;
    font-weight: 600;
    font-size: 14px;
    color: #e94560;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #e94560;
}
QPushButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-radius: 8px;
    padding: 10px 22px;
    font-weight: 600;
    font-size: 13px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #e94560;
    color: #ffffff;
}
QPushButton:pressed {
    background-color: #c81e45;
}
QPushButton:disabled {
    background-color: #2a2a4a;
    color: #555;
}
QPushButton#stopBtn {
    background-color: #533;
}
QPushButton#stopBtn:hover {
    background-color: #e94560;
}
QLineEdit, QSpinBox {
    background-color: #0f3460;
    border: 1px solid #1a4080;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    font-size: 13px;
    min-height: 18px;
}
QLineEdit:focus, QSpinBox:focus {
    border: 1px solid #e94560;
}
QComboBox {
    background-color: #0f3460;
    border: 1px solid #1a4080;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    min-height: 18px;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #16213e;
    color: #e0e0e0;
    selection-background-color: #e94560;
    border: 1px solid #0f3460;
}
QCheckBox {
    spacing: 8px;
    color: #e0e0e0;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #0f3460;
    background: #0f3460;
}
QCheckBox::indicator:checked {
    background: #e94560;
    border: 1px solid #e94560;
}
QTextEdit {
    background-color: #0d1b2a;
    border: 1px solid #1a4080;
    border-radius: 8px;
    padding: 10px;
    color: #a0d0a0;
    font-family: 'Cascadia Code', 'Consolas', 'Fira Code', monospace;
    font-size: 12px;
}
QTabWidget::pane {
    border: none;
    background: #1a1a2e;
}
QTabBar::tab {
    background: #16213e;
    border: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 10px 28px;
    margin-right: 2px;
    color: #999;
    font-weight: 600;
}
QTabBar::tab:selected {
    background: #0f3460;
    color: #e94560;
}
QTabBar::tab:hover {
    color: #e0e0e0;
}
QStatusBar {
    background: #0d1b2a;
    color: #777;
    font-size: 11px;
    border-top: 1px solid #1a4080;
}
QLabel#titleLabel {
    font-size: 28px;
    font-weight: 700;
    color: #e94560;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #777;
    margin-bottom: 6px;
}
QLabel#statusDot {
    font-size: 18px;
}
QFrame#separator {
    background-color: #0f3460;
    max-height: 1px;
}
"""


def get_local_ip() -> str:
    """Get the machine's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("my-hards")
        self.setMinimumSize(680, 520)
        self.resize(720, 560)

        self.server_proc: QProcess | None = None
        self.client_proc: QProcess | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(24, 18, 24, 12)
        root_layout.setSpacing(8)

        # ── Header ──
        header = QVBoxLayout()
        header.setSpacing(2)

        title = QLabel("my-hards")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        header.addWidget(title)

        subtitle = QLabel("Share keyboard & mouse between PCs")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        header.addWidget(subtitle)

        root_layout.addLayout(header)

        # separator
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        root_layout.addWidget(sep)

        # ── Tabs ──
        tabs = QTabWidget()
        tabs.addTab(self._build_connection_tab(), "Connection")
        tabs.addTab(self._build_settings_tab(), "Settings")
        root_layout.addWidget(tabs)

        # ── Log ──
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        log_layout.addWidget(self.log)
        root_layout.addWidget(log_group)

        # ── Status bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.local_ip = get_local_ip()
        self.status_bar.showMessage(f"Local IP: {self.local_ip}  |  Ready")

        # Timer to poll subprocess status
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_processes)
        self._poll_timer.start(1500)

        self._load_config_to_ui()

    # ── Connection Tab ──────────────────────────────────────────────

    def _build_connection_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Server card
        server_group = QGroupBox("Server Mode  (this PC shares keyboard & mouse)")
        sg = QHBoxLayout(server_group)

        self.server_status = QLabel("\u2b24")  # filled circle
        self.server_status.setObjectName("statusDot")
        self.server_status.setStyleSheet("color: #555;")
        self.server_status.setFixedWidth(28)
        sg.addWidget(self.server_status)

        self.server_status_label = QLabel("Stopped")
        self.server_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sg.addWidget(self.server_status_label)

        self.start_server_btn = QPushButton("\u25b6  Start Server")
        self.start_server_btn.clicked.connect(self.start_server)
        sg.addWidget(self.start_server_btn)

        self.stop_server_btn = QPushButton("\u25a0  Stop")
        self.stop_server_btn.setObjectName("stopBtn")
        self.stop_server_btn.setEnabled(False)
        self.stop_server_btn.clicked.connect(self.stop_server)
        sg.addWidget(self.stop_server_btn)

        layout.addWidget(server_group)

        # Client card
        client_group = QGroupBox("Client Mode  (this PC receives input)")
        cg = QGridLayout(client_group)

        self.client_status = QLabel("\u2b24")
        self.client_status.setObjectName("statusDot")
        self.client_status.setStyleSheet("color: #555;")
        self.client_status.setFixedWidth(28)
        cg.addWidget(self.client_status, 0, 0)

        self.client_status_label = QLabel("Disconnected")
        cg.addWidget(self.client_status_label, 0, 1)

        ip_label = QLabel("Server IP:")
        cg.addWidget(ip_label, 1, 0, 1, 1, Qt.AlignRight)

        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("e.g. 192.168.1.100")
        self.ip_input.returnPressed.connect(self.start_client)
        cg.addWidget(self.ip_input, 1, 1)

        self.start_client_btn = QPushButton("\u25b6  Connect")
        self.start_client_btn.clicked.connect(self.start_client)
        cg.addWidget(self.start_client_btn, 1, 2)

        self.stop_client_btn = QPushButton("\u25a0  Stop")
        self.stop_client_btn.setObjectName("stopBtn")
        self.stop_client_btn.setEnabled(False)
        self.stop_client_btn.clicked.connect(self.stop_client)
        cg.addWidget(self.stop_client_btn, 1, 3)

        layout.addWidget(client_group)
        layout.addStretch()
        return tab

    # ── Settings Tab ────────────────────────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        settings_group = QGroupBox("Configuration")
        grid = QGridLayout(settings_group)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        row = 0
        grid.addWidget(QLabel("Port:"), row, 0, Qt.AlignRight)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(24800)
        grid.addWidget(self.port_spin, row, 1)

        row += 1
        grid.addWidget(QLabel("Switch edge:"), row, 0, Qt.AlignRight)
        self.edge_combo = QComboBox()
        self.edge_combo.addItems(["right", "left", "top", "bottom"])
        grid.addWidget(self.edge_combo, row, 1)

        row += 1
        grid.addWidget(QLabel("Switch margin (px):"), row, 0, Qt.AlignRight)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(1, 50)
        self.margin_spin.setValue(2)
        grid.addWidget(self.margin_spin, row, 1)

        row += 1
        self.clipboard_check = QCheckBox("Sync clipboard between PCs")
        self.clipboard_check.setChecked(True)
        grid.addWidget(self.clipboard_check, row, 0, 1, 2)

        row += 1
        grid.addWidget(QLabel("Heartbeat interval (sec):"), row, 0, Qt.AlignRight)
        self.heartbeat_spin = QSpinBox()
        self.heartbeat_spin.setRange(1, 60)
        self.heartbeat_spin.setValue(5)
        grid.addWidget(self.heartbeat_spin, row, 1)

        layout.addWidget(settings_group)

        # Save / Reset row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        save_btn = QPushButton("Save config.json")
        save_btn.clicked.connect(self.save_config)
        btn_row.addWidget(save_btn)

        reset_btn = QPushButton("Reset defaults")
        reset_btn.clicked.connect(self.reset_config)
        btn_row.addWidget(reset_btn)

        layout.addLayout(btn_row)
        layout.addStretch()
        return tab

    # ── Config helpers ──────────────────────────────────────────────

    def _load_config_to_ui(self):
        from config import load_config
        cfg = load_config()
        self.port_spin.setValue(cfg.get("port", 24800))
        edge = cfg.get("switch_edge", "right")
        idx = self.edge_combo.findText(edge)
        if idx >= 0:
            self.edge_combo.setCurrentIndex(idx)
        self.margin_spin.setValue(cfg.get("switch_margin", 2))
        self.clipboard_check.setChecked(cfg.get("clipboard_sync", True))
        self.heartbeat_spin.setValue(cfg.get("heartbeat_interval", 5))

    def _ui_to_config(self) -> dict:
        return {
            "port": self.port_spin.value(),
            "switch_edge": self.edge_combo.currentText(),
            "switch_margin": self.margin_spin.value(),
            "client_screen_width": 1920,
            "client_screen_height": 1080,
            "clipboard_sync": self.clipboard_check.isChecked(),
            "heartbeat_interval": self.heartbeat_spin.value(),
        }

    def save_config(self):
        from config import save_config
        save_config(self._ui_to_config())
        self._log("Config saved to config.json")

    def reset_config(self):
        from config import DEFAULT_CONFIG, save_config
        save_config(DEFAULT_CONFIG)
        self._load_config_to_ui()
        self._log("Config reset to defaults")

    # ── Process management ──────────────────────────────────────────

    def start_server(self):
        if self.server_proc and self.server_proc.state() != QProcess.NotRunning:
            return
        self.save_config()  # persist current settings before starting
        self.server_proc = QProcess(self)
        self.server_proc.setWorkingDirectory(str(ROOT))
        self.server_proc.readyReadStandardOutput.connect(
            lambda: self._read_output(self.server_proc, "SERVER")
        )
        self.server_proc.readyReadStandardError.connect(
            lambda: self._read_stderr(self.server_proc, "SERVER")
        )
        self.server_proc.finished.connect(self._on_server_finished)
        self.server_proc.start(sys.executable, [str(ROOT / "server.py")])
        self._set_server_state(True)
        self._log("Server starting...")

    def stop_server(self):
        if self.server_proc and self.server_proc.state() != QProcess.NotRunning:
            self.server_proc.terminate()
            self._log("Server stopping...")

    def start_client(self):
        ip = self.ip_input.text().strip()
        if not ip:
            self._log("ERROR: Enter the server IP address first")
            self.ip_input.setFocus()
            return
        if self.client_proc and self.client_proc.state() != QProcess.NotRunning:
            return
        self.save_config()
        self.client_proc = QProcess(self)
        self.client_proc.setWorkingDirectory(str(ROOT))
        self.client_proc.readyReadStandardOutput.connect(
            lambda: self._read_output(self.client_proc, "CLIENT")
        )
        self.client_proc.readyReadStandardError.connect(
            lambda: self._read_stderr(self.client_proc, "CLIENT")
        )
        self.client_proc.finished.connect(self._on_client_finished)
        self.client_proc.start(sys.executable, [str(ROOT / "client.py"), ip])
        self._set_client_state(True)
        self._log(f"Client connecting to {ip}...")

    def stop_client(self):
        if self.client_proc and self.client_proc.state() != QProcess.NotRunning:
            self.client_proc.terminate()
            self._log("Client stopping...")

    # ── QProcess callbacks ──────────────────────────────────────────

    def _read_output(self, proc: QProcess, prefix: str):
        data = proc.readAllStandardOutput().data().decode(errors="replace").strip()
        if data:
            for line in data.splitlines():
                self._log(f"[{prefix}] {line}")

    def _read_stderr(self, proc: QProcess, prefix: str):
        data = proc.readAllStandardError().data().decode(errors="replace").strip()
        if data:
            for line in data.splitlines():
                self._log(f"[{prefix}] {line}")

    def _on_server_finished(self):
        self._set_server_state(False)
        self._log("Server stopped")

    def _on_client_finished(self):
        self._set_client_state(False)
        self._log("Client disconnected")

    # ── UI state helpers ────────────────────────────────────────────

    def _set_server_state(self, running: bool):
        self.start_server_btn.setEnabled(not running)
        self.stop_server_btn.setEnabled(running)
        color = "#4ade80" if running else "#555"
        text = "Running — waiting for client..." if running else "Stopped"
        self.server_status.setStyleSheet(f"color: {color};")
        self.server_status_label.setText(text)
        self._update_status_bar()

    def _set_client_state(self, running: bool):
        self.start_client_btn.setEnabled(not running)
        self.stop_client_btn.setEnabled(running)
        self.ip_input.setEnabled(not running)
        color = "#4ade80" if running else "#555"
        text = "Connected" if running else "Disconnected"
        self.client_status.setStyleSheet(f"color: {color};")
        self.client_status_label.setText(text)
        self._update_status_bar()

    def _update_status_bar(self):
        parts = [f"Local IP: {self.local_ip}"]
        srv = self.server_proc and self.server_proc.state() != QProcess.NotRunning
        cli = self.client_proc and self.client_proc.state() != QProcess.NotRunning
        if srv:
            parts.append("Server: ON")
        if cli:
            parts.append("Client: ON")
        if not srv and not cli:
            parts.append("Ready")
        self.status_bar.showMessage("  |  ".join(parts))

    def _poll_processes(self):
        """Periodically refresh button states in case a process died."""
        if self.server_proc and self.server_proc.state() == QProcess.NotRunning:
            if not self.start_server_btn.isEnabled():
                self._set_server_state(False)
        if self.client_proc and self.client_proc.state() == QProcess.NotRunning:
            if not self.start_client_btn.isEnabled():
                self._set_client_state(False)

    def _log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.append(f"<span style='color:#555'>[{ts}]</span> {text}")

    # ── Window close ────────────────────────────────────────────────

    def closeEvent(self, event):
        for proc in (self.client_proc, self.server_proc):
            if proc and proc.state() != QProcess.NotRunning:
                proc.terminate()
                proc.waitForFinished(2000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
