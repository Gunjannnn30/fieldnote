"""Publish the live address somewhere that does not change.

A ``trycloudflare`` quick tunnel gets a random subdomain, and it changes every
time the tunnel restarts. That is fine for a service and useless for a link
you put in a README or send to somebody.

The fix is a two-part arrangement:

* a **gist** holds the current address. The publisher rewrites it whenever the
  tunnel restarts. Gists are instant - no build, no deploy.
* a **GitHub Pages** site reads that gist and redirects to it. The Pages
  address is fixed for as long as the repository exists.

So the shareable link is ``https://gunjannnn30.github.io/fieldnote/`` and it
always lands on the running service, whatever the tunnel is called today.

    python scripts/publish_url.py https://example.trycloudflare.com
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

OWNER = os.environ.get("FIELDNOTE_GH_OWNER", "Gunjannnn30")
REPO = os.environ.get("FIELDNOTE_GH_REPO", "fieldnote")
GIST_NAME = "fieldnote-live-url"
PAGES_BRANCH = "gh-pages"

REDIRECTOR = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fieldnote - opening...</title>
<style>
  body { margin:0; height:100vh; display:grid; place-items:center;
         background:#0d1117; color:#e8eef5;
         font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
  .box { text-align:center; max-width:34rem; padding:24px; }
  h1 { font-size:20px; margin:0 0 10px; font-weight:640; }
  p { color:#9aa7b4; margin:0 0 16px; font-size:14px; }
  a { color:#4aa8ff; }
  .dot { display:inline-block; width:10px; height:10px; border-radius:50%;
         border:2px solid #262f3a; border-top-color:#4aa8ff;
         animation:s .8s linear infinite; vertical-align:-1px; }
  @keyframes s { to { transform: rotate(360deg); } }
  #direct { margin-top:14px; font-size:13px; }
  code { font-family:ui-monospace,Menlo,Consolas,monospace; color:#4aa8ff; }
</style>
</head>
<body>
<div class="box">
  <h1>Opening Fieldnote...</h1>
  <p><span class="dot"></span> Taking you to the live service.</p>
  <p id="direct"></p>
</div>
<script>
// The current address lives in a gist, so it can change without a rebuild.
const SOURCES = __SOURCES__;

(async () => {
  for (const url of SOURCES) {
    try {
      const res = await fetch(url + "?t=" + Date.now(), { cache: "no-store" });
      if (!res.ok) continue;
      const data = await res.json();
      const target = (data && (data.url || data.live)) || null;
      if (target && /^https:\/\//.test(target)) {
        document.getElementById("direct").innerHTML =
          'Taking you to <code>' + target + '</code> &middot; <a href="' + target + '">open now</a>';
        window.location.replace(target);
        return;
      }
    } catch (e) { /* try the next source */ }
  }
  document.getElementById("direct").innerHTML =
    'The live address is unavailable right now. Please try again in a moment.';
})();
</script>
</body>
</html>
"""


