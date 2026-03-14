"""
Configuration for my-hards.
"""

import json
import os
import secrets

DEFAULT_PORT = 24800
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
CERT_FILE = os.path.join(os.path.dirname(__file__), "cert.pem")
KEY_FILE = os.path.join(os.path.dirname(__file__), "key.pem")

DEFAULT_CONFIG = {
    "port": DEFAULT_PORT,
    "switch_edge": "right",      # Edge where cursor exits: left, right, top, bottom
    "switch_margin": 2,          # Pixels from edge to trigger switch
    "client_screen_width": 1920,
    "client_screen_height": 1080,
    "client_pointer_speed": 1.0,
    "clipboard_sync": True,
    "heartbeat_interval": 5,
    "switch_hotkey": "<ctrl>+<alt>+s",  # Hotkey to manually switch PC
    "shared_secret": "",                # HMAC auth token (auto-generated if empty)
    "last_server_ip": "",               # Last used server IP (auto-saved)
}


def load_config() -> dict:
    """Load config from file, falling back to defaults."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            config.update(user_config)
    # Auto-generate shared secret if empty
    if not config.get("shared_secret"):
        config["shared_secret"] = secrets.token_urlsafe(24)
        save_config(config)
    return config


def save_config(config: dict):
    """Save config to file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
