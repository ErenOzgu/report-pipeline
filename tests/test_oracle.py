"""The same numbers, computed independently with pandas, must agree with this tool's.

pandas is a test dependency only. The tool itself uses the standard library.
"""

import math
import random
from datetime import date, timedelta

import pytest

pd = pytest.importorskip("pandas")

from report_pipeline import fmt  # noqa: E402

from .conftest import SPEC, build, write_case  # noqa: E402


def pandas_view(csv_path):
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df = df.drop_duplicates("ticket_id", keep="first") if "ticket_id" in df else df
    return df


def oracle_example(csv_path):
    df = pandas_view(csv_path)
    df["opened_d"] = pd.to_datetime(df["opened"], errors="coerce")
    df = df.dropna(subset=["opened_d"]).copy()
    df["res"] = pd.to_numeric(df["resolution_hours"], errors="coerce")
    df["sat"] = pd.to_numeric(df["satisfaction"], errors="coerce")
    df["month"] = df["opened_d"].dt.strftime("%Y-%m")
    return df


def close(a, b):
    if a is None or (isinstance(b, float) and math.isnan(b)):
        return a is None and (isinstance(b, float) and math.isnan(b))
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def test_every_metric_of_every_month_matches_pandas(example):
    spec, table, res, _ = example
    df = oracle_example(spec.path)
    by = {x.metric.id: x for x in res.metrics}
    assert len(df) == len(table.rows)
    for month, g in df.groupby("month"):
        series = {mid: dict(x.series) for mid, x in by.items()}
        assert series["opened"][month] == len(g)
        assert series["customers"][month] == g["customer"].nunique()
        assert close(series["median_resolution"][month], g["res"].median())
        assert close(series["p90_resolution"][month], g["res"].quantile(0.9))
        assert close(series["slow"][month], 100.0 * (g["res"] > 24).sum() / len(g))
        assert close(series["satisfaction"][month], g["sat"].mean())


def test_the_breakdown_matches_pandas(example):
    spec, _, res, facts = example
    df = oracle_example(spec.path)
    cur = df[df["month"] == res.period]
    expected = cur.groupby("category").size().sort_values(ascending=False, kind="stable")
    got = {r["name"]: r["values"]["opened"] for r in facts["breakdowns"][0]["rows"]}
    assert got == {k: str(v) for k, v in expected.items()}
    med = cur.groupby("category")["res"].median()
    for r in facts["breakdowns"][0]["rows"]:
        assert r["values"]["median_resolution"] == fmt.number(float(med[r["name"]]), 1) + " h"


def test_group_counts_add_up_to_the_total(example):
    _, _, res, facts = example
    total = int(facts["metrics"][0]["current"])
    for b in facts["breakdowns"]:
        assert sum(int(r["values"]["opened"]) for r in b["rows"] if "opened" in r["values"]) == total


@pytest.mark.parametrize("seed", range(8))
def test_random_data_with_holes_matches_pandas(tmp_path, seed):
    rng = random.Random(seed)
    rows, d0 = [], date(2026, 1, 1)
    for i in range(400):
        day = (d0 + timedelta(days=rng.randint(0, 200))).isoformat()
        hours = "" if rng.random() < 0.1 else f"{rng.lognormvariate(2, 1):.2f}"
        amount = "" if rng.random() < 0.05 else f"{rng.uniform(1, 500):.2f}"
        rows.append(f"r{i},{day},{rng.choice(['a', 'b', 'c', 'd'])},{amount},{hours}")
    spec = SPEC.replace("trend_periods = 3", "trend_periods = 12")
    _, table, res, _ = build(write_case(tmp_path, rows, spec))
    df = pd.read_csv(tmp_path / "data.csv")
    df["month"] = pd.to_datetime(df["day"]).dt.strftime("%Y-%m")
    by = {x.metric.id: dict(x.series) for x in res.metrics}
    for month, g in df.groupby("month"):
        assert month in by["n"]
        assert by["n"][month] == len(g)
        assert close(by["total"][month], g["amount"].sum())
        assert close(by["slow"][month], 100.0 * (g["hours"] > 24).sum() / len(g))
