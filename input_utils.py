"""
Input utilities: capture and replay keyboard/mouse events cross-platform.
"""

import ctypes
import sys
import threading


def get_screen_size() -> tuple[int, int]:
    """Return (width, height) of the primary monitor."""
    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    else:
        # Linux/X11 fallback
        try:
            import subprocess
            output = subprocess.check_output(
                ["xdpyinfo"], stderr=subprocess.DEVNULL
            ).decode()
            for line in output.split("\n"):
                if "dimensions:" in line:
                    dim = line.split()[1]
                    w, h = dim.split("x")
                    return int(w), int(h)
        except Exception:
            pass
        return 1920, 1080


def lock_cursor_to_edge(edge: str, screen_w: int, screen_h: int):
    """Move the cursor to the edge of the screen (used when switching to client)."""
    from pynput.mouse import Controller
    mouse = Controller()
    if edge == "right":
        mouse.position = (screen_w - 1, screen_h // 2)
    elif edge == "left":
        mouse.position = (0, screen_h // 2)
    elif edge == "top":
        mouse.position = (screen_w // 2, 0)
    elif edge == "bottom":
        mouse.position = (screen_w // 2, screen_h - 1)


def is_at_edge(x: int, y: int, edge: str, screen_w: int, screen_h: int, margin: int = 2) -> bool:
    """Check if cursor position is at the specified screen edge."""
    if edge == "right":
        return x >= screen_w - margin
    elif edge == "left":
        return x <= margin
    elif edge == "top":
        return y <= margin
    elif edge == "bottom":
        return y >= screen_h - margin
    return False


def opposite_edge(edge: str) -> str:
    """Return the opposite edge."""
    return {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}[edge]
