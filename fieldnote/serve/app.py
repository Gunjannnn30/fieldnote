"""HTTP API.

The endpoint shape matters more than usual here: the answer a technician gets
on a roof is only trustworthy if it comes back with the picture it came from.
So the response carries the crop, the page number and the rectangle, not just
a string.
"""

from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..schema import Answer


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question to answer.")
    k: int = Field(default=settings.final_k, ge=1, le=100)
    modality: str | None = Field(
        default=None,
        description="Restrict retrieval to one modality: text, image or audio.",
    )
    include_crops: bool = Field(
        default=True, description="Base64-encode the cited crop images in the response."
    )


class CitationPayload(BaseModel):
    chunk_id: str
    modality: str
    source_id: str
    doc_title: str
    page: int | None
    region: str | None
    snippet: str
    score: float
    crop_path: str | None
    page_image_path: str | None
    bbox: dict[str, float] | None
    audio_path: str | None
    start_sec: float | None
    end_sec: float | None
    crop_b64: str | None = None


class AskResponse(BaseModel):
    question: str
    answer: str
    explanation: str = ""
    headline: str = ""
    glossary: list[dict[str, str]] = Field(default_factory=list)
    answerable: bool
    citations: list[CitationPayload]
    modality_hits: dict[str, int]
    latency_ms: float
    stage_ms: dict[str, float]
    trace: dict[str, Any] = Field(default_factory=dict)


def _encode_image(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    mime = mimetypes.guess_type(str(p))[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def _to_payload(answer: Answer, include_crops: bool) -> list[CitationPayload]:
    out: list[CitationPayload] = []
    for cit in answer.citations:
        out.append(
            CitationPayload(
                chunk_id=cit.chunk_id,
                modality=cit.modality.value,
                source_id=cit.source_id,
                doc_title=cit.doc_title,
                page=cit.page,
                region=cit.region_label,
                snippet=cit.snippet[:300],
                score=round(cit.score, 4),
                crop_path=cit.crop_path,
                page_image_path=cit.page_image_path,
                bbox=cit.bbox.to_dict() if cit.bbox else None,
                audio_path=cit.audio_path,
                start_sec=cit.start_sec,
                end_sec=cit.end_sec,
                crop_b64=_encode_image(cit.crop_path) if include_crops else None,
            )
        )
    return out


def create_app(backend: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Fieldnote",
        version="0.1.0",
        description=(
            "Multimodal retrieval for HVAC field service. Text, images and audio "
            "in one index; answers come back with the page and the crop."
        ),
    )
    state: dict[str, Any] = {"system": None}

    def _system():
        if state["system"] is None:
            from ..eval.runner import build_fieldnote_system
            from ..ingest import read_manifest

            manifest = settings.artifacts_dir / "manifest.jsonl"
            if not manifest.exists():
                raise HTTPException(
                    status_code=503,
                    detail="No index. Run `fieldnote ingest` and `fieldnote index` first.",
                )
            chunks = read_manifest(manifest)
            state["system"] = build_fieldnote_system(
                chunks,
                backend=backend or settings.store_backend,
                db_path=str(settings.index_dir / "fieldnote.db"),
            )
        return state["system"]

    @app.get("/health")
    def health() -> dict[str, Any]:
        manifest = settings.artifacts_dir / "manifest.jsonl"
        index = settings.index_dir / "fieldnote.db"
        return {
            "status": "ok",
            "ready": manifest.exists() and index.exists(),
            "loaded": state["system"] is not None,
            "corpus": manifest.exists(),
            "index": index.exists(),
        }

    @app.get("/", include_in_schema=False)
    def index() -> Any:
        """The browser UI."""
        from fastapi.responses import HTMLResponse

        page = Path(__file__).parent / "static" / "index.html"
        if not page.exists():
            raise HTTPException(status_code=404, detail="UI not installed")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        system = _system()
        modalities = [req.modality] if req.modality else None
        t0 = time.perf_counter()
        result = system.retriever.search(req.question, k=req.k, modalities=modalities)
        answer = system.synthesizer.synthesize(
            req.question, result.candidates, latency=result.timings, units=result.units
        )
        elapsed = (time.perf_counter() - t0) * 1000

        trace = answer.trace.to_dict()
        trace["spaces"] = result.space_counts()
        trace["fused"] = sum(len(v) for v in result.per_space.values())
        trace["shortlist"] = result.shortlist_size
        trace["units"] = len(result.units)
        trace["stage_ms"] = {k: round(v, 1) for k, v in result.timings.items()}

        return AskResponse(
            question=req.question,
            answer=answer.answer,
            explanation=answer.explanation,
            headline=answer.headline,
            glossary=[{"term": t, "meaning": m} for t, m in answer.glossary],
            answerable=answer.answerable,
            citations=_to_payload(answer, req.include_crops),
            modality_hits=answer.modality_hits,
            latency_ms=round(elapsed, 1),
            stage_ms={k: round(v, 1) for k, v in result.timings.items()},
            trace=trace,
        )

    @app.get("/evidence/{chunk_id}")
    def evidence(chunk_id: str) -> JSONResponse:
        """The raw evidence for a chunk - useful when a citation looks wrong."""
        from ..ingest import read_manifest

        manifest = settings.artifacts_dir / "manifest.jsonl"
        if not manifest.exists():
            raise HTTPException(status_code=503, detail="No manifest.")
        for chunk in read_manifest(manifest):
            if chunk.chunk_id == chunk_id:
                payload = chunk.to_dict()
                payload["crop_b64"] = _encode_image(chunk.crop_path)
                return JSONResponse(payload)
        raise HTTPException(status_code=404, detail=f"no chunk {chunk_id}")

    @app.get("/page/{chunk_id}")
    def page(chunk_id: str) -> Any:
        """The full manual page, with the cited region outlined.

        This is the view that settles a disagreement: the technician sees the
        whole page and exactly where on it the number was read from.
        """
        from fastapi.responses import Response

        from ..ingest import read_manifest

        manifest = settings.artifacts_dir / "manifest.jsonl"
        if not manifest.exists():
            raise HTTPException(status_code=503, detail="No manifest.")
        for chunk in read_manifest(manifest):
            if chunk.chunk_id != chunk_id:
                continue
            if not chunk.page_image_path or not Path(chunk.page_image_path).exists():
                raise HTTPException(status_code=404, detail="no page image for this chunk")
            image = _highlight_page(chunk)
            if image is None:
                raise HTTPException(status_code=404, detail="page image could not be read")
            import io

            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return Response(buffer.getvalue(), media_type="image/png")
        raise HTTPException(status_code=404, detail=f"no chunk {chunk_id}")

    return app


def _highlight_page(chunk) -> Any:
    """Draw the cited rectangle on the full page render."""
    from PIL import Image, ImageDraw

    try:
        image = Image.open(chunk.page_image_path).convert("RGB")
    except Exception:  # noqa: BLE001
        return None
    if not chunk.bbox:
        return image
    draw = ImageDraw.Draw(image)
    x0, y0, x1, y1 = chunk.bbox.as_tuple()
    pad = 6
    draw.rectangle(
        [max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad)],
        outline=(255, 196, 0),
        width=5,
    )
    draw.rectangle(
        [max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad)],
        outline=(40, 30, 0),
        width=1,
    )
    return image


app = create_app()
