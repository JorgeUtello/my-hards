"""
Client (remote PC): receives mouse/keyboard events from the server
and replays them locally.
"""

import hashlib
import hmac
import socket
import sys
import threading
import time
import logging

try:
    import pyperclip as _pyperclip
except ImportError:
    _pyperclip = None

from pynput.mouse import Button, Controller as MouseController
from pynput.keyboard import Key, Controller as KeyController, KeyCode

from protocol import (MessageType, encode_message, recv_message,
                      create_tls_context_client)
from config import load_config
from input_utils import get_screen_size, is_at_edge, opposite_edge

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("client")


# Map button names from pynput
BUTTON_MAP = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


class Client:
    def __init__(self, server_ip: str, config: dict):
        self.server_ip = server_ip
        self.config = config
        self.port = config["port"]
        self.screen_w, self.screen_h = get_screen_size()
        self.pointer_speed = float(config.get("client_pointer_speed", 1.0))

        self.sock: socket.socket | None = None
        self.active = False          # True when this PC is receiving input
        self.running = True
        self.lock = threading.Lock()

        self.mouse = MouseController()
        self.kb = KeyController()

        self.server_edge = "right"   # Updated from server hello
        self.entry_edge = "left"     # Edge where cursor enters on this screen

        log.info(
            "Screen: %dx%d | Server: %s:%d | Pointer speed: %.2fx",
            self.screen_w, self.screen_h, self.server_ip, self.port, self.pointer_speed,
        )

    # ── Networking ──────────────────────────────────────────────────

    def start(self):
        """Connect to the server and start handling input events."""
        tls_ctx = create_tls_context_client()
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        log.info("Connecting to %s:%d (TLS) ...", self.server_ip, self.port)
        raw_sock.connect((self.server_ip, self.port))
        raw_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = tls_ctx.wrap_socket(raw_sock, server_hostname="myHards")
        log.info("Connected (TLS)!")

        if not self._auth_handshake():
            log.error("Authentication FAILED — shared_secret doesn't match server")
            self._cleanup()
            return
        log.info("Authenticated!")

        # Immediately tell the server our screen dimensions
        self._send(MessageType.CLIENT_INFO, {
            "screen_w": self.screen_w,
            "screen_h": self.screen_h,
        })

        # Optionally stream local webcam to the server
        if self.config.get("webcam_share"):
            from camera_stream import CameraStream
            self._cam_stream = CameraStream(
                self.server_ip,
                self.config.get("camera_port", 24801),
                fps=self.config.get("camera_fps", 15),
                width=self.config.get("camera_width", 640),
                height=self.config.get("camera_height", 480),
            )
            threading.Thread(target=self._cam_stream.start, daemon=True).start()
            log.info("Stream de cámara iniciado")

        self._receive_loop()

    def _auth_handshake(self) -> bool:
        """Client-side: respond to server's HMAC challenge."""
        msg = recv_message(self.sock)
        if msg is None or msg.get("type") != MessageType.AUTH_CHALLENGE:
            return False
        nonce = msg.get("data", {}).get("nonce", "")
        response = hmac.new(
            self.config["shared_secret"].encode(),
            nonce.encode(),
            hashlib.sha256,
        ).hexdigest()
        self._send(MessageType.AUTH_RESPONSE, {"hmac": response})
        result = recv_message(self.sock)
        return result is not None and result.get("type") == MessageType.AUTH_OK

    def _send(self, msg_type: MessageType, data: dict = None):
        sock = self.sock
        if not sock:
            return
        msg = encode_message(msg_type, data)
        with self.lock:
            try:
                sock.sendall(msg)
            except OSError:
                log.error("Lost connection to server")
                self.running = False

    def _receive_loop(self):
        """Main loop: receive and handle messages from server."""
        try:
            while self.running:
                msg = recv_message(self.sock)
                if msg is None:
                    log.warning("Server disconnected")
                    break
                self._handle_message(msg)
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    # ── Message handling ────────────────────────────────────────────

    def _handle_message(self, msg: dict):
        msg_type = msg.get("type")
        data = msg.get("data", {})

        if msg_type == MessageType.HELLO:
            self.server_edge = data.get("edge", "right")
            self.entry_edge = opposite_edge(self.server_edge)
            log.info(
                "Server screen: %dx%d | Entry edge: %s",
                data.get("screen_w"), data.get("screen_h"), self.entry_edge,
            )

        elif msg_type == MessageType.SWITCH_TO_CLIENT:
            self._activate(data)

        elif msg_type == MessageType.MOUSE_MOVE:
            if self.active:
                self._handle_mouse_move(data)

        elif msg_type == MessageType.MOUSE_CLICK:
            if self.active:
                self._handle_mouse_click(data)

        elif msg_type == MessageType.MOUSE_SCROLL:
            if self.active:
                self._handle_mouse_scroll(data)

        elif msg_type == MessageType.KEY_PRESS:
            if self.active:
                self._handle_key_press(data)

        elif msg_type == MessageType.KEY_RELEASE:
            if self.active:
                self._handle_key_release(data)

        elif msg_type == MessageType.CLIPBOARD_SYNC:
            self._handle_clipboard(data)

        elif msg_type == MessageType.HEARTBEAT:
            pass  # Keep-alive, nothing to do

    # ── Activation / deactivation ───────────────────────────────────

    def _activate(self, data: dict):
        """Server switched input to us."""
        self.active = True
        edge = data.get("edge", self.server_edge)
        self.entry_edge = opposite_edge(edge)
        # Place cursor at the entry edge
        if self.entry_edge == "left":
            self.mouse.position = (0, self.screen_h // 2)
        elif self.entry_edge == "right":
            self.mouse.position = (self.screen_w - 1, self.screen_h // 2)
        elif self.entry_edge == "top":
            self.mouse.position = (self.screen_w // 2, 0)
        elif self.entry_edge == "bottom":
            self.mouse.position = (self.screen_w // 2, self.screen_h - 1)
        log.info("← Input ACTIVE (entry edge: %s)", self.entry_edge)

    def _deactivate(self):
        """Switch input back to server."""
        if not self.active:
            return
        self.active = False
        # Send current cursor position so server can map it proportionally
        cx, cy = self.mouse.position
        log.info("→ Input returned to SERVER (cursor at %d,%d)", cx, cy)
        self._send(MessageType.SWITCH_TO_SERVER, {
            "cursor_x": cx,
            "cursor_y": cy,
            "screen_w": self.screen_w,
            "screen_h": self.screen_h,
        })

    # ── Mouse handlers ──────────────────────────────────────────────

    def _handle_mouse_move(self, data: dict):
        dx = int(round(data.get("dx", 0) * self.pointer_speed))
        dy = int(round(data.get("dy", 0) * self.pointer_speed))
        cx, cy = self.mouse.position
        nx = cx + dx
        ny = cy + dy

        # Check if cursor would leave from the entry edge (return to server)
        if is_at_edge(nx, ny, self.entry_edge, self.screen_w, self.screen_h, margin=2):
            self._deactivate()
            return

        # Clamp to screen bounds
        nx = max(0, min(self.screen_w - 1, nx))
        ny = max(0, min(self.screen_h - 1, ny))
        self.mouse.position = (nx, ny)

    def _handle_mouse_click(self, data: dict):
        button = BUTTON_MAP.get(data.get("button", "left"), Button.left)
        if data.get("pressed"):
            self.mouse.press(button)
        else:
            self.mouse.release(button)

    def _handle_mouse_scroll(self, data: dict):
        dx = data.get("dx", 0)
        dy = data.get("dy", 0)
        self.mouse.scroll(dx, dy)

    # ── Keyboard handlers ───────────────────────────────────────────

    def _handle_key_press(self, data: dict):
        key = _deserialize_key(data.get("key", {}))
        if key:
            try:
                self.kb.press(key)
            except Exception:
                pass

    def _handle_key_release(self, data: dict):
        key = _deserialize_key(data.get("key", {}))
        if key:
            try:
                self.kb.release(key)
            except Exception:
                pass

    # ── Clipboard ───────────────────────────────────────────────────

    def _handle_clipboard(self, data: dict):
        if not self.config.get("clipboard_sync") or _pyperclip is None:
            return
        text = data.get("text", "")
        if text:
            try:
                _pyperclip.copy(text)
                log.info("Clipboard synced from server (%d chars)", len(text))
            except Exception:
                pass

    def _cleanup(self):
        self.running = False
        if hasattr(self, '_cam_stream'):
            self._cam_stream.stop()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        log.info("Client stopped.")


def _deserialize_key(key_data: dict):
    """Deserialize a key from JSON dict back to pynput key object."""
    key_type = key_data.get("type")
    if key_type == "char":
        value = key_data.get("value")
        if value:
            return KeyCode.from_char(value)
    elif key_type == "vk":
        vk = key_data.get("value")
        if vk is not None:
            return KeyCode.from_vk(vk)
    elif key_type == "special":
        name = key_data.get("name")
        if name:
            try:
                return Key[name]
            except KeyError:
                pass
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python client.py <server_ip>")
        print("  Example: python client.py 192.168.1.100")
        sys.exit(1)

    server_ip = sys.argv[1]
    config = load_config()
    client = Client(server_ip, config)
    client.start()


if __name__ == "__main__":
    main()
