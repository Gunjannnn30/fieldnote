"""Tests that need the models, the corpus and the index.

Marked slow. Run with:

    pytest -m slow
"""

from __future__ import annotations

import pytest

from fieldnote.config import settings
from fieldnote.eval.dataset import build_eval_set, picture_only, verify_unanswerable
from fieldnote.eval.metrics import contains_answer
from fieldnote.fixtures.build import check_collisions
from fieldnote.fixtures.spec import FIGURE_FACTS
from fieldnote.ingest import ingest_corpus, read_manifest, summarize
from fieldnote.schema import Modality

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def chunks():
    manifest = settings.artifacts_dir / "manifest.jsonl"
    if manifest.exists():
        existing = read_manifest(manifest)
        if existing:
            return existing
    result = ingest_corpus()
    return result


def test_corpus_has_all_three_modalities(chunks):
    stats = summarize(chunks)
    assert stats["by_modality"]["text"] > 0
    assert stats["by_modality"]["image"] > 0
    assert stats["by_modality"]["audio"] > 0


def test_every_chunk_is_tagged_with_a_modality(chunks):
    for chunk in chunks:
        assert isinstance(chunk.modality, Modality)


def test_no_picture_only_answer_leaks_into_the_text_corpus(chunks):
    leaks = verify_unanswerable(build_eval_set(), chunks)
    assert leaks == [], f"picture-only answers leaked into the text corpus: {leaks}"


def test_the_fixture_collision_check_agrees(chunks):
    assert check_collisions() == []


def test_every_figure_answer_is_readable_off_the_page(chunks):
    region_text = " | ".join(
        c.text or ""
        for c in chunks
        if c.modality is Modality.IMAGE and c.region_label not in ("full_page", "job_photo")
    )
    photo_text = " | ".join(
        c.text or ""
        for c in chunks
        if c.modality is Modality.IMAGE and c.region_label == "job_photo"
    )
    for fig in FIGURE_FACTS:
        pool = photo_text if fig.kind == "photo" else region_text
        assert contains_answer(fig.answer, pool), f"{fig.qid}: {fig.answer!r} is not readable"


def test_the_eval_set_is_the_shape_the_ship_gate_asks_for():
    questions = build_eval_set()
    assert len(questions) == 40
    assert len(picture_only(questions)) == 15
    assert all(q.answer for q in questions)


def test_the_system_answers_a_picture_only_question(chunks):
    from fieldnote.eval.runner import build_fieldnote_system

    system = build_fieldnote_system(chunks, db_path=str(settings.index_dir / "fieldnote.db"))
    question = (
        "What is the high-pressure cutout pressure labeled on the R-410A "
        "pressure-temperature curve?"
    )
    result = system.retriever.search(question, k=settings.final_k)
    answer = system.synthesizer.synthesize(
        question, result.candidates, latency=result.timings, units=result.units
    )
    assert contains_answer("385", answer.answer), answer.answer
    assert any(c.crop_path for c in answer.citations), "no cropped image in the citation"
    assert any(c.page is not None for c in answer.citations), "no page number in the citation"


def test_the_api_returns_the_crop(chunks):
    from fastapi.testclient import TestClient

    from fieldnote.serve.app import create_app

    client = TestClient(create_app(backend="sqlite"))
    response = client.post(
        "/ask",
        json={
            "question": "What model number is stamped on the nameplate in the job site photo?",
            "include_crops": True,
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert contains_answer("NP-42", payload["answer"]), payload["answer"]
    assert any(c["crop_b64"] for c in payload["citations"])
