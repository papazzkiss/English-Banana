"""Question-bank generators: every rule that keeps exactly one answer right.

Needs the `content` dependency group (spaCy + model, lemminflect, wordfreq); skipped without it.
"""

from __future__ import annotations

import random

import pytest

spacy = pytest.importorskip("spacy")
pytest.importorskip("lemminflect")

from banana_english.contentbank import grammar_gen as g  # noqa: E402
from banana_english.contentbank.build import (  # noqa: E402
    allocate,
    choice_question,
    near_duplicate_key,
    stable_id,
)
from banana_english.contentbank.lexicon import is_clean, length_level, topic_of  # noqa: E402
from banana_english.contentbank.schema import SourceRef  # noqa: E402
from banana_english.contentbank.templates import FAMILIES, generate  # noqa: E402


@pytest.fixture(scope="module")
def nlp():
    try:
        return spacy.load("en_core_web_sm")
    except OSError:
        pytest.skip("en_core_web_sm not installed")


def items(nlp, text, point=None):
    out = list(g.candidates(nlp(text)))
    return [c for c in out if point is None or c.point == point]


def test_tense_choice_only_with_a_signal_that_rules_out_the_distractors(nlp):
    mcq = [
        c
        for c in items(nlp, "Nancy ran across an old friend of hers yesterday.", "past_simple")
        if c.qtype == "mcq" and "signal:yesterday" in c.tags
    ]
    assert mcq, "a yesterday sentence gives a tense-choice question"
    right, *wrong = mcq[0].options
    assert right == "ran"
    # present perfect is wrong with "yesterday"; the past continuous (could fit) is never offered
    assert "has run" in wrong and not any(w.startswith(("was ", "were ")) for w in wrong)
    typed = [
        c
        for c in items(nlp, "Nancy ran across an old friend of hers yesterday.")
        if c.qtype == "fill_blank"
    ]
    assert typed and "past simple" in typed[0].instruction and typed[0].accepted == ["ran"]


def test_form_questions_keep_one_grammatical_option(nlp):
    form = [
        c
        for c in items(nlp, "Many immigrants to Britain have come from Asia.", "present_perfect")
        if "form" in c.tags
    ][0]
    assert form.options[0] == "have come"
    assert set(form.options[1:]) == {"has come", "have came", "have coming"}


def test_risky_verbs_are_left_out(nlp):
    # got/gotten are both right; put/did put/has put are all grammatical; fill is ergative
    assert not [
        c for c in items(nlp, "Miss Brown has gotten used to Japanese food.") if "form" in c.tags
    ]
    assert not [
        c
        for c in items(nlp, "She put it in the box.")
        if c.point == "past_simple" and c.qtype != "fill_blank"
    ]
    assert not items(nlp, "The hall was filled with students.", "passive")
    assert items(nlp, "The party was held on May 22.", "passive")


def test_collective_subjects_get_no_agreement_questions(nlp):
    assert not [
        c for c in items(nlp, "The firm has bought some new cars.") if c.qtype == "error_id"
    ]
    assert [
        c for c in items(nlp, "The twins have come down with measles.") if c.qtype == "error_id"
    ]


def test_articles_follow_the_sound(nlp):
    an = items(nlp, "We waited for an hour at the station.", "articles")[0]
    assert an.options == ["an", "a"] and "sound" in an.explanation
    a = items(nlp, "She studies at a university in Hanoi.", "articles")[0]
    assert a.options == ["a", "an"]


def test_contrast_linker_distractors_cannot_fit(nlp):
    c = items(nlp, "Although it was raining, we went for a walk.", "contrast_linkers")[0]
    assert c.options == ["although", "despite", "in spite of", "because of"]  # no clause after


def test_ordering_is_a_real_shuffle_with_contractions_kept(nlp):
    c = items(nlp, "It's a good deal.", "word_order")[0]
    assert c.pieces == ["It's", "a", "good", "deal"]
    assert sorted(c.options) == sorted(c.pieces) and c.options != c.pieces


def test_conditionals_follow_the_if_clause(nlp):
    c = items(nlp, "If you stuff the box too full, the bottom will fall out.", "conditionals")[0]
    assert c.options[0] == "will fall" and "would have fallen" in c.options


