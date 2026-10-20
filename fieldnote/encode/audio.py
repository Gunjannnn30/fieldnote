"""Audio encoder: CLAP audio tower, plus its paired text tower.

Audio is *not* pushed through a caption-and-embed pipeline. CLAP embeds the
waveform itself, so acoustic characteristics (a technician's tone, the sound of
a compressor short-cycling) are part of the index. The Whisper transcript is
kept as a *separate* text view of the same span, which is what makes a
"support call" searchable by words while the audio index stays genuinely
acoustic.
"""

from __future__ import annotations

import numpy as np
import torch

from ..audio_util import read_wav, resample, slice_window
from ..config import settings

CLAP_SR = 48000
CLAP_WINDOW_SEC = 10.0


class AudioEncoder:
    """CLAP joint space: 512-d, shared by the audio tower and the text tower."""

    name = "clap"
    modality = "audio"

    def __init__(self, model_name: str | None = None, device: str | None = None):
        self.model_name = model_name or settings.clap_model
        self.device = device or settings.device

        from transformers import ClapModel, ClapProcessor

        self.processor = ClapProcessor.from_pretrained(self.model_name)
        self.model = ClapModel.from_pretrained(self.model_name).to(self.device).eval()
        self.dim = int(self.model.config.projection_dim)

    # --- audio ------------------------------------------------------------
    def encode(
        self, items: list[tuple[str, float | None, float | None]]
    ) -> np.ndarray:
        """Encode (path, start_sec, end_sec) triples."""
        if not items:
            return np.zeros((0, self.dim), dtype=np.float32)
        out: list[np.ndarray] = []
        for path, start, end in items:
            samples, sr = read_wav(path)
            samples = resample(samples, sr, CLAP_SR)
            window = slice_window(samples, CLAP_SR, start, end, CLAP_WINDOW_SEC)
            inputs = self._process_audio(window)
            with torch.inference_mode():
                feats = self.model.get_audio_features(
                    input_features=inputs["input_features"].to(self.device)
                )
            out.append(self._norm(_as_tensor(feats)))
        return np.concatenate(out, axis=0)

    def _process_audio(self, window: np.ndarray) -> dict:
        """CLAP's processor renamed `audios` to `audio` in transformers 5.

        The feature extractor wants a plain numpy waveform - handing it a
        torch tensor makes it try to tile the array into gigabytes.
        """
        waveform = np.asarray(window, dtype=np.float32)
        try:
            inputs = self.processor(
                audio=waveform, sampling_rate=CLAP_SR, return_tensors="pt"
            )
        except (TypeError, ValueError):
            inputs = self.processor(
                audios=waveform, sampling_rate=CLAP_SR, return_tensors="pt"
            )
        return dict(inputs)

    # --- query side -------------------------------------------------------
    def encode_query(self, query: str) -> np.ndarray:
        """Embed a text query into the CLAP joint space via CLAP's text tower.

        CLAP's text tower is trained on caption-like phrases, so we strip the
        interrogative scaffolding for the same reason the CLIP branch does.
        """
        text = _strip_to_caption_style(query)
        try:
            inputs = self.processor(text=[text], return_tensors="pt", padding=True)
        except (TypeError, ValueError):
            inputs = self.processor(texts=[text], return_tensors="pt", padding=True)
        with torch.inference_mode():
            feats = self.model.get_text_features(
                input_ids=inputs.input_ids.to(self.device),
                attention_mask=inputs.attention_mask.to(self.device),
            )
        return self._norm(_as_tensor(feats))[0]

    @staticmethod
    def _norm(feats: torch.Tensor) -> np.ndarray:
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True).clamp_min(1e-8)
        return feats.detach().cpu().numpy().astype(np.float32)


def _as_tensor(out) -> torch.Tensor:
    """transformers >=5 returns a ModelOutput from get_*_features, not a tensor."""
    import torch

    if isinstance(out, torch.Tensor):
        return out
    for attr in ("audio_embeds", "text_embeds", "pooler_output", "last_hidden_state"):
        value = getattr(out, attr, None)
        if isinstance(value, torch.Tensor):
            return value
    if isinstance(out, dict):
        for attr in ("audio_embeds", "text_embeds", "pooler_output", "last_hidden_state"):
            value = out.get(attr)
            if isinstance(value, torch.Tensor):
                return value
    if isinstance(out, (tuple, list)):
        return out[0]
    raise TypeError(f"cannot pull a tensor out of {type(out)!r}")


_PREFIXES = (
    "why does", "why is", "why do", "what is", "what's", "what are",
    "how do", "how does", "how much", "when does", "when should", "which",
    "can you tell me", "tell me", "please",
)


def _strip_to_caption_style(query: str) -> str:
    q = " ".join(query.lower().split())
    for prefix in _PREFIXES:
        if q.startswith(prefix):
            q = q[len(prefix) :].strip()
            break
    q = q.rstrip("?.! ")
    return q or query.lower()
