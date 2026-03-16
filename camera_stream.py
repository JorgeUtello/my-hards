"""
Camera streaming (client side): captures the local webcam and streams
JPEG frames over a plain TCP connection to the server's camera port.

No TLS here — frames are not sensitive and TLS overhead hurts latency.
The port is separate from the main control channel.
"""

import socket
import struct
import time
import logging

log = logging.getLogger("camera_stream")

_cv2 = None
try:
    import cv2 as _cv2_import
    _cv2 = _cv2_import
except ImportError:
    pass


class CameraStream:
    def __init__(self, server_ip: str, port: int, fps: int = 15,
                 width: int = 640, height: int = 480):
        self.server_ip = server_ip
        self.port      = port
        self.fps       = fps
        self.width     = width
        self.height    = height
        self.running   = False

    def start(self):
        if _cv2 is None:
            log.error("opencv-python no instalado — instala con: pip install opencv-python")
            return

        self.running = True

        # CAP_DSHOW is faster than CAP_MSMF on Windows for USB webcams
        backend = _cv2.CAP_DSHOW if hasattr(_cv2, 'CAP_DSHOW') else 0
        cap = _cv2.VideoCapture(0, backend)
        cap.set(_cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        cap.set(_cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(_cv2.CAP_PROP_FPS,          self.fps)

        if not cap.isOpened():
            log.error("No se pudo abrir la cámara web (índice 0)")
            self.running = False
            return

        log.info("Cámara web iniciada — %dx%d @ %d fps", self.width, self.height, self.fps)
        frame_interval = 1.0 / self.fps
        quality_params = [_cv2.IMWRITE_JPEG_QUALITY, 70]

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.server_ip, self.port))
            log.info("Stream de cámara conectado a %s:%d", self.server_ip, self.port)

            while self.running:
                t0 = time.monotonic()

                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                ok, buf = _cv2.imencode('.jpg', frame, quality_params)
                if not ok:
                    continue

                data = buf.tobytes()
                try:
                    sock.sendall(struct.pack('!I', len(data)) + data)
                except OSError:
                    log.warning("Conexión de cámara perdida")
                    break

                elapsed   = time.monotonic() - t0
                remaining = frame_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)

        except Exception as e:
            log.error("Error en stream de cámara: %s", e)
        finally:
            cap.release()
            try:
                sock.close()
            except OSError:
                pass
            log.info("Stream de cámara detenido")

    def stop(self):
        self.running = False
