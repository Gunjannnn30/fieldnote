"""Set the repository description, topics and homepage.

    python scripts/publish.py --configure
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from publish import NAME, OWNER, api, credential  # noqa: E402

TOPICS = [
    "multimodal-rag",
    "retrieval",
    "cross-encoder",
    "clip",
    "whisper",
    "ocr",
    "hvac",
    "field-service",
    "late-fusion",
]


def main() -> int:
    _user, token = credential()

    status, payload = api(f"/repos/{OWNER}/{NAME}", token, method="PATCH", body={
        "description": (
            "Multimodal retrieval for HVAC field service: text, images and audio in one "
            "index, with answers that carry the page and the crop they came from."
        ),
        "homepage": f"https://github.com/{OWNER}/{NAME}",
        "has_wiki": False,
        "topics": TOPICS,
    })
    if status not in (200, 201):
        print(f"could not configure the repository: {status} {payload}")
        return 1
    print(f"description set: {payload.get('description')}")
    print(f"topics: {payload.get('topics')}")

    status, payload = api(f"/repos/{OWNER}/{NAME}", token)
    print(f"url    : {payload.get('html_url')}")
    print(f"stars  : {payload.get('stargazers_count')}  forks: {payload.get('forks_count')}")
    print(f"default branch: {payload.get('default_branch')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
