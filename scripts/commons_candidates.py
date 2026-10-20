"""List Wikimedia Commons candidates so the right ones can be chosen.

    python scripts/commons_candidates.py "Category:Air conditioners" 20
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = "fieldnote-readme/0.1 (https://github.com/Gunjannnn30/fieldnote)"


def api(params: dict) -> dict:
    params = {**params, "format": "json"}
    url = API + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    category = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    data = api(
        {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": category,
            "gcmtype": "file",
            "gcmlimit": limit,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|size",
            "iiurlwidth": 1600,
        }
    )
    pages = (data.get("query") or {}).get("pages") or {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        title = page.get("title", "")
        artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", "")).strip()
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        print(f"{title[:78]:<78} {info.get('width', 0):>5}x{info.get('height', 0):<5} {lic[:22]:<22} {artist[:26]}")
    if not pages:
        print("(no files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
