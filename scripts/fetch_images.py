"""Download a curated set of context photographs from Wikimedia Commons.

These are the pictures that appear in the README. They are openly licensed and
the attribution is recorded in docs/images/CREDITS.md, so the repository stays
honest about where the images came from.

    python scripts/fetch_images.py
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "fieldnote-readme/0.1 (https://github.com/Gunjannnn30/fieldnote)"
OUT = Path(__file__).resolve().parents[1] / "docs" / "images"

# (local filename, Commons file title, caption used in the README)
PHOTOS = [
    (
        "rooftop-hvac.jpg",
        "File:130420-F-ZZ999-101 (15718415681), rooftop HVAC.jpg",
        "Rooftop HVAC units on a commercial building.",
    ),
    (
        "air-handler.jpg",
        "File:Air Handler Unit aanzuiging.JPG",
        "An air handling unit serving part of a large building.",
    ),
    (
        "rooftop-units-brisbane.jpg",
        "File:Air handling units in large commercial building, Brisbane.jpg",
        "Air handling units on the roof of a large commercial building.",
    ),
    (
        "chiller.jpg",
        "File:Air Cooled Liquid Chiller.jpg",
        "An air cooled liquid chiller in a plant room.",
    ),
    (
        "outdoor-unit.jpg",
        "File:2011-11-06 AC unit at Duke East.jpg",
        "An outdoor condensing unit.",
    ),
]


def api(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch(title: str, width: int) -> dict | None:
    data = api(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size",
            "iiurlwidth": width,
        }
    )
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        if "missing" in page:
            return None
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        return {
            "url": info.get("thumburl") or info.get("url"),
            "descurl": info.get("descriptionurl"),
            "license": (meta.get("LicenseShortName") or {}).get("value", ""),
            "license_url": (meta.get("LicenseUrl") or {}).get("value", ""),
            "artist": re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip(),
        }
    return None


def download(url: str, dest: Path) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
    except Exception as exc:  # noqa: BLE001
        print(f"    download failed: {exc}")
        return False
    if len(data) < 20_000:
        print("    file too small, skipping")
        return False
    dest.write_bytes(data)
    return True


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    credits: list[dict] = []

    for filename, title, caption in PHOTOS:
        print(f"  {filename}")
        info = fetch(title, 1600)
        if not info or not info["url"]:
            print("    not found")
            continue
        if download(info["url"], OUT / filename):
            print(f"    ok <- {title[:60]}")
            credits.append({"file": filename, "caption": caption, **info})
        else:
            print("    failed")

    lines = [
        "# Image credits",
        "",
        "The photographs in the README come from Wikimedia Commons and are used",
        "under the licences listed below. Each file is the full-resolution",
        "original as hosted by Commons; the README references them by the local",
        "name in this folder.",
        "",
    ]
    for c in credits:
        artist = c["artist"] or "Unknown"
        lines += [
            f"## `{c['file']}`",
            "",
            f"{c['caption']}",
            "",
            f"- Author: {artist}",
            f"- Licence: {c['license']}"
            + (f" ({c['license_url']})" if c.get("license_url") else ""),
            f"- Source: {c['descurl']}",
            "",
        ]
    (OUT / "CREDITS.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "CREDITS.json").write_text(json.dumps(credits, indent=2), encoding="utf-8")
    print(f"\n{len(credits)}/{len(PHOTOS)} images, credits in {OUT / 'CREDITS.md'}")
    return 0 if len(credits) == len(PHOTOS) else 1


if __name__ == "__main__":
    sys.exit(main())
