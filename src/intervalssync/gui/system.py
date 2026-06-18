"""Small OS integration helpers for the desktop GUI."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def open_folder(path: str | Path) -> None:
    """Open `path` in the OS file manager, creating it first if needed."""
    folder = Path(path)
    folder.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        os.startfile(folder)  # type: ignore[attr-defined]  # Windows-only
    elif sys.platform == "darwin":
        subprocess.run(["open", str(folder)], check=False)
    else:
        subprocess.run(["xdg-open", str(folder)], check=False)
