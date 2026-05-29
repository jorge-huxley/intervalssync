"""Entry shim.

    uv run main.py          # launch the GUI
    uv run main.py --cli    # run the headless sync (original behavior)
"""

import sys


def _ensure_src_on_path() -> None:
    from pathlib import Path

    src = Path(__file__).resolve().parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()

    if "--cli" in sys.argv[1:]:
        from igpsync.cli import main as cli_main

        return cli_main()

    from igpsync.gui.app import main as gui_main

    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
