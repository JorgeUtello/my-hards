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
    "switch_edge": "right",
    "switch_margin": 2,
    "client_screen_width": 1920,
    "client_screen_height": 1080,
    "client_pointer_speed": 1.0,
    "clipboard_sync": True,
    "heartbeat_interval": 5,
    "switch_hotkey": "<ctrl>+<alt>+s",
    "shared_secret": "",
    "last_server_ip": "",
}

_config_cache: dict | None = None


def load_config() -> dict:
    """Load config from file, falling back to defaults. Cached after first load."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config.update(json.load(f))
    if not config.get("shared_secret"):
        config["shared_secret"] = secrets.token_urlsafe(24)
        save_config(config)
    _config_cache = config
    return config


def save_config(config: dict):
    """Save config to file and update the in-memory cache."""
    global _config_cache
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    _config_cache = dict(config)
