"""Screenshot the UI with headless Chrome so the result can be checked.

    python scripts/shoot.py <url> <out.png> [width] [height]
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/"
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "data/artifacts/ui.png")
    width = sys.argv[3] if len(sys.argv) > 3 else "1280"
    height = sys.argv[4] if len(sys.argv) > 4 else "1400"
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            f"--user-data-dir={profile}",
            f"--window-size={width},{height}",
            "--virtual-time-budget=9000",
            f"--screenshot={out.resolve()}",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if out.exists():
        print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
        return 0
    print("screenshot failed")
    print(proc.stdout[-800:])
    print(proc.stderr[-800:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
