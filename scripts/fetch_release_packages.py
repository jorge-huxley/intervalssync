"""Download official v0.9.1 packages into dist/. Resumable via HTTP Range."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BASES = (
    "https://ghfast.top/https://github.com/jorge-huxley/intervalssync/releases/download/v0.9.1",
    "https://github.com/jorge-huxley/intervalssync/releases/download/v0.9.1",
)
FILES = (
    "intervalssync-v0.9.1-windows.zip",
    "intervalssync-v0.9.1-macos.zip",
    "intervalssync-v0.9.1-android.apk",
)
MIN_BYTES = 1_000_000


def fetch_from(base: str, name: str) -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    url = f"{base}/{name}"
    dest = DIST / name
    partial = dest.with_suffix(dest.suffix + ".part")
    start = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "intervalssync-fetch/1.0"}
    if start:
        headers["Range"] = f"bytes={start}-"
        print(f"resume {name} from {start} via {base}", flush=True)
    else:
        print(f"GET {name} via {base}", flush=True)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp, partial.open("ab") as out:
        while True:
            chunk = resp.read(1024 * 512)
            if not chunk:
                break
            out.write(chunk)
    size = partial.stat().st_size
    if size < MIN_BYTES:
        raise RuntimeError(f"too small: {name} ({size} bytes)")
    partial.replace(dest)
    print(f"OK {name} ({size} bytes)", flush=True)


def fetch(name: str) -> None:
    errors: list[str] = []
    for base in BASES:
        try:
            fetch_from(base, name)
            return
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            errors.append(f"{base}: {exc}")
            print(f"fail {name}: {exc}", flush=True)
    raise SystemExit(f"could not fetch {name}:\n" + "\n".join(errors))


def main() -> int:
    names = sys.argv[1:] or list(FILES)
    for name in names:
        fetch(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
