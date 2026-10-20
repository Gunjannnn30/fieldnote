"""Sanity check: do the encoders put a picture and its description in the same space?

Retrieval across modalities is only meaningful if the image tower and the text
tower of the same model agree. This prints the cosine similarity of matching
and non-matching pairs, so a silent misconfiguration (wrong projection, wrong
normalisation, tokenizer mismatch) shows up as a flat line instead of as bad
accuracy numbers three hours later.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from fieldnote.config import settings  # noqa: E402
from fieldnote.encode.registry import get_audio_encoder, get_image_encoder  # noqa: E402


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _find(pattern: str) -> str:
    matches = sorted(Path("data/artifacts/pages").rglob(pattern))
    if not matches:
        raise SystemExit(f"no file matching {pattern!r}; run the ingester first")
    return str(matches[0])


def image_check() -> None:
    enc = get_image_encoder()
    chart = _find("*chart.png")
    wiring = _find("*wiring_diagram.png")
    nameplate = "data/corpus/photos/job_photo_unit_7_nameplate.png"
    print(f"chart    -> {chart}")
    print(f"wiring   -> {wiring}")

    imgs = enc.encode([chart, wiring, nameplate])
    texts = enc.encode_texts(
        [
            "a pressure temperature curve with a cutout point",
            "an electrical wiring diagram with terminals",
            "a nameplate with a model number sticker",
            "a plate of spaghetti with tomato sauce",
        ]
    )
    print("\nCLIP image tower vs text tower (cosine):")
    print("               " + "".join(f"  t{i}      " for i in range(len(texts))))
    for i, name in enumerate(["chart   ", "wiring  ", "nameplate"]):
        row = "".join(f"  {_cos(imgs[i], texts[j]):.3f}  " for j in range(len(texts)))
        print(f"  {name}  {row}")


def audio_check() -> None:
    enc = get_audio_encoder()
    call = "data/corpus/calls/call_unit7_hp_trip.wav"
    items = [(call, 0.0, 6.0), (call, 45.0, 52.0), (call, 24.0, 30.0)]
    audio = enc.encode(items)
    texts = enc.encode_query.__self__  # keep the encoder alive
    from fieldnote.encode.audio import AudioEncoder

    enc_text = enc.model.get_text_features
    import torch

    captions = [
        "a technician on the phone about a rooftop unit",
        "someone asking for a nameplate photograph",
        "a recording of wind and birds",
    ]
    feats = []
    for cap in captions:
        inputs = enc.processor(text=[cap], return_tensors="pt", padding=True)
        with torch.inference_mode():
            out = enc_text(
                input_ids=inputs.input_ids, attention_mask=inputs.attention_mask
            )
        feats.append(_as(out))
    print("\nCLAP audio tower vs text tower (cosine):")
    print("                 " + "".join(f"  t{i}      " for i in range(len(captions))))
    for i, name in enumerate(["seg0 call", "seg1 call", "seg2 call"]):
        row = "".join(f"  {_cos(audio[i], feats[j]):.3f}  " for j in range(len(captions)))
        print(f"  {name}  {row}")
    del texts


def _as(out) -> np.ndarray:
    import torch

    if isinstance(out, torch.Tensor):
        t = out
    else:
        t = None
        for attr in ("text_embeds", "pooler_output", "last_hidden_state"):
            value = getattr(out, attr, None)
            if isinstance(value, torch.Tensor):
                t = value
                break
    t = t / t.norm(p=2, dim=-1, keepdim=True).clamp_min(1e-8)
    return t.detach().cpu().numpy().astype(np.float32).reshape(-1)


if __name__ == "__main__":
    print(f"device={settings.device} image_model={settings.image_model} clap={settings.clap_model}")
    image_check()
    audio_check()
