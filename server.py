"""
Server (host PC): captures mouse/keyboard and forwards events to the client
when the cursor crosses the screen edge.

Mouse relay inspired by Barrier/Synergy: a dedicated polling thread reads
GetCursorPos at ~500 Hz, computes deltas, recenters with SetCursorPos, and
hides the server cursor while relaying.  pynput is used only for edge
detection (when idle) and keyboard/click/scroll forwarding.
"""

import ctypes
import ctypes.wintypes as wintypes
import os
import socket
import sys
import threading
import time
import logging

from pynput import mouse, keyboard
from pynput.mouse import Controller as MouseController

from protocol import MessageType, encode_message, recv_message
from config import load_config
from input_utils import get_screen_size, is_at_edge, lock_cursor_to_edge, opposite_edge

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("server")

# Win32 helpers
_user32 = ctypes.windll.user32


class Server:
    def __init__(self, config: dict):
        self.config = config
        self.port = config["port"]
        self.switch_edge = config["switch_edge"]
        self.margin = config["switch_margin"]
        self.screen_w, self.screen_h = get_screen_size()

        self.client_sock: socket.socket | None = None
        self.active = False          # True when input is being sent to client
        self.running = True
        self.lock = threading.Lock()
        self.mouse_ctrl = MouseController()

        # Center anchor for relay mode
        self._cx = self.screen_w // 2
        self._cy = self.screen_h // 2

        # Cooldown after switching back to server (prevents instant re-trigger)
        self._switch_back_until = 0.0
        self._SWITCH_BACK_GRACE = 0.6  # seconds

        # Focus tracking: only gate edge detection when our app lacks focus.
        # NEVER blocks relay/click/key forwarding while active.
        self._app_focused = True
        self._my_pids = {os.getpid(), os.getppid()}

        # Client screen dimensions (received via CLIENT_INFO message)
        self.client_screen_w = config.get("client_screen_width", 1920)
        self.client_screen_h = config.get("client_screen_height", 1080)

        # Hotkey suppression: don't forward keys for a short window after hotkey fires
        self._suppress_until = 0.0

        # Cursor visibility counter (ShowCursor is ref-counted)
        self._cursor_hidden = False

        log.info(
            "Screen: %dx%d | Edge: %s | Port: %d",
            self.screen_w, self.screen_h, self.switch_edge, self.port,
        )

    # ── Networking ──────────────────────────────────────────────────

    def start(self):
        """Start the server: listen for a client, then capture input."""
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("0.0.0.0", self.port))
        srv.listen(1)
        log.info("Waiting for client on port %d ...", self.port)

        conn, addr = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.client_sock = conn
        log.info("Client connected from %s", addr[0])

        # Send hello with screen info
        self._send(MessageType.HELLO, {
            "screen_w": self.screen_w,
            "screen_h": self.screen_h,
            "edge": self.switch_edge,
        })

        # Start receiver thread (for switch-back messages)
        threading.Thread(target=self._receive_loop, daemon=True).start()

        # Start heartbeat
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()

        # Start focus monitor
        threading.Thread(target=self._focus_loop, daemon=True).start()

        # Start mouse relay polling thread (Barrier-style)
        threading.Thread(target=self._relay_loop, daemon=True).start()

        # Start input listeners (blocks)
        self._start_listeners()

    def _send(self, msg_type: MessageType, data: dict = None):
        with self.lock:
            if self.client_sock:
                try:
                    self.client_sock.sendall(encode_message(msg_type, data))
                except OSError:
                    log.error("Lost connection to client")
                    self.running = False

    def _receive_loop(self):
        """Listen for messages from the client (e.g. switch-back)."""
        while self.running:
            msg = recv_message(self.client_sock)
            if msg is None:
                log.warning("Client disconnected")
                self.running = False
                break
            msg_type = msg.get("type")
            if msg_type == MessageType.CLIENT_INFO:
                data = msg.get("data", {})
                self.client_screen_w = data.get("screen_w", self.client_screen_w)
                self.client_screen_h = data.get("screen_h", self.client_screen_h)
                log.info("Client screen: %dx%d", self.client_screen_w, self.client_screen_h)
            elif msg_type == MessageType.SWITCH_TO_SERVER:
                self._switch_to_server(msg.get("data", {}))
            elif msg_type == MessageType.CLIPBOARD_SYNC:
                self._handle_clipboard(msg.get("data", {}))

    def _heartbeat_loop(self):
        interval = self.config.get("heartbeat_interval", 5)
        while self.running:
            time.sleep(interval)
            self._send(MessageType.HEARTBEAT)

    def _focus_loop(self):
        """Poll Windows foreground window every 100 ms to track focus."""
        user32 = ctypes.windll.user32
        while self.running:
            try:
                hwnd = user32.GetForegroundWindow()
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                self._app_focused = pid.value in self._my_pids
            except Exception:
                self._app_focused = True  # fail-open
            time.sleep(0.1)

    # ── Cursor visibility (Barrier-style) ──────────────────────────

    def _hide_cursor(self):
        """Hide the server cursor while relaying (ref-counted)."""
        if not self._cursor_hidden:
            _user32.ShowCursor(False)
            self._cursor_hidden = True

    def _show_cursor(self):
        """Re-show the server cursor."""
        if self._cursor_hidden:
            _user32.ShowCursor(True)
            self._cursor_hidden = False

    # ── Switching ───────────────────────────────────────────────────

    def _switch_to_client(self):
        """Called when cursor hits the edge — redirect input to client."""
        if self.active:
            return
        self.active = True
        log.info("→ Switched to CLIENT")
        self._send(MessageType.SWITCH_TO_CLIENT, {
            "edge": self.switch_edge,
        })
        # Warp cursor to center and hide it
        _user32.SetCursorPos(self._cx, self._cy)
        self._hide_cursor()

    def _switch_to_server(self, data: dict = None):
        """Called when client signals the cursor came back."""
        if not self.active:
            return
        self.active = False
        self._show_cursor()

        # Map client cursor position proportionally onto server screen
        if data:
            cli_x = data.get("cursor_x", self.client_screen_w // 2)
            cli_y = data.get("cursor_y", self.client_screen_h // 2)
        else:
            cli_x = self.client_screen_w // 2
            cli_y = self.client_screen_h // 2

        pct_x = cli_x / max(1, self.client_screen_w)
        pct_y = cli_y / max(1, self.client_screen_h)
        target_x = int(pct_x * self.screen_w)
        target_y = int(pct_y * self.screen_h)

        # Keep cursor away from the switch edge so we don't immediately re-trigger
        safe_margin = 80
        if self.switch_edge == "right":
            target_x = min(target_x, self.screen_w - safe_margin)
        elif self.switch_edge == "left":
            target_x = max(target_x, safe_margin)
        elif self.switch_edge == "bottom":
            target_y = min(target_y, self.screen_h - safe_margin)
        elif self.switch_edge == "top":
            target_y = max(target_y, safe_margin)

        target_x = max(0, min(self.screen_w - 1, target_x))
        target_y = max(0, min(self.screen_h - 1, target_y))

        # Set cooldown BEFORE warping so the callback doesn't re-trigger
        self._switch_back_until = time.monotonic() + self._SWITCH_BACK_GRACE
        _user32.SetCursorPos(target_x, target_y)
        log.info("← Switched back to SERVER, cursor at (%d, %d)", target_x, target_y)

    # ── Clipboard ───────────────────────────────────────────────────

    def _handle_clipboard(self, data: dict):
        if not self.config.get("clipboard_sync"):
            return
        text = data.get("text", "")
        if text:
            try:
                import pyperclip
                pyperclip.copy(text)
                log.info("Clipboard synced from client (%d chars)", len(text))
            except Exception:
                pass

    # ── Mouse relay polling loop (Barrier-style) ──────────────────

    def _relay_loop(self):
        """
        Dedicated thread: polls GetCursorPos at ~500 Hz while active,
        computes deltas from center, sends them, and recenters with
        SetCursorPos.  This avoids all callback/warp timing issues.
        """
        point = wintypes.POINT()
        cx, cy = self._cx, self._cy

        while self.running:
            if not self.active:
                time.sleep(0.05)  # idle — no need to poll fast
                continue

            _user32.GetCursorPos(ctypes.byref(point))
            dx = point.x - cx
            dy = point.y - cy

            if dx != 0 or dy != 0:
                self._send(MessageType.MOUSE_MOVE, {"dx": dx, "dy": dy})
                _user32.SetCursorPos(cx, cy)

            time.sleep(0.002)  # ~500 Hz

    # ── Input capture ───────────────────────────────────────────────

    def _start_listeners(self):
        """Start mouse & keyboard listeners (runs in current thread context)."""
        mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        key_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        hotkey_str = self.config.get("switch_hotkey", "<ctrl>+<alt>+s")
        hotkey_listener = keyboard.GlobalHotKeys({hotkey_str: self._on_hotkey})

        mouse_listener.start()
        key_listener.start()
        hotkey_listener.start()
        log.info("Input capture active. Hotkey: %s | Ctrl+Alt+Q to quit.", hotkey_str)

        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            self._show_cursor()  # Ensure cursor is visible on exit
            mouse_listener.stop()
            key_listener.stop()
            hotkey_listener.stop()
            self._cleanup()

    def _on_hotkey(self):
        """Called when the manual switch hotkey is pressed."""
        self._suppress_until = time.time() + 0.35  # suppress next 350 ms of key events
        if self.active:
            log.info("Hotkey → switching back to SERVER")
            self._switch_to_server()
        else:
            log.info("Hotkey → switching to CLIENT")
            self._switch_to_client()

    def _on_mouse_move(self, x: int, y: int):
        # Mouse relay is handled by _relay_loop — this callback is
        # only used for edge detection when NOT active.
        if self.active:
            return

        # Only detect edge if our app has foreground focus
        if not self._app_focused:
            return

        if time.monotonic() < self._switch_back_until:
            return
        if is_at_edge(x, y, self.switch_edge, self.screen_w, self.screen_h, self.margin):
            self._switch_to_client()

    def _on_mouse_click(self, x, y, button, pressed):
        if not self.active:
            return
        self._send(MessageType.MOUSE_CLICK, {
            "button": button.name,
            "pressed": pressed,
        })

    def _on_mouse_scroll(self, x, y, dx, dy):
        if not self.active:
            return
        self._send(MessageType.MOUSE_SCROLL, {"dx": dx, "dy": dy})

    def _on_key_press(self, key):
        # Ctrl+Alt+Q to quit
        if hasattr(key, "char") and key.char == "\x11":  # Ctrl+Q
            self.running = False
            return False

        # Suppress hotkey combo keys so they're not forwarded to client
        if time.time() < self._suppress_until:
            return

        if not self.active:
            return
        self._send(MessageType.KEY_PRESS, {"key": _serialize_key(key)})

    def _on_key_release(self, key):
        # Suppress hotkey combo keys
        if time.time() < self._suppress_until:
            return

        if not self.active:
            return
        self._send(MessageType.KEY_RELEASE, {"key": _serialize_key(key)})

    def _cleanup(self):
        self.running = False
        if self.client_sock:
            try:
                self.client_sock.close()
            except OSError:
                pass
        log.info("Server stopped.")


def _serialize_key(key) -> dict:
    """Serialize a pynput key to a JSON-safe dict."""
    if hasattr(key, "char") and key.char is not None:
        return {"type": "char", "value": key.char}
    elif hasattr(key, "vk"):
        return {"type": "vk", "value": key.vk, "name": key.name if hasattr(key, "name") else str(key)}
    else:
        return {"type": "special", "name": key.name}


def main():
    config = load_config()
    server = Server(config)
    server.start()


if __name__ == "__main__":
    main()
