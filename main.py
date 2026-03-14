"""
my-hards — Desktop application for sharing keyboard & mouse between PCs.
Launches the GUI directly.
"""

import sys
import os

# Ensure the package directory is in the path
sys.path.insert(0, os.path.dirname(__file__))


def main():
    from gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
