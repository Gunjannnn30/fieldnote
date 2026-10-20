"""Support-call audio ingestion.

Whisper transcribes the call into timestamped segments. Each segment becomes
an AUDIO chunk - tagged as audio, embedded acoustically by CLAP, and cited with
a time span so a technician can scrub to the exact second of the call.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path

from ..audio_util import read_wav, resample
from ..config import settings
from ..schema import Chunk, Modality, SourceKind

WHISPER_SR = 16000
WINDOW_SEC = 30.0
STRIDE_SEC = 5.0


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@functools.lru_cache(maxsize=1)
def _whisper():
    import torch
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    proc = WhisperProcessor.from_pretrained(settings.whisper_model)
    model = WhisperForConditionalGeneration.from_pretrained(settings.whisper_model)
    model.to(settings.device).eval()
    del torch
    return proc, model


def transcribe(path: str | Path) -> list[TranscriptSegment]:
    """Transcribe an audio file into timestamped segments.

    Whisper does its own long-form chunking (30 s windows, 5 s stride) when
    handed the whole file, and it returns absolute timestamps. Handing it
    overlapping windows ourselves instead produces the same sentence twice
    with different wording, which then pollutes the index.
    """
    import torch

    proc, model = _whisper()
    samples, sr = read_wav(path)
    samples = resample(samples, sr, WHISPER_SR)
    if samples.size == 0:
        return []

    inputs = proc(
        samples,
        sampling_rate=WHISPER_SR,
        return_tensors="pt",
        truncation=False,
        padding="longest",
        return_attention_mask=True,
    )
    features = inputs.input_features.to(settings.device)

    with torch.inference_mode():
        out = model.generate(
            input_features=features,
            return_timestamps=True,
            return_dict_in_generate=True,
            max_new_tokens=440,
            num_beams=1,
        )

    segments: list[TranscriptSegment] = []
    for seg in _flatten_segments(_get(out, "segments") or []):
        text = (seg.get("text") or "").strip()
        if not text and seg.get("tokens") is not None:
            try:
                text = proc.decode(seg["tokens"], skip_special_tokens=True).strip()
            except Exception:  # noqa: BLE001
                text = ""
        if not text:
            continue
        s = float(seg.get("start", 0.0) or 0.0)
        e = float(seg.get("end", s + 1.0) or s + 1.0)
        segments.append(TranscriptSegment(s, e, text))

    if not segments:
        sequences = _get(out, "sequences")
        if sequences is not None:
            text = proc.batch_decode(sequences, skip_special_tokens=True)[0].strip()
            if text:
                segments.append(TranscriptSegment(0.0, samples.size / WHISPER_SR, text))

    return _merge(segments)


def _flatten_segments(raw) -> list[dict]:
    """Whisper returns segments either flat or nested per window."""
    out: list[dict] = []
    stack = list(raw) if isinstance(raw, list) else [raw]
    while stack:
        item = stack.pop(0)
        if isinstance(item, list):
            stack = list(item) + stack
        elif isinstance(item, dict):
            out.append(item)
    return out


def _get(out, key):
    """Read a field from a generate() output, dict-style or attribute-style."""
    if out is None:
        return None
    if isinstance(out, dict):
        return out.get(key)
    return getattr(out, key, None)


def _merge(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    """Drop empty segments and stitch together ones that genuinely overlap.

    Whisper already breaks the call at natural pauses. Merging merely
    *adjacent* segments would glue a whole call into one chunk and make the
    time span useless as a citation.
    """
    out: list[TranscriptSegment] = []
    for seg in segments:
        text = re.sub(r"\s+", " ", seg.text).strip()
        if not text:
            continue
        if out and seg.start < out[-1].end - 0.05:
            out[-1].text = f"{out[-1].text} {text}".strip()
            out[-1].end = max(out[-1].end, seg.end)
        else:
            out.append(TranscriptSegment(seg.start, seg.end, text))
    return out


def ingest_audio(
    audio_path: str | Path,
    source_id: str,
    doc_title: str,
    out_dir: str | Path,
) -> list[Chunk]:
    audio_path = Path(audio_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    segments = transcribe(audio_path)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", doc_title).strip("-").lower()[:60] or "call"

    chunks: list[Chunk] = []
    for i, seg in enumerate(segments):
        chunks.append(
            Chunk(
                chunk_id=f"{slug}-{source_id}-a{i:03d}",
                modality=Modality.AUDIO,
                source_id=source_id,
                source_kind=SourceKind.CALL_RECORDING,
                doc_title=doc_title,
                text=seg.text,
                page=None,
                audio_path=str(audio_path),
                start_sec=round(seg.start, 2),
                end_sec=round(seg.end, 2),
                region_label="call_segment",
                metadata={"duration": round(seg.end - seg.start, 2), "speaker": "unknown"},
            )
        )
    return chunks


def transcription_text(segments: list[TranscriptSegment]) -> str:
    return " ".join(s.text for s in segments)
