from datetime import date

import pytest

from report_pipeline.metrics import (
    compute_metric,
    next_period,
    percentile,
    period_end,
    period_of,
    period_range,
    period_start,
)
from report_pipeline.spec import Condition, Metric, SpecError

from .conftest import ROWS, SPEC, build, write_case


# -- periods -------------------------------------------------------------------------------------
def test_period_labels():
    assert period_of(date(2026, 9, 30), "month") == "2026-09"
    assert period_of(date(2026, 1, 1), "week") == "2026-W01"  # a Thursday: week 1 of 2026
    assert period_of(date(2027, 1, 1), "week") == "2026-W53"  # 2026 has 53 ISO weeks
    assert period_of(date(2026, 1, 5), "week") == "2026-W02"
    assert period_of(date(2026, 9, 30), "day") == "2026-09-30"


@pytest.mark.parametrize("kind", ["day", "week", "month"])
def test_a_period_contains_exactly_its_own_days(kind):
    d = date(2026, 1, 1)
    from datetime import timedelta

    for _ in range(800):
        label = period_of(d, kind)
        assert period_start(label, kind) <= d <= period_end(label, kind)
        assert period_of(period_start(label, kind), kind) == label
        assert period_of(period_end(label, kind), kind) == label
        d += timedelta(days=1)


def test_period_range_crosses_year_ends_and_leap_days():
    assert period_range("2025-11", "2026-02", "month") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert period_range("2026-W52", "2027-W02", "week") == ["2026-W52", "2026-W53", "2027-W01", "2027-W02"]
    assert period_range("2028-02-28", "2028-03-01", "day") == ["2028-02-28", "2028-02-29", "2028-03-01"]
    assert period_end("2028-02", "month") == date(2028, 2, 29)
    assert next_period("2026-12", "month") == "2027-01"


# -- aggregation ---------------------------------------------------------------------------------
def test_percentile_interpolates_like_numpy():
    xs = [1.0, 2.0, 3.0, 4.0]
    assert percentile(xs, 0.5) == 2.5
    assert percentile(xs, 0.9) == pytest.approx(3.7)
    assert percentile([7.0], 0.9) == 7.0
    assert percentile(xs, 0.0) == 1.0 and percentile(xs, 1.0) == 4.0


class R:  # a row
    def __init__(self, **values):
        self.values = values


def m(agg, column=None, where=()):
    return Metric(id="x", label="x", agg=agg, column=column, where=tuple(where))


def test_each_aggregation():
    rows = [R(v=1.0, k="a"), R(v=2.0, k="a"), R(v=9.0, k="b"), R(v=None, k="b")]
    assert compute_metric(m("count"), rows) == 4
    assert compute_metric(m("distinct", "k"), rows) == 2
    assert compute_metric(m("sum", "v"), rows) == 12
    assert compute_metric(m("mean", "v"), rows) == 4
    assert compute_metric(m("median", "v"), rows) == 2
    assert compute_metric(m("min", "v"), rows) == 1 and compute_metric(m("max", "v"), rows) == 9
    assert compute_metric(m("p90", "v"), rows) == pytest.approx(7.6)
    assert compute_metric(m("count", where=[Condition("k", "==", "a")]), rows) == 2


def test_empty_scopes():
    assert compute_metric(m("mean", "v"), []) is None
    assert compute_metric(m("median", "v"), [R(v=None)]) is None
    assert compute_metric(m("sum", "v"), []) == 0
    assert compute_metric(m("count"), []) == 0
    assert compute_metric(m("rate", where=[Condition("v", ">", 1)]), []) is None


def test_a_rate_counts_against_all_rows_of_the_scope():
    rows = [R(v=5.0), R(v=50.0), R(v=None), R(v=70.0)]
    rate = compute_metric(m("rate", where=[Condition("v", ">", 24)]), rows)
    assert rate == 50.0  # 2 of 4, the empty one counts as not matching


def test_an_empty_cell_satisfies_no_condition_not_even_not_equal():
    rows = [R(k="a"), R(k=None), R(k="b")]
    assert compute_metric(m("count", where=[Condition("k", "!=", "a")]), rows) == 1
    assert compute_metric(m("count", where=[Condition("k", "not_in", ("a",))]), rows) == 1
    assert compute_metric(m("count", where=[Condition("k", "in", ("a", "b"))]), rows) == 2


