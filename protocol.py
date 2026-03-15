"""
Protocol definitions and message types for myHards.
All messages are JSON-encoded, length-prefixed (4 bytes, big-endian).
TLS encryption and HMAC authentication protect the connection.
"""

import datetime
import json
import os
import socket
import ssl
import struct
from enum import Enum

# Pre-compiled struct for 4-byte big-endian unsigned int (length prefix)
_STRUCT4 = struct.Struct("!I")

# Fast binary frame for MOUSE_MOVE (hot path — avoids JSON alloc at 125 Hz)
# Frame layout: [4-byte length=5][0xFF marker][dx: i16 BE][dy: i16 BE] = 9 bytes total
_MOVE_STRUCT      = struct.Struct("!hh")                        # 2 × signed short
_MOVE_PAYLOAD_LEN = 5                                           # marker(1) + data(4)
_FAST_MOVE_PREFIX = _STRUCT4.pack(_MOVE_PAYLOAD_LEN) + b'\xff'  # pre-computed 5 bytes


def encode_mouse_move(dx: int, dy: int) -> bytes:
    """Encode MOUSE_MOVE as a compact 9-byte binary frame (vs ~45-byte JSON)."""
    return _FAST_MOVE_PREFIX + _MOVE_STRUCT.pack(dx, dy)


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
    CLIENT_INFO = "client_info"  # client sends its screen dimensions to server
    AUTH_CHALLENGE = "auth_challenge"
    AUTH_RESPONSE = "auth_response"
    AUTH_OK = "auth_ok"
    AUTH_FAIL = "auth_fail"


# Valid message types for fast validation (frozenset is slightly faster for 'in')
_VALID_TYPES = frozenset(t.value for t in MessageType)

# Maximum message size (64 KB — input events are tiny)
MAX_MESSAGE_SIZE = 65_536


def encode_message(msg_type: MessageType, data: dict = None) -> bytes:
    """Encode a message as length-prefixed JSON bytes."""
    payload = {"type": msg_type.value}
    if data:
        payload["data"] = data
    json_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return _STRUCT4.pack(len(json_bytes)) + json_bytes


def recv_message(sock: socket.socket) -> dict | None:
    """Receive a length-prefixed JSON message from a socket. Returns None on disconnect."""
    raw_len = _recv_exact(sock, 4)
    if raw_len is None:
        return None
    msg_len = _STRUCT4.unpack(raw_len)[0]
    if msg_len > MAX_MESSAGE_SIZE:
        return None
    raw_data = _recv_exact(sock, msg_len)
    if raw_data is None:
        return None
    # Fast path: binary MOUSE_MOVE (9-byte frame, marker byte 0xFF)
    if msg_len == _MOVE_PAYLOAD_LEN and raw_data[0] == 0xFF:
        dx, dy = _MOVE_STRUCT.unpack(raw_data[1:])
        return {"type": "mouse_move", "data": {"dx": dx, "dy": dy}}
    try:
        msg = json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(msg, dict) or msg.get("type") not in _VALID_TYPES:
        return None
    return msg


def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Receive exactly n bytes from a socket using a pre-allocated buffer."""
    buf = bytearray(n)
    view = memoryview(buf)
    pos = 0
    try:
        while pos < n:
            received = sock.recv_into(view[pos:], n - pos)
            if not received:
                return None
            pos += received
    except (ConnectionResetError, ConnectionAbortedError, OSError):
        return None
    return bytes(buf)


# ── TLS helpers ─────────────────────────────────────────────────────

def ensure_certs(cert_path: str, key_path: str):
    """Generate a self-signed TLS certificate/key pair if they don't exist."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "myHards")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .sign(key, hashes.SHA256())
    )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))


def create_tls_context_server(cert_path: str, key_path: str) -> ssl.SSLContext:
    """Create a server-side TLS context with the given cert/key."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def create_tls_context_client() -> ssl.SSLContext:
    """Create a client-side TLS context (self-signed, no hostname verification)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
