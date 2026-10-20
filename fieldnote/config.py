"""Central configuration. Everything tunable lives here so the runtime is reproducible."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FIELDNOTE_",
        env_file=(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- paths -------------------------------------------------------------
    root: Path = ROOT
    data_dir: Path = ROOT / "data"

    @property
    def corpus_dir(self) -> Path:
        return self.data_dir / "corpus"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"

    # --- models ------------------------------------------------------------
    text_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    image_model: str = "openai/clip-vit-base-patch32"
    clap_model: str = "laion/clap-htsat-unfused"
    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    caption_model: str = "Salesforce/blip-image-captioning-base"
    whisper_model: str = "openai/whisper-tiny.en"
    vlm_model: str = "HuggingFaceTB/SmolVLM-500M-Instruct"

    # --- retrieval ---------------------------------------------------------
    store_backend: Literal["sqlite", "pgvector", "qdrant"] = "sqlite"
    pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/fieldnote"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "fieldnote"

    candidate_k: int = 40          # per-modality candidate depth before fusion
    final_k: int = 20              # candidates handed to the reranker
    fusion: Literal["rrf", "max", "weighted_rrf"] = "rrf"
    rrf_k: int = 60                # RRF smoothing constant
    use_cross_encoder: bool = True
    use_clip_rerank: bool = True

    # --- synthesis ---------------------------------------------------------
    synthesis: Literal["extractive", "vlm"] = "extractive"
    vlm_max_new_tokens: int = 160

    # --- runtime -----------------------------------------------------------
    device: str = "cpu"
    torch_threads: int = 4
    ocr_enabled: bool = True
    seed: int = 7

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.corpus_dir, self.index_dir, self.artifacts_dir):
            p.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
# Thread count is set at import time so every torch consumer inherits it.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

try:
    import torch

    torch.set_num_threads(max(1, settings.torch_threads))
except Exception:  # noqa: BLE001
    pass
