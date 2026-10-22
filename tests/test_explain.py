"""Tests for the plain-language layer.

The interface is only as good as its ability to explain itself to somebody who
does not work in HVAC, so this is behaviour worth pinning down.
"""

from __future__ import annotations

from fieldnote.answer.explain import explain, find_terms, headline


def test_pressure_question_gets_a_plain_explanation():
    text = explain(
        "What is the high-pressure cutout pressure labeled on the curve?",
        "HP CUTOUT 385 PSI",
    )
    assert "385" in text
    assert "switches itself off" in text
    assert "compressor" in text


def test_voltage_question_is_explained_as_wiring():
    text = explain("What field supply voltage is printed on the diagram?", "240V 3PH 60HZ")
    assert "wired for" in text


def test_model_question_is_explained_as_an_identifier():
    text = explain("What model number is stamped on the nameplate?", "MODEL NP-42")
    assert "NP-42" in text
    assert "parts" in text


def test_fault_code_question_is_explained_as_a_report():
    text = explain("What fault code is displayed on the control board?", "FAULT LP-2")
    assert "LP-2" in text
    assert "control board" in text


def test_an_unrecognised_answer_falls_back_to_the_fragment():
    text = explain("What does the note say?", "The note says to verify the field wiring")
    assert "documentation states" in text
    assert "field wiring" in text


def test_headline_names_the_kind_of_value():
    assert headline("What is the cutout pressure?", "385 PSI").startswith("Pressure")
    assert headline("What model number is it?", "NP-42").startswith("Model")
    assert headline("What is the fault code?", "LP-2").startswith("Fault code")


def test_glossary_finds_the_terms_in_a_sentence():
    terms = dict(find_terms("the economizer opens the damper and the cutout switch trips"))
    assert "economizer" in terms
    assert "cutout" in terms


def test_glossary_does_not_invent_terms():
    assert find_terms("a completely unrelated sentence about cats") == []


def test_glossary_explains_a_term_in_words_a_non_specialist_understands():
    terms = dict(find_terms("check the nameplate on the unit"))
    assert "model" in terms["nameplate"].lower()
