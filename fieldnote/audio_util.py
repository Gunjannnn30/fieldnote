"""Small WAV helpers built on the standard library + numpy.

We deliberately avoid librosa/soundfile: Fieldnote only needs mono 16 kHz for
Whisper and mono 48 kHz for CLAP, and rolling our own keeps the dependency
list short on an air-gapped field laptop.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    """Return (float32 mono samples in [-1, 1], sample_rate)."""
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width: {sampwidth}")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)
    return data.astype(np.float32), sr


def resample(samples: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Linear-interpolation resampler. Fine for speech at these ratios."""
    if sr_in == sr_out or samples.size == 0:
        return samples.astype(np.float32)
    n_out = int(round(samples.size * (sr_out / sr_in)))
    x_old = np.arange(samples.size, dtype=np.float64)
    x_new = np.linspace(0.0, samples.size - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, samples).astype(np.float32)


def to_mono(samples: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    return resample(samples, sr, target_sr)


def slice_window(
    samples: np.ndarray, sr: int, start_sec: float | None, end_sec: float | None,
    window_sec: float = 10.0,
) -> np.ndarray:
    """Extract a fixed-length window, zero-padded if the segment is short.

    CLAP is trained on 10-second clips, so short audio segments are padded
    rather than stretched.
    """
    n_window = int(window_sec * sr)
    if samples.size == 0:
        return np.zeros(n_window, dtype=np.float32)

    if start_sec is None or end_sec is None:
        chunk = samples[:n_window]
    else:
        a = max(0, int(start_sec * sr))
        b = min(samples.size, int(end_sec * sr))
        chunk = samples[a:b] if b > a else samples[:n_window]

    if chunk.size >= n_window:
        return chunk[:n_window].astype(np.float32)
    padded = np.zeros(n_window, dtype=np.float32)
    padded[: chunk.size] = chunk
    return padded


def write_wav(path: str | Path, samples: np.ndarray, sr: int) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