def _token() -> str:
    """The GitHub credential that is already on this machine."""
    if os.environ.get("FIELDNOTE_GH_TOKEN"):
        return os.environ["FIELDNOTE_GH_TOKEN"]
    payload = f"protocol=https\nhost=github.com\nusername={OWNER}\n\n"
    proc = subprocess.run(
        ["git", "credential-manager", "get"],
        input=payload,
        capture_output=True,
        text=True,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    raise SystemExit(
        "no GitHub credential found - run `git credential-manager github login`"
    )


def _api(token: str, path: str, method: str = "GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"https://api.github.com{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "fieldnote")
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw or b"{}")
        except Exception:  # noqa: BLE001
            return exc.code, {"message": raw[:200].decode("utf-8", "replace")}


def find_gist(token: str) -> dict | None:
    status, payload = _api(token, "/gists")
    if status != 200 or not isinstance(payload, list):
        return None
    for gist in payload:
        if gist.get("description") == GIST_NAME:
            return gist
    return None


def ensure_gist(token: str, live_url: str) -> dict:
    """Create or update the gist that holds the current address."""
    body = {
        "description": GIST_NAME,
        "public": True,
        "files": {"live.json": {"content": json.dumps({"url": live_url}, indent=2)}},
    }
    existing = find_gist(token)
    if existing:
        status, payload = _api(token, f"/gists/{existing['id']}", "PATCH", body)
        if status == 200:
            return payload
    status, payload = _api(token, "/gists", "POST", body)
    if status not in (200, 201):
        raise SystemExit(f"could not create the gist: {status} {payload}")
    return payload


def _stable_raw_url(gist: dict) -> str | None:
    """The gist's raw URL *without* the commit SHA.

    GitHub hands out ``/raw/<sha>/live.json``, and the SHA changes every time
    the gist is updated - so a Pages site built against that URL would keep
    pointing at the previous address. The SHA-less form always serves the
    current file.
    """
    files = gist.get("files") or {}
    entry = files.get("live.json") or {}
    raw = entry.get("raw_url")
    if not raw:
        return None
    if "/raw/" in raw:
        head, _, tail = raw.partition("/raw/")
        return f"{head}/raw/{tail.split('/', 1)[1] if '/' in tail else tail}"
    return raw


def _page_sha(token: str) -> str | None:
    status, payload = _api(
        token, f"/repos/{OWNER}/{REPO}/contents/index.html?ref={PAGES_BRANCH}"
    )
    if status == 200 and isinstance(payload, dict):
        return payload.get("sha")
    return None


def _branch_exists(token: str, branch: str) -> bool:
    status, _ = _api(token, f"/repos/{OWNER}/{REPO}/git/ref/heads/{branch}")
    return status == 200


def _ensure_branch(token: str, branch: str) -> bool:
    """Create a branch from the default branch if it is not there yet."""
    if _branch_exists(token, branch):
        return True
    status, ref = _api(token, f"/repos/{OWNER}/{REPO}/git/ref/heads/{branch}")
    if status == 200:
        return True
    status, head = _api(token, f"/repos/{OWNER}/{REPO}/git/ref/heads/main")
    sha = head.get("object", {}).get("sha") if status == 200 else None
    if not sha:
        status, repo = _api(token, f"/repos/{OWNER}/{REPO}")
        sha = repo.get("default_branch")
        if not sha:
            return False
        status, ref = _api(token, f"/repos/{OWNER}/{REPO}/git/ref/heads/{sha}")
        sha = ref.get("object", {}).get("sha") if status == 200 else None
        if not sha:
            return False
    status, payload = _api(
        token,
        f"/repos/{OWNER}/{REPO}/git/refs",
        "POST",
        {"ref": f"refs/heads/{branch}", "sha": sha},
    )
    if status not in (200, 201):
        print(f"  could not create the {branch} branch: {status} {payload.get('message')}")
        return False
    return True


def ensure_pages(token: str, sources: list[str]) -> str | None:
    """Publish the redirector on the gh-pages branch and switch Pages on."""
    if not _ensure_branch(token, PAGES_BRANCH):
        return None

    html = REDIRECTOR.replace("__SOURCES__", json.dumps(sources))
    encoded = base64.b64encode(html.encode()).decode()

    payload = {
        "message": "Publish the Fieldnote live link",
        "content": encoded,
        "branch": PAGES_BRANCH,
    }
    sha = _page_sha(token)
    if sha:
        payload["sha"] = sha

    status, result = _api(
        token, f"/repos/{OWNER}/{REPO}/contents/index.html", "PUT", payload
    )
    if status not in (200, 201):
        print(f"  could not write {PAGES_BRANCH}/index.html: {status} {result.get('message')}")

    status, result = _api(
        token,
        f"/repos/{OWNER}/{REPO}/pages",
        "POST",
        {"source": {"branch": PAGES_BRANCH, "path": "/"}},
    )
    if status in (200, 201):
        return result.get("html_url")
    if status == 409:
        # Already enabled - just rebuild so the new source URL is published.
        _api(token, f"/repos/{OWNER}/{REPO}/pages/builds", "POST", {})
        status, result = _api(token, f"/repos/{OWNER}/{REPO}/pages")
        if status == 200:
            return result.get("html_url")
    print(f"  could not enable Pages: {status} {result.get('message')}")
    return None


def main() -> int:
    live = sys.argv[1] if len(sys.argv) > 1 else ""
    if not live:
        print("usage: publish_url.py <live-url>")
        return 1

    token = _token()

    gist = ensure_gist(token, live)
    raw = _stable_raw_url(gist)
    if not raw:
        print("could not read back the gist")
        return 1
    print(f"gist    : {gist.get('html_url')}")
    print(f"raw     : {raw}")

    pages_url = ensure_pages(token, [raw])
    if pages_url:
        print(f"stable  : {pages_url}")
        out = Path(__file__).resolve().parents[1] / "data" / "artifacts" / "stable_url.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(pages_url, encoding="utf-8")
    else:
        print("Pages could not be enabled - the gist is still updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
