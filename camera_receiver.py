"""
Camera receiver (server side): accepts JPEG frames from the client and
feeds them into pyvirtualcam using the Unity Capture DirectShow backend.
Teams and other video-call apps will see it as "Unity Video Capture".

Requires:
  pip install pyvirtualcam opencv-python
  Unity Capture driver registered (handled automatically by Electron main.js).
"""

import socket
import struct
import logging

log = logging.getLogger("camera_receiver")

_pyvirtualcam = None
_cv2          = None
_np           = None

try:
    import pyvirtualcam as _pvc
    _pyvirtualcam = _pvc
except ImportError:
    pass

try:
    import cv2 as _cv2_import
    _cv2 = _cv2_import
except ImportError:
    pass

try:
    import numpy as _np_import
    _np = _np_import
except ImportError:
    pass


class CameraReceiver:
    def __init__(self, port: int, width: int = 640, height: int = 480, fps: int = 15):
        self.port        = port
        self.width       = width
        self.height      = height
        self.fps         = fps
        self.running     = False
        self._srv_sock: socket.socket | None = None

    def start(self):
        if _pyvirtualcam is None:
            log.error("pyvirtualcam no instalado — instala con: pip install pyvirtualcam")
            return
        if _cv2 is None:
            log.error("opencv-python no instalado — instala con: pip install opencv-python")
            return
        if _np is None:
            log.error("numpy no instalado — instala con: pip install numpy")
            return

        self.running = True
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.settimeout(2.0)   # allows stop() to unblock the accept loop
        srv.bind(("0.0.0.0", self.port))
        srv.listen(1)
        self._srv_sock = srv
        log.info("Receptor de cámara esperando en puerto %d …", self.port)

        conn = None
        try:
            # Accept loop with timeout so stop() can interrupt it
            while self.running:
                try:
                    conn, addr = srv.accept()
                    break
                except socket.timeout:
                    continue

            if not self.running or conn is None:
                return

            log.info("Stream de cámara recibido desde %s", addr[0])

            try:
                with _pyvirtualcam.Camera(
                    width=self.width, height=self.height,
                    fps=self.fps, backend='unitycapture',
                ) as cam:
                    log.info("Cámara virtual activa: %s", cam.device)

                    while self.running:
                        raw_len = self._recv_exact(conn, 4)
                        if raw_len is None:
                            break

                        length = struct.unpack('!I', raw_len)[0]
                        if length == 0 or length > 2_000_000:   # 2 MB max per frame
                            log.warning("Frame inválido: %d bytes — cerrando", length)
                            break

                        data = self._recv_exact(conn, length)
                        if data is None:
                            break

                        arr   = _np.frombuffer(data, dtype=_np.uint8)
                        frame = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
                        if frame is None:
                            continue

                        # Resize if the sender's resolution differs
                        h, w = frame.shape[:2]
                        if w != self.width or h != self.height:
                            frame = _cv2.resize(frame, (self.width, self.height))

                        # pyvirtualcam expects RGBA
                        frame_rgba = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGBA)
                        cam.send(frame_rgba)
                        cam.sleep_until_next_frame()

            except Exception as e:
                log.error("Error en cámara virtual: %s — ¿driver Unity Capture instalado?", e)

        except Exception as e:
            log.error("Error en receptor de cámara: %s", e)
        finally:
            if conn:
                try:
                    conn.close()
                except OSError:
                    pass
            try:
                srv.close()
            except OSError:
                pass
            log.info("Receptor de cámara detenido")

    def stop(self):
        self.running = False
        if self._srv_sock:
            try:
                self._srv_sock.close()
            except OSError:
                pass

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> bytes | None:
        buf  = bytearray(n)
        view = memoryview(buf)
        pos  = 0
        try:
            while pos < n:
                received = sock.recv_into(view[pos:], n - pos)
                if not received:
                    return None
                pos += received
        except (ConnectionResetError, ConnectionAbortedError, OSError):
            return None
        return bytes(buf)
