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
import ttkbootstrap as tb
from datetime import datetime
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

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
        # Use ttkbootstrap Window for a modern theme (dark by default)
        try:
            self.root = tb.Window(themename="darkly")
        except Exception:
            self.root = tk.Tk()
        self.root.title("my-hards")
        self.root.geometry("800x700")
        self.root.minsize(720, 600)
        self.root.configure(bg=BG_MAIN)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_minimize)

        self.tray_icon: pystray.Icon | None = None

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
        self.secret_var = tk.StringVar()
        self.ip_var = tk.StringVar()

        self._configure_styles()
        self._build_ui()
        self._load_config_to_ui()
        self._poll_processes()

    # ── Styles ──────────────────────────────────────────────────────

    def _configure_styles(self):
        # Prefer ttkbootstrap Style for nicer defaults; fallback to ttk.Style
        try:
            style = tb.Style()
        except Exception:
            style = ttk.Style(self.root)
            style.theme_use("clam")

        # Base ttk (used only for Notebook)
        style.configure(".", background=BG_MAIN, foreground=FG,
                         font=("Segoe UI", 11))
        style.configure("TFrame", background=BG_MAIN)
        style.configure("TLabel", background=BG_MAIN, foreground=FG)

        # Notebook tabs — smaller padding and fixed minimum width so tabs match
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=BG_CARD,
            foreground=FG_DIM,
            font=("Segoe UI", 11, "bold"),
            padding=(16, 8),
            minwidth=160,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", BG_INPUT)],
            foreground=[("selected", ACCENT)],
        )

    # ── Native-tk widget helpers (full dark-colour control) ─────────

    def _btn(self, parent, text, command, bg=None, state="normal"):
        """Create a fully-styled tk.Button."""
        b = tk.Button(
            parent, text=text, command=command,
            bg=bg or BG_INPUT, fg=FG,
            activebackground=ACCENT, activeforeground="#ffffff",
            disabledforeground="#555555",
            font=("Segoe UI", 11, "bold"),
            relief="flat", bd=0, cursor="hand2",
            padx=18, pady=10,
        )
        if state == "disabled":
            b.configure(state="disabled", bg="#252545")
        return b

    def _entry(self, parent, textvariable, width=22):
        return tk.Entry(
            parent, textvariable=textvariable, width=width,
            bg=BG_INPUT, fg=FG, insertbackground=FG,
            relief="flat", bd=6,
            font=("Segoe UI", 11),
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )

    def _spinbox(self, parent, variable, lo, hi, fmt=None, step=1):
        kw = dict(
            from_=lo, to=hi, textvariable=variable, width=12,
            bg=BG_INPUT, fg=FG, insertbackground=FG,
            buttonbackground=BG_INPUT,
            relief="flat", bd=4,
            font=("Segoe UI", 11),
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT,
            increment=step,
        )
        if fmt:
            kw["format"] = fmt
        return tk.Spinbox(parent, **kw)

    def _optionmenu(self, parent, variable, values):
        om = tk.OptionMenu(parent, variable, *values)
        om.configure(
            bg=BG_INPUT, fg=FG,
            activebackground=ACCENT, activeforeground="#fff",
            relief="flat", bd=0,
            font=("Segoe UI", 11),
            highlightthickness=1, highlightbackground=BORDER,
            indicatoron=True, width=10,
        )
        om["menu"].configure(
            bg=BG_CARD, fg=FG,
            activebackground=ACCENT, activeforeground="#fff",
            relief="flat", bd=0,
        )
        return om

    def _card(self, parent, title):
        """Create a tk.LabelFrame styled as a dark card."""
        return tk.LabelFrame(
            parent, text=f"  {title}  ",
            bg=BG_CARD, fg=ACCENT,
            font=("Segoe UI", 10, "bold"),
            relief="flat", bd=2,
            highlightthickness=1, highlightbackground=BORDER,
        )

    def _label(self, parent, text, bg=None, fg=None, font=None):
        return tk.Label(
            parent, text=text,
            bg=bg or BG_CARD, fg=fg or FG,
            font=font or ("Segoe UI", 11),
        )

    def _checkbutton(self, parent, text, variable):
        return tk.Checkbutton(
            parent, text=text, variable=variable,
            bg=BG_CARD, fg=FG,
            activebackground=BG_CARD, activeforeground=FG,
            selectcolor=BG_INPUT,
            font=("Segoe UI", 11),
            relief="flat", bd=0,
        )

    # ── Build UI ────────────────────────────────────────────────────

    def _build_ui(self):
        # Status bar — packed first so it reserves space at the bottom
        self.status_label = tk.Label(
            self.root, anchor="w",
            bg=BG_LOG, fg=FG_DIM, font=("Segoe UI", 10),
        )
        self.status_label.pack(fill="x", side="bottom", ipady=4)

        # Main content: grid with row weights — notebook 40%, log 60%
        main = tk.Frame(self.root, bg=BG_MAIN)
        main.pack(fill="both", expand=True)
        main.rowconfigure(0, weight=0)   # notebook — altura natural
        main.rowconfigure(1, weight=3)   # log — ocupar más espacio relativo
        main.columnconfigure(0, weight=1)

        nb = ttk.Notebook(main)
        nb.grid(row=0, column=0, sticky="nsew", padx=18, pady=(4, 2))

        nb.add(self._build_connection_tab(nb), text="  Connection  ")
        nb.add(self._build_settings_tab(nb), text="  Settings  ")

        # Log — 60% of main area
        log_outer = self._card(main, "Log")
        log_outer.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 6))
        log_outer.rowconfigure(0, weight=1)
        log_outer.columnconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_outer, bg=BG_LOG, fg="#7ec88a",
            insertbackground=FG, font=("Consolas", 10),
            relief="flat", borderwidth=0, highlightthickness=0,
            state="disabled", wrap="word",
        )
        sb = tk.Scrollbar(log_outer, orient="vertical",
                           command=self.log_text.yview,
                           bg=BG_CARD, troughcolor=BG_MAIN,
                           activebackground=ACCENT, relief="flat", bd=0)
        self.log_text.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns", padx=(0, 4), pady=6)
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=6)

        self._update_status_bar()

    def _build_connection_tab(self, parent) -> ttk.Frame:
        tab = ttk.Frame(parent)   # ttk Frame so notebook background works

        # ── Server card ──
        srv = self._card(tab, "Server Mode  —  this PC shares keyboard & mouse")
        srv.pack(fill="x", padx=10, pady=(4, 2))

        srv_inner = tk.Frame(srv, bg=BG_CARD)
        srv_inner.pack(fill="x", padx=12, pady=4)

        self.server_dot = tk.Label(srv_inner, text="\u2b24",
                                    bg=BG_CARD, fg="#444", font=("Segoe UI", 16))
        self.server_dot.pack(side="left")

        self.server_status_lbl = tk.Label(srv_inner, text="Stopped",
                                           bg=BG_CARD, fg=FG_DIM,
                                           font=("Segoe UI", 10))
        self.server_status_lbl.pack(side="left", padx=(8, 0))

        # spacer
        tk.Frame(srv_inner, bg=BG_CARD).pack(side="left", fill="x", expand=True)

        self.stop_server_btn = self._btn(srv_inner, "\u25a0  Stop",
                                          self.stop_server, bg="#4a2020",
                                          state="disabled")
        self.stop_server_btn.pack(side="right", padx=(6, 0))

        self.start_server_btn = self._btn(srv_inner, "\u25b6  Start Server",
                                           self.start_server)
        self.start_server_btn.pack(side="right")

        # ── Client card ──
        cli = self._card(tab, "Client Mode  —  Esta PC recibe entrada")
        cli.pack(fill="x", padx=10, pady=(0, 4))

        row0 = tk.Frame(cli, bg=BG_CARD)
        row0.pack(fill="x", padx=12, pady=(4, 2))

        self.client_dot = tk.Label(row0, text="\u2b24",
                                    bg=BG_CARD, fg="#444", font=("Segoe UI", 16))
        self.client_dot.pack(side="left")

        self.client_status_lbl = tk.Label(row0, text="Desconectado",
                                           bg=BG_CARD, fg=FG_DIM,
                                           font=("Segoe UI", 10))
        self.client_status_lbl.pack(side="left", padx=(8, 0))

        row1 = tk.Frame(cli, bg=BG_CARD)
        row1.pack(fill="x", padx=12, pady=(0, 4))

        self._label(row1, "IP del servidor:").pack(side="left")

        self.ip_entry = self._entry(row1, self.ip_var, width=22)
        self.ip_entry.pack(side="left", padx=(8, 10))
        self.ip_entry.bind("<Return>", lambda _: self.start_client())

        self.start_client_btn = self._btn(row1, "\u25b6  Conectar",
                                           self.start_client)
        self.start_client_btn.pack(side="left")

        self.stop_client_btn = self._btn(row1, "\u25a0  Detener",
                                          self.stop_client, bg="#4a2020",
                                          state="disabled")
        self.stop_client_btn.pack(side="left", padx=(6, 0))

        return tab

    def _build_settings_tab(self, parent) -> ttk.Frame:
        tab = ttk.Frame(parent)

        cfg = self._card(tab, "Configuración")
        cfg.pack(fill="x", padx=10, pady=(12, 6))

        grid = tk.Frame(cfg, bg=BG_CARD)
        grid.pack(fill="x", padx=16, pady=12)

        fields = [
            ("Puerto:",                    self._spinbox(grid, self.port_var, 1024, 65535)),
            ("Borde de cambio:",             self._optionmenu(grid, self.edge_var,
                                                          ["derecha", "izquierda", "arriba", "abajo"])),
            ("Margen de cambio (px):",      self._spinbox(grid, self.margin_var, 1, 50)),
            ("Velocidad del puntero del cliente:",    self._spinbox(grid, self.speed_var, 0.10, 4.00,
                                                       fmt="%.2f", step=0.10)),
            ("Intervalo de latido (seg):", self._spinbox(grid, self.heartbeat_var, 1, 60)),
            ("Tecla de cambio:",           self._entry(grid, self.hotkey_var, width=24)),
            ("Clave compartida:",           self._entry(grid, self.secret_var, width=24)),
        ]
        for i, (lbl_text, widget) in enumerate(fields):
            self._label(grid, lbl_text).grid(
                row=i, column=0, sticky="e", padx=(0, 12), pady=6)
            widget.grid(row=i, column=1, sticky="w", pady=6)

        # Clipboard checkbox
        self.clip_check = self._checkbutton(
            grid, "Sincronizar portapapeles entre PCs", self.clipboard_var)
        self.clip_check.grid(row=len(fields), column=0, columnspan=2,
                              sticky="w", pady=(8, 2))

        # Hotkey hint
        tk.Label(grid, text="Format: <ctrl>+<alt>+s",
                  bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8)
                  ).grid(row=len(fields) - 2, column=2, sticky="w", padx=(10, 0))

        # Secret hint
        tk.Label(grid, text="Must match on both PCs",
                  bg=BG_CARD, fg=FG_DIM, font=("Segoe UI", 8)
                  ).grid(row=len(fields) - 1, column=2, sticky="w", padx=(10, 0))

        # Buttons
        btn_row = tk.Frame(tab, bg=BG_MAIN)
        btn_row.pack(fill="x", padx=10, pady=(4, 10))

        self._btn(btn_row, "Reset defaults",
                   self.reset_config).pack(side="right", padx=(6, 0))
        self._btn(btn_row, "Save config.json",
                   self.save_config).pack(side="right")

        return tab

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
        self.secret_var.set(cfg.get("shared_secret", ""))
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
            "shared_secret": self.secret_var.get().strip(),
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
        if running:
            self.start_server_btn.configure(state="disabled", bg="#252545")
            self.stop_server_btn.configure(state="normal", bg="#4a2020")
        else:
            self.start_server_btn.configure(state="normal", bg=BG_INPUT)
            self.stop_server_btn.configure(state="disabled", bg="#252545")
        self.server_dot.configure(fg=GREEN if running else "#444")
        self.server_status_lbl.configure(
            text="Running \u2014 waiting for client..." if running else "Stopped",
            fg=GREEN if running else FG_DIM)
        self._update_status_bar()

    def _set_client_state(self, running: bool):
        if running:
            self.start_client_btn.configure(state="disabled", bg="#252545")
            self.stop_client_btn.configure(state="normal", bg="#4a2020")
            self.ip_entry.configure(state="disabled")
        else:
            self.start_client_btn.configure(state="normal", bg=BG_INPUT)
            self.stop_client_btn.configure(state="disabled", bg="#252545")
            self.ip_entry.configure(state="normal")
        self.client_dot.configure(fg=GREEN if running else "#444")
        self.client_status_lbl.configure(
            text="Connected" if running else "Disconnected",
            fg=GREEN if running else FG_DIM)
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
        # Poll every 2s — low enough to catch crashes promptly, fast enough to be light
        self.root.after(2000, self._poll_processes)

    def _log(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        widget = self.log_text
        widget.configure(state="normal")
        # Cap log at 500 lines to prevent unbounded memory growth
        line_count = int(widget.index("end-1c").split(".")[0])
        if line_count > 500:
            widget.delete("1.0", "50.0")  # remove oldest 50 lines at once
        widget.insert("end", f"[{ts}] {text}\n")
        widget.see("end")
        widget.configure(state="disabled")

    # ── System tray ─────────────────────────────────────────────────

    def _create_tray_image(self) -> Image.Image:
        """Draw a simple 64x64 icon for the tray."""
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(img)
        dc.rounded_rectangle([4, 4, 60, 60], radius=12, fill="#1a1a2e", outline="#e94560", width=3)
        dc.text((16, 14), "MH", fill="#e94560")
        return img

    def _on_minimize(self, event=None):
        """When the window is minimized, hide it and show a tray icon."""
        if self.root.state() == "iconic":
            self.root.withdraw()
            if self.tray_icon is None:
                menu = pystray.Menu(
                    pystray.MenuItem("Abrir myHards", self._tray_restore, default=True),
                    pystray.MenuItem("Cerrar", self._tray_quit),
                )
                self.tray_icon = pystray.Icon("myHards", self._create_tray_image(),
                                              "myHards", menu)
                threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _tray_restore(self, icon=None, item=None):
        """Restore the window from tray."""
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after(0, self._show_window)

    def _show_window(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def _tray_quit(self, icon=None, item=None):
        """Close the app from the tray menu."""
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.after(0, self._on_close)

    # ── Window close ────────────────────────────────────────────────

    def _on_close(self):
        self.save_config()
        if self.tray_icon:
            self.tray_icon.stop()
            self.tray_icon = None
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
