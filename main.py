"""
my-hards launcher — interactive CLI to run as server or client.
"""

import sys
import os

# Ensure the package directory is in the path
sys.path.insert(0, os.path.dirname(__file__))


def main():
    print("=" * 50)
    print("  my-hards — Share keyboard & mouse between PCs")
    print("=" * 50)
    print()
    print("  1) Server  (PC with the keyboard/mouse)")
    print("  2) Client  (PC that receives input)")
    print("  3) Generate default config")
    print()

    choice = input("Select mode [1/2/3]: ").strip()

    if choice == "1":
        from server import main as server_main
        server_main()

    elif choice == "2":
        ip = input("Server IP address: ").strip()
        if not ip:
            print("Error: IP address required")
            sys.exit(1)
        sys.argv = ["client.py", ip]
        from client import main as client_main
        client_main()

    elif choice == "3":
        from config import save_config, DEFAULT_CONFIG
        save_config(DEFAULT_CONFIG)
        print("Default config saved to config.json")
        print("Edit it to customize port, switch edge, etc.")

    else:
        print("Invalid option")
        sys.exit(1)


if __name__ == "__main__":
    main()
