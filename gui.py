"""
my-hards — Desktop GUI for sharing keyboard & mouse between PCs.
Dark-themed interface using tkinter (built into Python, no extra deps).
"""

import sys
import os
import subprocess
import socket
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent

# ── Dark colour palette ─────────────────────────────────────────────

BG_MAIN   = "#1a1a2e"
BG_CARD   = "#16213e"
BG_INPUT  = "#0f3460"
BG_LOG    = "#0d1b2a"
FG        = "#e0e0e0"
FG_DIM    = "#777777"
ACCENT    = "#e94560"
GREEN     = "#4ade80"
RED_DIM   = "#553333"
BORDER    = "#1a4080"


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class _Proc:
    """Thin wrapper around subprocess.Popen with non-blocking output reading."""

    def __init__(self, args: list[str], cwd: str, on_line, on_finish):
        self._on_line = on_line
        self._on_finish = on_finish
        self.proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        try:
            for line in self.proc.stdout:
                self._on_line(line.rstrip("\n"))
        except Exception:
            pass
        self.proc.wait()
        self._on_finish()

    def is_running(self) -> bool:
        return self.proc.poll() is None

    def terminate(self):
        if self.is_running():
            self.proc.terminate()

    def kill(self):
        if self.is_running():
            self.proc.kill()


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("my-hards")
        self.root.geometry("720x580")
        self.root.minsize(680, 520)
        self.root.configure(bg=BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.server_proc: _Proc | None = None
        self.client_proc: _Proc | None = None
        self.local_ip = get_local_ip()

        # Tkinter variables
        self.port_var = tk.IntVar(value=24800)
        self.edge_var = tk.StringVar(value="right")
        self.margin_var = tk.IntVar(value=2)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.clipboard_var = tk.BooleanVar(value=True)
        self.heartbeat_var = tk.IntVar(value=5)
        self.hotkey_var = tk.StringVar(value="<ctrl>+<alt>+s")
        self.ip_var = tk.StringVar()

        self._configure_styles()
        self._build_ui()
        self._load_config_to_ui()
        self._poll_processes()

    # ── Styles ──────────────────────────────────────────────────────

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=BG_MAIN, foreground=FG,
                         font=("Segoe UI", 10))
        style.configure("TFrame", background=BG_MAIN)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_MAIN, foreground=FG,
                         font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=BG_CARD, foreground=FG)
        style.configure("Title.TLabel", background=BG_MAIN, foreground=ACCENT,
                         font=("Segoe UI", 22, "bold"))
        style.configure("Sub.TLabel", background=BG_MAIN, foreground=FG_DIM,
                         font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=BG_CARD, foreground=ACCENT,
                         font=("Segoe UI", 10, "bold"))
        style.configure("Dot.TLabel", background=BG_CARD, font=("Segoe UI", 14))
        style.configure("Status.TLabel", background=BG_LOG, foreground=FG_DIM,
                         font=("Segoe UI", 9))

        # Buttons
        style.configure("Accent.TButton", background=BG_INPUT, foreground=FG,
                         font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.map("Accent.TButton",
                   background=[("active", ACCENT), ("disabled", "#2a2a4a")],
                   foreground=[("active", "#fff"), ("disabled", "#555")])

        style.configure("Stop.TButton", background=RED_DIM, foreground=FG,
                         font=("Segoe UI", 10, "bold"), padding=(14, 6))
        style.map("Stop.TButton",
                   background=[("active", ACCENT), ("disabled", "#2a2a4a")],
                   foreground=[("active", "#fff"), ("disabled", "#555")])

        # Notebook tabs
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG_DIM,
                         font=("Segoe UI", 10, "bold"), padding=(22, 8))
        style.map("TNotebook.Tab",
                   background=[("selected", BG_INPUT)],
                   foreground=[("selected", ACCENT)])

        # Checkbutton
        style.configure("TCheckbutton", background=BG_CARD, foreground=FG,
                         font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", BG_CARD)])

        # Combobox
        style.configure("TCombobox", fieldbackground=BG_INPUT,
                         background=BG_INPUT, foreground=FG,
                         selectbackground=ACCENT, selectforeground="#fff")
        style.map("TCombobox",
                   fieldbackground=[("readonly", BG_INPUT)],
                   foreground=[("readonly", FG)])

        # Spinbox
        style.configure("TSpinbox", fieldbackground=BG_INPUT,
                         background=BG_INPUT, foreground=FG)

        # Entry
        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG,
                         insertcolor=FG)

        # LabelFrame
        style.configure("Card.TLabelframe", background=BG_CARD,
                         bordercolor=BG_INPUT, borderwidth=1)
        style.configure("Card.TLabelframe.Label", background=BG_CARD,
                         foreground=ACCENT, font=("Segoe UI", 10, "bold"))

    # ── Build UI ────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 16, "pady": 4}

        # Header
        ttk.Label(self.root, text="my-hards", style="Title.TLabel")\
            .pack(pady=(14, 0))
        ttk.Label(self.root, text="Share keyboard & mouse between PCs",
                  style="Sub.TLabel").pack()

        ttk.Separator(self.root).pack(fill="x", padx=20, pady=6)

        # Notebook
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 4))

        nb.add(self._build_connection_tab(nb), text="  Connection  ")
        nb.add(self._build_settings_tab(nb), text="  Settings  ")

        # Log
        log_frame = ttk.LabelFrame(self.root, text="Log",
                                    style="Card.TLabelframe")
        log_frame.pack(fill="both", padx=16, pady=(0, 4))

        self.log_text = tk.Text(log_frame, height=7, bg=BG_LOG, fg="#a0d0a0",
                                 insertbackground=FG, font=("Consolas", 9),
                                 borderwidth=0, highlightthickness=0,
                                 state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=6, pady=6)

        # Status bar
        self.status_label = ttk.Label(self.root, style="Status.TLabel",
                                       anchor="w")
        self.status_label.pack(fill="x", side="bottom", ipady=3, padx=1)
        self._update_status_bar()

    def _build_connection_tab(self, parent) -> ttk.Frame:
        tab = ttk.Frame(parent)

        # ── Server card ──
        srv = ttk.LabelFrame(tab,
                              text="  Server Mode  (this PC shares keyboard & mouse)  ",
                              style="Card.TLabelframe")
        srv.pack(fill="x", padx=8, pady=(10, 4))
        srv_inner = ttk.Frame(srv, style="Card.TFrame")
        srv_inner.pack(fill="x", padx=8, pady=8)

        self.server_dot = ttk.Label(srv_inner, text="\u2b24",
                                     style="Dot.TLabel", foreground="#555")
        self.server_dot.pack(side="left")

        self.server_status_lbl = ttk.Label(srv_inner, text="Stopped",
                                            style="Card.TLabel")
        self.server_status_lbl.pack(side="left", padx=(6, 0), fill="x", expand=True)

        self.stop_server_btn = ttk.Button(srv_inner, text="\u25a0  Stop",
                                           style="Stop.TButton",
                                           command=self.stop_server,
                                           state="disabled")
        self.stop_server_btn.pack(side="right", padx=(4, 0))

        self.start_server_btn = ttk.Button(srv_inner, text="\u25b6  Start Server",
                                            style="Accent.TButton",
                                            command=self.start_server)
        self.start_server_btn.pack(side="right")

        # ── Client card ──
        cli = ttk.LabelFrame(tab,
                              text="  Client Mode  (this PC receives input)  ",
                              style="Card.TLabelframe")
        cli.pack(fill="x", padx=8, pady=(4, 4))

        row0 = ttk.Frame(cli, style="Card.TFrame")
        row0.pack(fill="x", padx=8, pady=(8, 2))

        self.client_dot = ttk.Label(row0, text="\u2b24",
                                     style="Dot.TLabel", foreground="#555")
        self.client_dot.pack(side="left")

        self.client_status_lbl = ttk.Label(row0, text="Disconnected",
                                            style="Card.TLabel")
        self.client_status_lbl.pack(side="left", padx=(6, 0))

        row1 = ttk.Frame(cli, style="Card.TFrame")
        row1.pack(fill="x", padx=8, pady=(2, 8))

        ttk.Label(row1, text="Server IP:", style="Card.TLabel")\
            .pack(side="left")

        self.ip_entry = ttk.Entry(row1, textvariable=self.ip_var, width=18)
        self.ip_entry.pack(side="left", padx=(6, 6))
        self.ip_entry.bind("<Return>", lambda _: self.start_client())

        self.start_client_btn = ttk.Button(row1, text="\u25b6  Connect",
                                            style="Accent.TButton",
                                            command=self.start_client)
        self.start_client_btn.pack(side="left")

        self.stop_client_btn = ttk.Button(row1, text="\u25a0  Stop",
                                           style="Stop.TButton",
                                           command=self.stop_client,
                                           state="disabled")
        self.stop_client_btn.pack(side="left", padx=(4, 0))

        return tab

    def _build_settings_tab(self, parent) -> ttk.Frame:
        tab = ttk.Frame(parent)

        cfg = ttk.LabelFrame(tab, text="  Configuration  ",
                              style="Card.TLabelframe")
        cfg.pack(fill="x", padx=8, pady=(10, 4))

        grid = ttk.Frame(cfg, style="Card.TFrame")
        grid.pack(fill="x", padx=12, pady=10)

        rows = [
            ("Port:", self._make_spinbox(grid, self.port_var, 1024, 65535)),
            ("Switch edge:", self._make_combobox(grid, self.edge_var,
                                                  ["right", "left", "top", "bottom"])),
            ("Switch margin (px):", self._make_spinbox(grid, self.margin_var, 1, 50)),
            ("Client pointer speed:", self._make_spinbox_float(grid, self.speed_var,
                                                                0.10, 4.00, 0.10)),
            ("Heartbeat interval (sec):", self._make_spinbox(grid, self.heartbeat_var,
                                                              1, 60)),
            ("Switch hotkey:", self._make_entry(grid, self.hotkey_var)),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(grid, text=label, style="Card.TLabel")\
                .grid(row=i, column=0, sticky="e", padx=(0, 10), pady=4)
            widget.grid(row=i, column=1, sticky="w", pady=4)

        # Clipboard checkbox
        self.clip_check = ttk.Checkbutton(grid, text="Sync clipboard between PCs",
                                           variable=self.clipboard_var)
        self.clip_check.grid(row=len(rows), column=0, columnspan=2,
                              sticky="w", pady=4)

        # Hotkey hint
        hint = ttk.Label(grid, text="Hotkey format: <ctrl>, <alt>, <shift> + letter",
                          style="Card.TLabel", foreground=FG_DIM,
                          font=("Segoe UI", 8))
        hint.grid(row=len(rows) - 1, column=2, sticky="w", padx=(8, 0))

        # Buttons
        btn_row = ttk.Frame(tab)
        btn_row.pack(fill="x", padx=8, pady=(4, 8))

        ttk.Button(btn_row, text="Reset defaults", style="Accent.TButton",
                    command=self.reset_config).pack(side="right", padx=(4, 0))
        ttk.Button(btn_row, text="Save config.json", style="Accent.TButton",
                    command=self.save_config).pack(side="right")

        return tab

    # ── Widget factories ────────────────────────────────────────────

    def _make_spinbox(self, parent, var, lo, hi):
        sb = ttk.Spinbox(parent, from_=lo, to=hi, textvariable=var, width=10)
        return sb

    def _make_spinbox_float(self, parent, var, lo, hi, step):
        sb = ttk.Spinbox(parent, from_=lo, to=hi, increment=step,
                          textvariable=var, width=10, format="%.2f")
        return sb

    def _make_combobox(self, parent, var, values):
        cb = ttk.Combobox(parent, textvariable=var, values=values,
                           state="readonly", width=10)
        return cb

    def _make_entry(self, parent, var):
        return ttk.Entry(parent, textvariable=var, width=18)

    # ── Config helpers ──────────────────────────────────────────────

    def _load_config_to_ui(self):
        from config import load_config
        cfg = load_config()
        self.port_var.set(cfg.get("port", 24800))
        self.edge_var.set(cfg.get("switch_edge", "right"))
        self.margin_var.set(cfg.get("switch_margin", 2))
        self.speed_var.set(float(cfg.get("client_pointer_speed", 1.0)))
        self.clipboard_var.set(cfg.get("clipboard_sync", True))
        self.heartbeat_var.set(cfg.get("heartbeat_interval", 5))
        self.hotkey_var.set(cfg.get("switch_hotkey", "<ctrl>+<alt>+s"))
        last_ip = cfg.get("last_server_ip", "")
        if last_ip:
            self.ip_var.set(last_ip)

    def _ui_to_config(self) -> dict:
        return {
            "port": self.port_var.get(),
            "switch_edge": self.edge_var.get(),
            "switch_margin": self.margin_var.get(),
            "client_screen_width": 1920,
            "client_screen_height": 1080,
            "client_pointer_speed": self.speed_var.get(),
            "clipboard_sync": self.clipboard_var.get(),
            "heartbeat_interval": self.heartbeat_var.get(),
            "switch_hotkey": self.hotkey_var.get().strip() or "<ctrl>+<alt>+s",
            "last_server_ip": self.ip_var.get().strip(),
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
        if self.server_proc and self.server_proc.is_running():
            return
        self.save_config()
        self.server_proc = _Proc(
            [sys.executable, str(ROOT / "server.py")],
            cwd=str(ROOT),
            on_line=lambda line: self.root.after(0, self._log, f"[SERVER] {line}"),
            on_finish=lambda: self.root.after(0, self._on_server_finished),
        )
        self._set_server_state(True)
        self._log("Server starting...")

    def stop_server(self):
        if self.server_proc and self.server_proc.is_running():
            self._log("Server stopping...")
            self.stop_server_btn.configure(state="disabled")
            self.server_proc.terminate()
            self.root.after(1500, self._force_kill_server)

    def _force_kill_server(self):
        if self.server_proc and self.server_proc.is_running():
            self.server_proc.kill()

    def start_client(self):
        ip = self.ip_var.get().strip()
        if not ip:
            self._log("ERROR: Enter the server IP address first")
            self.ip_entry.focus_set()
            return
        if self.client_proc and self.client_proc.is_running():
            return
        self.save_config()
        self.client_proc = _Proc(
            [sys.executable, str(ROOT / "client.py"), ip],
            cwd=str(ROOT),
            on_line=lambda line: self.root.after(0, self._log, f"[CLIENT] {line}"),
            on_finish=lambda: self.root.after(0, self._on_client_finished),
        )
        self._set_client_state(True)
        self._log(f"Client connecting to {ip}...")

    def stop_client(self):
        if self.client_proc and self.client_proc.is_running():
            self._log("Client stopping...")
            self.stop_client_btn.configure(state="disabled")
            self.client_proc.terminate()
            self.root.after(1500, self._force_kill_client)

    def _force_kill_client(self):
        if self.client_proc and self.client_proc.is_running():
            self.client_proc.kill()

    # ── Process callbacks ───────────────────────────────────────────

    def _on_server_finished(self):
        self._set_server_state(False)
        self._log("Server stopped")

    def _on_client_finished(self):
        self._set_client_state(False)
        self._log("Client disconnected")

    # ── UI state helpers ────────────────────────────────────────────

    def _set_server_state(self, running: bool):
        self.start_server_btn.configure(
            state="disabled" if running else "normal")
        self.stop_server_btn.configure(
            state="normal" if running else "disabled")
        self.server_dot.configure(foreground=GREEN if running else "#555")
        self.server_status_lbl.configure(
            text="Running \u2014 waiting for client..." if running else "Stopped")
        self._update_status_bar()

    def _set_client_state(self, running: bool):
        self.start_client_btn.configure(
            state="disabled" if running else "normal")
        self.stop_client_btn.configure(
            state="normal" if running else "disabled")
        self.ip_entry.configure(state="disabled" if running else "normal")
        self.client_dot.configure(foreground=GREEN if running else "#555")
        self.client_status_lbl.configure(
            text="Connected" if running else "Disconnected")
        self._update_status_bar()

    def _update_status_bar(self):
        parts = [f"Local IP: {self.local_ip}"]
        srv = self.server_proc and self.server_proc.is_running()
        cli = self.client_proc and self.client_proc.is_running()
        if srv:
            parts.append("Server: ON")
        if cli:
            parts.append("Client: ON")
        if not srv and not cli:
            parts.append("Ready")
        self.status_label.configure(text="  |  ".join(parts))

    def _poll_processes(self):
        if self.server_proc and not self.server_proc.is_running():
            if str(self.start_server_btn.cget("state")) == "disabled":
                self._set_server_state(False)
        if self.client_proc and not self.client_proc.is_running():
            if str(self.start_client_btn.cget("state")) == "disabled":
                self._set_client_state(False)
        self.root.after(1500, self._poll_processes)

    def _log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {text}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ── Window close ────────────────────────────────────────────────

    def _on_close(self):
        self.save_config()
        for proc in (self.client_proc, self.server_proc):
            if proc and proc.is_running():
                proc.kill()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
