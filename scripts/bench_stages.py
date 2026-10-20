"""Measure where the per-query time actually goes."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldnote.config import settings  # noqa: E402
from fieldnote.encode.registry import get_cross_encoder, get_image_encoder, get_audio_encoder  # noqa: E402


def timeit(label: str, fn):
    t0 = time.perf_counter()
    out = fn()
    dt = (time.perf_counter() - t0) * 1000
    print(f"  {label}: {dt:8.0f} ms")
    return out


def main() -> int:
    q = "What is the high-pressure cutout pressure labeled on the R-410A pressure-temperature curve?"

    print("model load + first inference")
    ce = timeit("load cross encoder", get_cross_encoder)
    img = timeit("load clip", get_image_encoder)
    aud = timeit("load clap", get_audio_encoder)

    print("\nquery encoding (warm)")
    timeit("clip text query", lambda: img.encode_query(q))
    timeit("clap text query", lambda: aud.encode_query(q))

    print("\ncross encoder throughput")
    long_text = ("Trane Precedent YSC072 Service Manual page 11 chart. Figure 14. R-410A "
                 "pressure-temperature curve with safety cutouts. " + ("R-410APRESSURE-TEMPERATURECURVE " * 12))
    for n, length in ((32, 200), (64, 200), (32, 400), (64, 400)):
        pairs = [(q, long_text[:length]) for _ in range(n)]
        t0 = time.perf_counter()
        ce.predict(pairs, batch_size=16, show_progress_bar=False)
        dt = (time.perf_counter() - t0) * 1000
        print(f"  {n:>3} pairs @ {length:>3} chars: {dt:8.0f} ms  ({dt / n:.1f} ms/pair)")

    print("\nimage encode")
    paths = [str(p) for p in sorted(Path("data/artifacts/pages").rglob("*.png"))][:8]
    timeit(f"encode {len(paths)} images", lambda: img.encode(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
