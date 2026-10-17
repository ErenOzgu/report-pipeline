from __future__ import annotations

import pathlib

import pytest

from report_pipeline.data import load_table
from report_pipeline.facts import build_facts
from report_pipeline.metrics import compute
from report_pipeline.spec import load_spec

from .fakes import FakeAnthropic

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "support-tickets" / "spec.toml"

SPEC = """\
title = "Test report"
period_column = "day"
period = "month"
trend_periods = 3

[source]
path = "data.csv"
key = "id"

[columns]
id = "text"
day = "date"
kind = "category"
amount = "number"
hours = "number"

[[metric]]
id = "n"
label = "Orders"
agg = "count"

[[metric]]
id = "total"
label = "Revenue"
agg = "sum"
column = "amount"
unit = "EUR"
decimals = 2
better = "up"

[[metric]]
id = "slow"
label = "Slow orders"
agg = "rate"
unit = "%"
decimals = 1
better = "down"
where = [{ column = "hours", op = ">", value = 24 }]

[[breakdown]]
id = "by_kind"
label = "By kind"
by = "kind"
metrics = ["n", "total"]
top = 2
"""


def write_case(tmp_path: pathlib.Path, rows: list[str], spec: str = SPEC) -> pathlib.Path:
    (tmp_path / "data.csv").write_text(
        "id,day,kind,amount,hours\n" + "\n".join(rows) + "\n", encoding="utf-8"
    )
    (tmp_path / "spec.toml").write_text(spec, encoding="utf-8")
    return tmp_path / "spec.toml"


def build(spec_path):
    spec = load_spec(spec_path)
    table = load_table(spec)
    res = compute(spec, table)
    return spec, table, res, build_facts(res)


# two months: August has 4 orders, September has 5 (and is complete)
ROWS = [
    "a1,2026-08-03,books,10.00,5",
    "a2,2026-08-10,books,20.00,30",
    "a3,2026-08-17,games,30.00,2",
    "a4,2026-08-31,games,40.00,25",
    "b1,2026-09-01,books,15.00,3",
    "b2,2026-09-10,books,25.00,48",
    "b3,2026-09-20,games,35.00,1",
    "b4,2026-09-25,toys,45.00,26",
    "b5,2026-09-30,toys,55.00,4",
]


@pytest.fixture
def case(tmp_path):
    return build(write_case(tmp_path, ROWS))


@pytest.fixture
def example():
    return build(EXAMPLE)


@pytest.fixture
def anthropic():
    srv = FakeAnthropic()
    yield srv
    srv.close()
