"""Entry point — launches the GUI.

    uv run main.py
"""

import sys
from pathlib import Path


def main() -> None:
    src = Path(__file__).resolve().parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    from intervalssync.gui.app import main as gui_main

    gui_main()


if __name__ == "__main__":
    main()
