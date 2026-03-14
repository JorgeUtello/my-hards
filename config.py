"""
Configuration for my-hards.
"""

import json
import os

DEFAULT_PORT = 24800
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "port": DEFAULT_PORT,
    "switch_edge": "right",      # Edge where cursor exits: left, right, top, bottom
    "switch_margin": 2,          # Pixels from edge to trigger switch
    "client_screen_width": 1920,
    "client_screen_height": 1080,
    "clipboard_sync": True,
    "heartbeat_interval": 5,
}


def load_config() -> dict:
    """Load config from file, falling back to defaults."""
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            config.update(user_config)
    return config


def save_config(config: dict):
    """Save config to file."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
