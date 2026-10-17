import pytest

from report_pipeline import fmt
from report_pipeline.data import load_table
from report_pipeline.spec import SpecError, load_spec

from .conftest import ROWS, SPEC, write_case


# -- fmt -----------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("x", "d", "out"),
    [
        (0.125, 2, "0.13"),
        (2.675, 2, "2.68"),
        (1234.5, 1, "1,234.5"),
        (1234567, 0, "1,234,567"),
        (-0.04, 1, "0.0"),
        (12.0, 1, "12.0"),
        (0.5, 0, "1"),
        (1.5, 0, "2"),
        (2.5, 0, "3"),
    ],
)
def test_numbers_are_rounded_half_up_and_never_negative_zero(x, d, out):
    assert fmt.number(x, d) == out


def test_value_and_signed():
    assert fmt.value(31.25, 1, "%") == "31.3%"
    assert fmt.value(12.1, 1, "h") == "12.1 h"
    assert fmt.value(None) == "n/a"
    assert fmt.signed(8.24, 1, "%") == "+8.2%"
    assert fmt.signed(-3.1, 1, "pp") == "-3.1 pp"
    assert fmt.signed(-0.01, 1, "%") == "0.0%"


def test_numbers_in_text_and_comparison_by_value():
    assert fmt.numbers_in("1,234.5 tickets, up 8.2% in 2026-09") == ["1,234.5", "8.2", "2026", "09"]
    assert fmt.normalise("1,234.50") == fmt.normalise("1234.5")
    assert fmt.normalise("12.0") == fmt.normalise("12")
    assert fmt.numbers_in("v2.1 and abc3") == []  # digits glued to a word are not figures


# -- spec ----------------------------------------------------------------------------------------
def bad(tmp_path, old, new, match):
    p = write_case(tmp_path, ROWS, SPEC.replace(old, new))
    with pytest.raises(SpecError, match=match):
        load_spec(p)


def test_a_good_spec_loads(tmp_path):
    spec = load_spec(write_case(tmp_path, ROWS))
    assert [m.id for m in spec.metrics] == ["n", "total", "slow"]
    assert spec.path == (tmp_path / "data.csv").resolve()
    assert spec.breakdowns[0].top == 2


def test_spec_errors_name_the_problem(tmp_path):
    bad(tmp_path, 'agg = "sum"', 'agg = "summ"', "metric 'total': unknown agg 'summ'")
    bad(tmp_path, 'column = "amount"\nunit', "unit", "agg 'sum' needs a column")
    bad(tmp_path, 'column = "amount"', 'column = "nope"', "unknown column 'nope'")
    bad(tmp_path, 'column = "amount"', 'column = "kind"', "needs a number column")
    bad(tmp_path, 'op = ">"', 'op = "~"', "unknown op '~'")
    bad(tmp_path, "value = 24", 'value = "24"', "compare it with a number")
    bad(tmp_path, 'where = [{ column = "hours", op = ">", value = 24 }]', "", "a rate needs a 'where'")
    bad(tmp_path, 'period_column = "day"', 'period_column = "kind"', "must be a column of type 'date'")
    bad(tmp_path, 'amount = "number"', 'amount = "money"', "unknown type 'money'")
    bad(tmp_path, 'metrics = ["n", "total"]', 'metrics = ["n", "x"]', "unknown metric 'x'")
    bad(tmp_path, 'by = "kind"', 'by = "amount"', "must be a category or text column")
    bad(tmp_path, 'period = "month"', 'period = "year"', "period must be one of")
    bad(tmp_path, 'key = "id"', 'key = "nope"', "source.key 'nope'")
    bad(tmp_path, 'id = "total"', 'id = "n"', "duplicate id")


def test_unreadable_and_invalid_toml(tmp_path):
    with pytest.raises(SpecError, match="cannot read"):
        load_spec(tmp_path / "nope.toml")
    (tmp_path / "x.toml").write_text("this is = = not toml")
    with pytest.raises(SpecError, match="not valid TOML"):
        load_spec(tmp_path / "x.toml")


# -- data ----------------------------------------------------------------------------------------
def table(tmp_path, rows):
    return load_table(load_spec(write_case(tmp_path, rows)))


def test_types_blanks_and_bad_values(tmp_path):
    t = table(
        tmp_path,
        [
            "a,2026-08-03,books,10.5,5",
            "b,2026-08-04,books,,n/a",  # blank amount, unreadable hours
            "c,2026-08-05T10:00:00Z,,7,3",  # a datetime, a blank category
            "d,not-a-date,books,1,1",  # no usable date: left out
            "e,2026-02-30,books,1,1",  # an impossible date: left out
        ],
    )
    assert t.rows_read == 5 and len(t.rows) == 3
    assert t.rows[0].values["amount"] == 10.5 and t.rows[1].values["amount"] is None
    assert t.rows[1].values["hours"] is None and t.invalid["hours"].count == 1
    assert t.skipped_no_date.count == 2 and t.skipped_no_date.lines == [5, 6]
    assert t.blank == {"amount": 1, "kind": 1}


def test_duplicate_keys_are_dropped_after_the_first(tmp_path):
    t = table(tmp_path, ["a,2026-08-03,books,1,1", "a,2026-08-04,books,99,1", "b,2026-08-05,books,2,1"])
    assert [r.values["id"] for r in t.rows] == ["a", "b"]
    assert t.duplicates.count == 1 and t.duplicates.lines == [3]


def test_empty_lines_bom_quotes_and_line_numbers(tmp_path):
    p = write_case(tmp_path, [])
    (tmp_path / "data.csv").write_bytes(
        "﻿id,day,kind,amount,hours\n"
        'a,2026-08-03,"books, new",1,1\n'
        "\n"
        'b,2026-08-04,"multi\nline",2,x\n'
        "c,2026-08-05,books,3,3\n".encode()
    )
    t = load_table(load_spec(p))
    assert [r.values["kind"] for r in t.rows] == ["books, new", "multi\nline", "books"]
    assert t.invalid["hours"].lines == [5]  # the record ends on physical line 5


def test_missing_column_and_empty_file(tmp_path):
    p = write_case(tmp_path, [])
    (tmp_path / "data.csv").write_text("id,day,kind\na,2026-08-03,books\n")
    with pytest.raises(SpecError, match="no column 'amount', 'hours'"):
        load_table(load_spec(p))
    (tmp_path / "data.csv").write_text("")
    with pytest.raises(SpecError, match="is empty"):
        load_table(load_spec(p))
    with pytest.raises(SpecError, match="cannot read"):
        (tmp_path / "data.csv").unlink()
        load_table(load_spec(p))


def test_the_hash_is_of_the_bytes_that_were_read(tmp_path):
    import hashlib

    t = table(tmp_path, ["a,2026-08-03,books,1,1"])
    assert t.sha256 == hashlib.sha256((tmp_path / "data.csv").read_bytes()).hexdigest()
