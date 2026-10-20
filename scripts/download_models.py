"""Pre-download every model Fieldnote uses so later runs are CPU-only and offline-ish.

Usage:  python scripts/download_models.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldnote.config import settings  # noqa: E402


def _fetch_safetensors(repo: str) -> None:
    from huggingface_hub import snapshot_download

    for attempt in range(1, 4):
        try:
            path = snapshot_download(repo, allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model"])
            print(f"[ok] {repo} -> {path}", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[retry {attempt}] {repo}: {exc}", flush=True)
            time.sleep(3)
    raise RuntimeError(f"could not download {repo}")


def _fetch_blip(repo: str) -> None:
    from huggingface_hub import snapshot_download

    for attempt in range(1, 4):
        try:
            path = snapshot_download(
                repo, allow_patterns=["*.json", "*.txt", "*.safetensors", "*.model", "*.bin"]
            )
            print(f"[ok] {repo} -> {path}", flush=True)
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[retry {attempt}] {repo}: {exc}", flush=True)
            time.sleep(3)
    raise RuntimeError(f"could not download {repo}")


def main() -> int:
    repos = [
        settings.text_model,
        settings.image_model,
        settings.cross_encoder_model,
        settings.caption_model,
        settings.whisper_model,
        settings.vlm_model,
    ]
    for repo in repos:
        print(f"--- {repo}", flush=True)
        if "blip" in repo.lower():
            _fetch_blip(repo)
        else:
            _fetch_safetensors(repo)
    print("all models cached", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
