"""The checker: every figure of a text must be in the facts, and up/down must match the sign."""

import pytest

from report_pipeline.narrative import check_text, deterministic_summary

from .conftest import ROWS, build, write_case


def test_the_deterministic_summary_always_passes_its_own_check(case, example):
    for _, _, _, facts in (case, example):
        text = deterministic_summary(facts)
        chk = check_text(text, facts)
        assert chk.ok, chk.problems()
        assert chk.numbers_checked > 10


@pytest.mark.parametrize("n_rows", [1, 2, 3, 5])
def test_the_summary_passes_for_small_and_odd_data(tmp_path, n_rows):
    _, _, _, facts = build(write_case(tmp_path, ROWS[-n_rows:]))
    assert check_text(deterministic_summary(facts), facts).ok


def test_a_figure_that_is_not_in_the_data_is_found(case):
    _, _, _, facts = case
    chk = check_text("Orders were 5 in 2026-09, and revenue reached 190.00 EUR.", facts)
    assert chk.unknown_numbers == ["190.00"]
    assert not chk.ok and "figures that are not in the data: 190.00" in chk.problems()[0]


def test_rounding_or_rewording_a_figure_is_not_allowed(case):
    _, _, _, facts = case
    assert check_text("Revenue was 175.00 EUR.", facts).ok
    assert not check_text("Revenue was 175.5 EUR.", facts).ok
    assert not check_text("Revenue was 176 EUR.", facts).ok
    assert not check_text("Revenue was about 180 EUR.", facts).ok


def test_the_same_value_written_differently_is_the_same_figure(case):
    _, _, _, facts = case
    assert check_text("Revenue was 175 EUR in 2026-09.", facts).ok
    assert check_text("Orders were 5.0 in September 2026.", facts).ok


def test_thousands_separators_and_percent_signs(tmp_path):
    rows = [f"x{i},2026-09-{1 + i % 28:02d},books,1000.00,1" for i in range(1500)]
    _, _, _, facts = build(write_case(tmp_path, rows))
    assert check_text("Revenue was 1,500,000.00 EUR from 1,500 orders.", facts).ok
    assert not check_text("Revenue was 1,500,001.00 EUR.", facts).ok


def test_numbers_from_the_period_labels_and_notes_are_allowed(case):
    _, _, _, facts = case
    assert check_text("In September 2026 (2026-09) there were 5 orders, compared with 2026-08.", facts).ok


def test_the_wrong_direction_is_found(case):
    _, _, _, facts = case  # orders went from 4 to 5: +25.0%
    assert check_text("Orders rose 25.0% from 4 in 2026-08.", facts).ok
    assert check_text("Orders were 25.0% higher than in 2026-08.", facts).ok
    wrong = check_text("Orders fell 25.0% from 4 in 2026-08.", facts)
    assert wrong.wrong_direction and not wrong.unknown_numbers and not wrong.ok
    assert "direction contradicts the data" in wrong.problems()[0]
    assert not check_text("Orders were down 25.0% on the month.", facts).ok


def test_directions_are_judged_per_figure_in_a_sentence(case):
    _, _, _, facts = case  # orders +25.0%, slow-order rate -10.0 pp
    ok = "Orders were up 25.0%, while the rate of slow orders fell 10.0 pp."
    assert check_text(ok, facts).ok
    swapped = "Orders were down 25.0%, while the rate of slow orders rose 10.0 pp."
    assert len(check_text(swapped, facts).wrong_direction) == 1  # one sentence, reported once
    assert not check_text(swapped, facts).ok


def test_a_figure_without_a_direction_word_is_not_judged(case):
    _, _, _, facts = case
    assert check_text("The change in orders was 25.0%.", facts).ok


def test_a_bad_sentence_does_not_hide_in_a_good_text(case):
    _, _, _, facts = case
    text = "Orders were 5 in 2026-09. Revenue was 175.00 EUR. Nobody expected the 99% jump."
    assert check_text(text, facts).unknown_numbers == ["99"]


def test_number_words_are_not_checked_which_is_a_known_limit(case):
    _, _, _, facts = case
    # documented in the README: only digits are checked, so the prompt asks for digits
    assert check_text("Orders doubled to five hundred.", facts).ok


def test_incomplete_period_note_is_part_of_the_summary(tmp_path):
    rows = [r for r in ROWS if not r.startswith("b5")]
    _, _, _, facts = build(write_case(tmp_path, rows))
    text = deterministic_summary(facts)
    assert "2026-09 is incomplete" in text and check_text(text, facts).ok
