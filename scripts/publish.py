"""Create the GitHub repository and push.

Uses the credential that Git Credential Manager already holds for github.com,
so no token has to be pasted anywhere.

    python scripts/publish.py
"""

from __future__ import annotations

import json
import subprocess
import sys

OWNER = "Gunjannnn30"
NAME = "fieldnote"
DESCRIPTION = (
    "Multimodal retrieval for HVAC field service: text, images and audio in one "
    "index, with answers that carry the page and the crop they came from."
)


def credential() -> tuple[str, str]:
    payload = f"protocol=https\nhost=github.com\nusername={OWNER}\n\n"
    proc = subprocess.run(
        ["git", "credential-manager", "get"],
        input=payload,
        capture_output=True,
        text=True,
    )
    user = token = ""
    for line in proc.stdout.splitlines():
        if line.startswith("username="):
            user = line.split("=", 1)[1]
        elif line.startswith("password="):
            token = line.split("=", 1)[1]
    if not token:
        raise SystemExit("no credential for github.com - run `git credential-manager github login`")
    return user, token


def api(path: str, token: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    import urllib.error
    import urllib.request

    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            payload = {"message": raw[:300].decode("utf-8", "replace")}
        return exc.code, payload


def main() -> int:
    user, token = credential()
    print(f"authenticated as {user}")

    status, payload = api(f"/repos/{OWNER}/{NAME}", token)
    if status == 200:
        print(f"repository {OWNER}/{NAME} already exists")
    elif status == 404:
        status, payload = api(
            "/user/repos",
            token,
            method="POST",
            body={
                "name": NAME,
                "description": DESCRIPTION,
                "private": False,
                "auto_init": False,
                "has_issues": True,
                "has_wiki": False,
            },
        )
        if status not in (200, 201):
            print(f"could not create the repository: {status} {payload}")
            return 1
        print(f"created repository {OWNER}/{NAME}")
    else:
        print(f"unexpected response {status}: {payload}")
        return 1

    subprocess.run(["git", "remote", "remove", "origin"], capture_output=True, text=True)
    subprocess.run(
        ["git", "remote", "add", "origin", f"https://github.com/{OWNER}/{NAME}.git"],
        check=True,
    )
    print("remote origin set")

    push = subprocess.run(["git", "push", "-u", "origin", "main"], text=True)
    if push.returncode != 0:
        print("push failed")
        return push.returncode
    print(f"pushed -> https://github.com/{OWNER}/{NAME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