def test_record_assembly_shuffles_answers_and_rejects_clashes():
    src = SourceRef(id="t", license="CC0")
    common = dict(
        skill="grammar",
        skill_id="g",
        level="A1",
        topic="t",
        point="p",
        difficulty="easy",
        qtype="mcq",
        prompt="She ___ home.",
        instruction="i",
        explanation="an explanation",
        explanation_vi="",
        source=src,
        quality=0.9,
    )
    positions = {
        choice_question(
            qid=stable_id("gr.p", str(i)), right="went", wrong=["go", "gone", "going"], **common
        ).answer["option"]
        for i in range(40)
    }
    assert positions == {"a", "b", "c", "d"}  # the answer is not always first
    assert choice_question(qid="gr.p.x", right="went", wrong=["Went"], **common) is None
    start = choice_question(
        qid="gr.p.y", right="our", wrong=["ours"], **{**common, "prompt": "___ house is big."}
    )
    assert {o.text for o in start.options} == {"Our", "Ours"}


def test_near_duplicates_and_quotas():
    assert near_duplicate_key("Tom is a teacher.") == near_duplicate_key("Mary is a teacher.")
    assert near_duplicate_key("I have 3 cats.") == near_duplicate_key("I have 12 cats.")
    assert allocate({"a": 10, "b": 1000}, {"a": 1, "b": 1}, 100) == {"a": 10, "b": 90}


def test_filters_and_levels():
    assert not is_clean("He was killed in the war.") and is_clean("She plays the piano.")
    assert length_level(5) == "A1" and length_level(30) == "C1"
    assert topic_of(["train", "ticket", "station"]) == "travel"
    assert topic_of(["august", "month"], default="society", min_hits=2) == "society"


def test_template_texts_answer_their_own_questions():
    rng = random.Random(3)
    for family in FAMILIES.values():
        t = family(rng)
        for q in t.questions:
            assert q.right not in q.wrong and len(set(q.wrong)) == len(q.wrong)
            if q.kind == "detail":
                assert q.right in t.text or q.right.replace("on ", "") in t.text
    texts = [t.text for t in generate(200, seed="x")]
    assert len(set(texts)) == 200


def test_there_be_distractors_have_the_wrong_number(nlp):
    c = items(nlp, "There are always many gifts in the house.", "there_be")[0]
    assert c.options[0] == "are" and "were" not in c.options and "was" in c.options
    c = items(nlp, "There was a small shop near the station.", "there_be")[0]
    assert c.options[0] == "was" and "is" not in c.options and "were" in c.options
    assert not items(nlp, "I was wondering if there is any way you could help.", "there_be")


def test_reading_distractors_never_name_the_answer_again():
    from banana_english.contentbank.reading_gen import _same_name

    assert _same_name("Brunei", "Brunei Darussalam") and _same_name("Robot Arena", "Robot Arena 3")
    assert not _same_name("The Beatles", "The Dentist 2") and not _same_name("Hanoi", "Borneo")


def test_encyclopedia_topics_need_a_clear_lead():
    from banana_english.contentbank.lexicon import AMBIGUOUS_TOPIC_WORDS

    upper_house = ["house", "parliament", "government", "law", "election"]
    assert topic_of(upper_house, default="society", skip=AMBIGUOUS_TOPIC_WORDS) == "society"
    mixed = ["film", "movie", "shop", "store"]
    assert topic_of(mixed, default="society", min_hits=2, margin=1.5) == "society"


def test_template_numbers_look_alike_and_routes_exist():
    from banana_english.contentbank.templates import TRAIN_ROUTES, advert, timetable

    for seed in range(50):
        rent = advert(random.Random(seed)).questions[0]
        if "rent" in rent.prompt:
            assert all(int(w.split()[0]) % 50 == 0 for w in rent.wrong)
        t = timetable(random.Random(seed))
        assert "about 1 hours" not in t.text
        assert any(
            f"to {b} leaves {a}" in t.text
            for a, b in TRAIN_ROUTES + [(b, a) for a, b in TRAIN_ROUTES]
        )
