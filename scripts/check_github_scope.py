"""What can the stored GitHub credential actually do?"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish import credential  # noqa: E402

REPO = "Gunjannnn30/fieldnote"


def call(token: str, url: str, method: str = "GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("User-Agent", "fieldnote")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            return exc.code, {"raw": raw[:200].decode("utf-8", "replace")}


def main() -> int:
    _user, token = credential()
    checks = [
        ("repo", f"https://api.github.com/repos/{REPO}", "GET", None),
        ("gists", "https://api.github.com/gists", "GET", None),
        ("pages", f"https://api.github.com/repos/{REPO}/pages", "GET", None),
        ("contents", f"https://api.github.com/repos/{REPO}/contents", "GET", None),
    ]
    for name, url, method, body in checks:
        status, payload = call(token, url, method, body)
        if isinstance(payload, list):
            detail = f"{len(payload)} item(s)"
        else:
            detail = payload.get("html_url") or payload.get("message") or ""
        print(f"{name:<10} -> {status}  {str(detail)[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
