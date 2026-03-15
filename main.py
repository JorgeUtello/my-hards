"""Application launcher for the Electron desktop app."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _electron_command() -> tuple[list[str], str] | None:
    """Return the Electron launch command plus working directory, if available."""
    electron_dir = ROOT / "electron"
    if sys.platform == "win32":
        candidates = [
            electron_dir / "node_modules" / ".bin" / "electron.cmd",
            electron_dir / "node_modules" / "electron" / "dist" / "electron.exe",
        ]
    else:
        candidates = [
            electron_dir / "node_modules" / ".bin" / "electron",
            electron_dir / "node_modules" / "electron" / "dist" / "electron",
        ]

    for candidate in candidates:
        if candidate.exists():
            return [str(candidate), "."], str(electron_dir)
    return None


def main() -> int:
    electron = _electron_command()
    if electron is not None:
        cmd, cwd = electron
        completed = subprocess.run(cmd, cwd=cwd, check=False)
        return completed.returncode
    print(
        "Electron no esta instalado localmente. Ejecuta 'cd electron && npm install' primero.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
