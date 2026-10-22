"""Follow the stable Pages link with headless Chrome and report where it lands."""

from __future__ import annotations

import subprocess
import sys
import tempfile

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://gunjannnn30.github.io/fieldnote/"
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.run(
            [
                CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=20000",
                "--dump-dom",
                url,
            ],
            capture_output=True, text=True, timeout=240,
        )
    dom = proc.stdout or ""
    markers = {
        "the Fieldnote app": "Find the answer in the",
        "the redirect page": "Opening Fieldnote",
        "the live service": "trycloudflare.com",
    }
    for label, needle in markers.items():
        if needle in dom:
            print(f"landed on {label}  (marker: {needle!r})")
    if "Fieldnote" not in dom:
        print("unexpected page; first 400 chars:")
        print(dom[:400])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
