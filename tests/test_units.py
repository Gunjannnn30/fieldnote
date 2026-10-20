"""Tests for the pieces that must not silently break.

The expensive model-backed tests are marked `slow`; run them with

    pytest -m slow

The fast ones cover the things that would quietly corrupt an answer: the
sentence splitter, the OCR de-mangler, the grader, the fusion, and the
fixture's own honesty checks.
"""

from __future__ import annotations

import numpy as np
import pytest

from fieldnote.answer.units import (
    extract_values,
    is_caption,
    is_which_focus,
    question_focus,
    wants_a_value,
)
from fieldnote.eval.metrics import canonical, contains_answer, grade, latency_stats
from fieldnote.retrieve.fuse import fuse
from fieldnote.schema import BBox, Chunk, Modality, SourceKind
from fieldnote.store.base import IndexedRecord
from fieldnote.textutil import sentences
from fieldnote.vision.demangle import demangle


# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------


def test_sentence_splitter_keeps_units_with_their_value():
    text = "The required filter differential pressure for this unit is 0.5 in. w.c. measured across the bank."
    parts = sentences(text)
    assert len(parts) == 1
    assert "0.5 in. w.c." in parts[0]


def test_sentence_splitter_keeps_fraction_sizes_together():
    parts = sentences("Install a 1/8 in. rated filter drier in the liquid line.")
    assert len(parts) == 1


def test_sentence_splitter_keeps_figure_captions_together():
    parts = sentences("Figure 14. R-410A pressure-temperature curve with safety cutouts.")
    assert len(parts) == 1
    assert parts[0].startswith("Figure 14.")


def test_sentence_splitter_still_splits_real_sentences():
    parts = sentences("The unit trips. The discharge pressure is high. Check the cutout.")
    assert len(parts) == 3


# ---------------------------------------------------------------------------
# OCR de-mangling
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("LPCUTOUT92PSI", "LP CUTOUT 92 PSI"),
        ("PEAK425PSIG", "PEAK 425 PSIG"),
        ("FIELDSUPPLY:240V3PH60HZ", "FIELD SUPPLY 240 V 3 PH 60 HZ"),
        ("MODELNP-42", "MODEL NP-42"),
        ("FAULT LP-2", "FAULT LP-2"),
        ("385.PSI", "385 PSI"),
    ],
)
def test_demangle_splits_run_together_ocr(raw, expected):
    assert demangle(raw) == expected


def test_demangle_leaves_what_it_cannot_explain_alone():
    # Guessing would corrupt the evidence; a wrong split is worse than no split.
    assert demangle("NORTHPOINTMANUFACTURING") == "NORTHPOINTMANUFACTURING"


# ---------------------------------------------------------------------------
# Value extraction
# ---------------------------------------------------------------------------


def test_extract_values_reads_run_together_values():
    assert extract_values("LP CUTOUT 92 PSI") == ["92"]
    assert extract_values("PEAK 425 PSIG") == ["425"]


def test_identifiers_are_not_bare_numbers():
    assert extract_values("MODEL NP-42") == []
    assert extract_values("FAULT LP-2") == []


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def test_grade_matches_a_value_inside_a_sentence():
    result = grade("0.5 in. w.c.", "The required filter differential pressure is 0.5 in. w.c. measured across the bank.")
    assert result.correct


def test_grade_does_not_match_a_number_inside_another_number():
    assert not grade("18", "the unit sees 187 volts").correct
    assert not grade("12", "2400 CFM of airflow").correct


def test_grade_handles_spelled_out_numbers():
    result = grade("97°F", "it was ninety seven degrees outside")
    assert result.correct


def test_grade_matches_run_together_ocr():
    assert grade("240V 3PH 60HZ", "FIELD SUPPLY 240 V 3 PH 60 HZ").correct
    assert grade("NP-42", "MODEL NP-42").correct
    assert grade("LP-2", "FAULT LP-2").correct


def test_grade_fuzzy_for_near_misses():
    result = grade("the nameplate", "I will go photograph the name plate and send it in.")
    assert result.correct


def test_contains_answer_respects_token_boundaries():
    assert not contains_answer("14", "the XC14 condenser")
    assert contains_answer("14", "figure 14 shows the curve")


# ---------------------------------------------------------------------------
# Question focus
# ---------------------------------------------------------------------------


def test_focus_splits_off_the_locator():
    focus = question_focus("What field supply voltage is printed on the YSC072 unit 7 wiring diagram?")
    assert "voltage" in focus.lower()
    assert "wiring diagram" not in focus.lower()


def test_which_focus_is_detected():
    assert is_which_focus("Which roof was the unit on?")
    assert not is_which_focus("What is the control voltage?")


def test_wants_a_value():
    assert wants_a_value("What is the required filter differential pressure?")
    assert wants_a_value("How many filters does the rack accept?")
    assert not wants_a_value("Which roof was the unit on?")
    assert not wants_a_value("What did the support line ask the technician to send back?")


def test_caption_detection():
    assert is_caption("Figure 14. R-410A pressure-temperature curve.")
    assert is_caption("Table 7. Coil capacity data.")
    assert not is_caption("The condensing temperature should run 5F above ambient.")


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def _chunk(chunk_id: str, modality: Modality) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        modality=modality,
        source_id="src",
        source_kind=SourceKind.MANUAL_PAGE,
        doc_title="Manual",
        text="text",
    )


def test_rrf_fusion_prefers_items_ranked_high_in_several_spaces():
    text_hits = [(_rec("t1"), 0.9), (_rec("t2"), 0.8)]
    image_hits = [(_rec("t1"), 0.9), (_rec("i1"), 0.7)]
    result = fuse({"text": text_hits, "image": image_hits})
    assert result.candidates[0].chunk.chunk_id == "t1"


def test_rrf_fusion_is_scale_free():
    # A space with wildly different score magnitudes must not dominate.
    a = fuse({"text": [(_rec("x"), 0.9), (_rec("y"), 0.1)]})
    b = fuse({"text": [(_rec("x"), 90.0), (_rec("y"), 10.0)]})
    assert a.candidates[0].chunk.chunk_id == b.candidates[0].chunk.chunk_id


def _rec(chunk_id: str) -> IndexedRecord:
    return IndexedRecord(
        chunk=_chunk(chunk_id, Modality.TEXT),
        space="text",
        vector=np.zeros(4, dtype=np.float32),
    )


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def test_latency_percentiles():
    stats = latency_stats([100, 200, 300, 400, 5000])
    assert stats.p50 == 300
    assert stats.p95 == 5000
    assert stats.count == 5


def test_latency_of_nothing():
    stats = latency_stats([])
    assert stats.count == 0


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_bbox_area_and_roundtrip():
    box = BBox(0, 0, 10, 5)
    assert box.area == 50
    assert BBox.from_dict(box.to_dict()).area == 50


def test_chunk_roundtrip_keeps_the_modality_tag():
    chunk = _chunk("c1", Modality.AUDIO)
    restored = Chunk.from_dict(chunk.to_dict())
    assert restored.modality is Modality.AUDIO
