"""
Protocol definitions and message types for my-hards.
All messages are JSON-encoded, length-prefixed (4 bytes, big-endian).
"""

import json
import struct
import socket
from enum import Enum


class MessageType(str, Enum):
    MOUSE_MOVE = "mouse_move"
    MOUSE_CLICK = "mouse_click"
    MOUSE_SCROLL = "mouse_scroll"
    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    SWITCH_TO_CLIENT = "switch_to_client"
    SWITCH_TO_SERVER = "switch_to_server"
    CLIPBOARD_SYNC = "clipboard_sync"
    HEARTBEAT = "heartbeat"
    HELLO = "hello"


def encode_message(msg_type: MessageType, data: dict = None) -> bytes:
    """Encode a message as length-prefixed JSON bytes."""
    payload = {"type": msg_type.value}
    if data:
        payload["data"] = data
    json_bytes = json.dumps(payload).encode("utf-8")
    return struct.pack("!I", len(json_bytes)) + json_bytes


def recv_message(sock: socket.socket) -> dict | None:
    """Receive a length-prefixed JSON message from a socket. Returns None on disconnect."""
    raw_len = _recv_exact(sock, 4)
    if raw_len is None:
        return None
    msg_len = struct.unpack("!I", raw_len)[0]
    if msg_len > 1_000_000:  # 1 MB sanity limit
        return None
    raw_data = _recv_exact(sock, msg_len)
    if raw_data is None:
        return None
    return json.loads(raw_data.decode("utf-8"))


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Receive exactly n bytes from a socket."""
    buf = bytearray()
    while len(buf) < n:
        try:
            chunk = sock.recv(n - len(buf))
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            return None
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)