# -- a whole result ------------------------------------------------------------------------------
def test_current_previous_and_changes(case):
    _, _, res, facts = case
    by = {x.metric.id: x for x in res.metrics}
    assert res.period == "2026-09" and res.previous_period == "2026-08"
    assert (by["n"].current, by["n"].previous) == (5, 4)
    assert by["n"].delta_pct == 25.0 and by["n"].delta_abs == 1
    assert by["total"].current == 175.0 and by["total"].previous == 100.0
    assert by["slow"].current == 40.0 and by["slow"].previous == 50.0  # a rate
    assert by["slow"].delta_pct is None and by["slow"].delta_abs == -10.0
    assert facts["metrics"][2]["delta_text"] == "-10.0 pp"
    assert facts["metrics"][0]["delta_text"] == "+25.0%"


def test_trend_window_is_the_last_n_calendar_periods(case):
    _, _, res, _ = case
    assert res.periods == ["2026-08", "2026-09"]  # the data starts in August; trend_periods is 3
    n = next(x for x in res.metrics if x.metric.id == "n")
    assert n.series == [("2026-08", 4.0), ("2026-09", 5.0)]


def test_a_gap_month_is_the_previous_period_not_the_last_populated_one(tmp_path):
    rows = ["a,2026-06-03,books,10,1", "b,2026-08-03,books,20,1", "c,2026-08-04,books,30,1"]
    _, _, res, facts = build(write_case(tmp_path, rows))
    assert res.previous_period == "2026-07"
    n = next(x for x in res.metrics if x.metric.id == "n")
    assert n.previous == 0 and n.delta_pct is None  # no percent change from zero
    total = next(x for x in res.metrics if x.metric.id == "total")
    assert total.previous is None  # July has no rows: its revenue is not "0", it is unknown
    assert facts["metrics"][0]["delta_text"] == ""
    # the gap shows in the trend: no orders, and no rate (there were no rows to take a share of)
    assert [v for _, v in n.series] == [1.0, 0.0, 2.0]
    slow = next(x for x in res.metrics if x.metric.id == "slow")
    assert [v for _, v in slow.series][1] is None


def test_first_period_has_no_previous(tmp_path):
    _, _, res, facts = build(write_case(tmp_path, ["a,2026-08-03,books,10,1"]))
    assert res.previous_period == "" and facts["metrics"][0]["previous_text"] == ""


def test_report_period_can_be_chosen(tmp_path):
    spec = SPEC.replace('title = "Test report"', 'title = "Test report"\nreport_period = "2026-08"')
    _, _, res, _ = build(write_case(tmp_path, ROWS, spec))
    assert res.period == "2026-08" and res.rows_in_period == 4
    bad = SPEC.replace('title = "Test report"', 'title = "Test report"\nreport_period = "2025-01"')
    with pytest.raises(SpecError, match="has no rows"):
        build(write_case(tmp_path, ROWS, bad))


def test_an_incomplete_period_is_flagged(tmp_path):
    rows = [r for r in ROWS if not r.startswith("b5")]  # data now ends on 2026-09-25
    _, _, res, _ = build(write_case(tmp_path, rows))
    assert any("2026-09 is incomplete" in n and "2026-09-25" in n for n in res.notes)
    _, _, res, _ = build(write_case(tmp_path, ROWS))
    assert not any("incomplete" in n for n in res.notes)


def test_breakdown_top_n_and_other(case):
    _, _, res, facts = case
    rows = facts["breakdowns"][0]["rows"]
    # September: books 2, toys 2, games 1. Ties are broken by name; the rest goes into "Other"
    assert [r["name"] for r in rows] == ["books", "toys", "Other (1 more)"]
    assert rows[0]["values"] == {"n": "2", "total": "40.00 EUR"}
    assert rows[1]["values"] == {"n": "2", "total": "100.00 EUR"}
    assert rows[2]["values"] == {"n": "1", "total": "35.00 EUR"}
    assert [r["share_text"] for r in rows] == ["40.0%", "40.0%", "20.0%"]


def test_notes_for_data_problems_are_in_the_facts(tmp_path):
    rows = ROWS + ["a1,2026-09-02,books,1,1", "z9,,books,1,1", "z8,2026-09-03,books,x,1"]
    _, _, _, facts = build(write_case(tmp_path, rows))
    text = " ".join(facts["notes"])
    assert "1 rows repeat an earlier 'id'" in text
    assert "1 rows have no usable 'day'" in text
    assert "1 values in 'amount' could not be read as a number" in text
