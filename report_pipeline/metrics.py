"""The numbers. Everything in a report is computed here, from the rows, with plain arithmetic."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .data import Row, Table
from .spec import Breakdown, Condition, Metric, Spec, SpecError


# -- periods -----------------------------------------------------------------------------------
def period_of(d: date, kind: str) -> str:
    if kind == "month":
        return f"{d.year:04d}-{d.month:02d}"
    if kind == "week":
        iso = d.isocalendar()
        return f"{iso.year:04d}-W{iso.week:02d}"
    return d.isoformat()


def period_start(label: str, kind: str) -> date:
    if kind == "month":
        y, m = label.split("-")
        return date(int(y), int(m), 1)
    if kind == "week":
        y, w = label.split("-W")
        return date.fromisocalendar(int(y), int(w), 1)
    return date.fromisoformat(label)


def period_end(label: str, kind: str) -> date:
    start = period_start(label, kind)
    if kind == "month":
        nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        return nxt - timedelta(days=1)
    if kind == "week":
        return start + timedelta(days=6)
    return start


def next_period(label: str, kind: str) -> str:
    return period_of(period_end(label, kind) + timedelta(days=1), kind)


def period_range(first: str, last: str, kind: str) -> list[str]:
    out = [first]
    while out[-1] != last:
        out.append(next_period(out[-1], kind))
        if len(out) > 5000:
            raise SpecError("period range is absurdly long; check the dates in the data")
    return out


# -- aggregation -------------------------------------------------------------------------------
def percentile(sorted_values: list[float], p: float) -> float:
    """Linear interpolation between closest ranks (what numpy and pandas do by default)."""
    n = len(sorted_values)
    h = (n - 1) * p
    lo, hi = math.floor(h), math.ceil(h)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


def _holds(c: Condition, v: object) -> bool:
    if v is None:
        return False  # an empty cell satisfies no condition, not even '!='
    op, ref = c.op, c.value
    if op == "in":
        return v in ref  # type: ignore[operator]
    if op == "not_in":
        return v not in ref  # type: ignore[operator]
    try:
        if op == "==":
            return v == ref
        if op == "!=":
            return v != ref
        if op == ">":
            return v > ref  # type: ignore[operator]
        if op == ">=":
            return v >= ref  # type: ignore[operator]
        if op == "<":
            return v < ref  # type: ignore[operator]
        return v <= ref  # type: ignore[operator]
    except TypeError:
        return False


def select(rows: list[Row], conditions: tuple[Condition, ...]) -> list[Row]:
    return [r for r in rows if all(_holds(c, r.values.get(c.column)) for c in conditions)]


def compute_metric(m: Metric, scope: list[Row]) -> float | None:
    """The value of one metric over the rows of one period (or one group within it)."""
    if m.agg == "rate":
        if not scope:
            return None
        return 100.0 * len(select(scope, m.where)) / len(scope)
    rows = select(scope, m.where)
    if m.agg == "count":
        return float(len(rows))
    vals = [r.values[m.column] for r in rows if r.values.get(m.column) is not None]
    if m.agg == "distinct":
        return float(len(set(vals)))
    if m.agg == "sum":
        return float(sum(vals))  # type: ignore[arg-type]
    if not vals:
        return None
    nums = sorted(vals)  # type: ignore[type-var]
    if m.agg == "mean":
        return sum(nums) / len(nums)  # type: ignore[arg-type]
    if m.agg == "median":
        return percentile(nums, 0.5)  # type: ignore[arg-type]
    if m.agg == "p90":
        return percentile(nums, 0.9)  # type: ignore[arg-type]
    if m.agg == "p95":
        return percentile(nums, 0.95)  # type: ignore[arg-type]
    if m.agg == "min":
        return float(nums[0])  # type: ignore[arg-type]
    return float(nums[-1])  # type: ignore[arg-type]


# -- results -----------------------------------------------------------------------------------
@dataclass
class MetricResult:
    metric: Metric
    current: float | None
    previous: float | None
    series: list[tuple[str, float | None]]

    @property
    def is_rate(self) -> bool:
        return self.metric.unit == "%"

    @property
    def delta_abs(self) -> float | None:
        if self.current is None or self.previous is None:
            return None
        return self.current - self.previous

    @property
    def delta_pct(self) -> float | None:
        """Relative change in percent. Not defined for a rate (those get percentage points) or from zero."""
        if self.is_rate or self.current is None or self.previous in (None, 0):
            return None
        return (self.current - self.previous) / abs(self.previous) * 100.0  # type: ignore[operator]


@dataclass
class GroupRow:
    name: str
    values: dict[str, float | None]
    share: float | None  # share of the period total for the first metric, if it is a count or a sum


@dataclass
class BreakdownResult:
    breakdown: Breakdown
    rows: list[GroupRow]


@dataclass
class Notes:
    items: list[str] = field(default_factory=list)


@dataclass
class Result:
    spec: Spec
    table: Table
    period: str
    previous_period: str
    periods: list[str]
    metrics: list[MetricResult]
    breakdowns: list[BreakdownResult]
    notes: list[str]
    rows_in_period: int


def _data_notes(spec: Spec, table: Table, period: str, last_date: date) -> list[str]:
    out: list[str] = []
    if table.skipped_no_date.count:
        n = table.skipped_no_date
        out.append(
            f"{n.count} rows have no usable '{spec.period_column}' and were left out "
            f"(first at lines {', '.join(map(str, n.lines))})."
        )
    if table.duplicates.count:
        n = table.duplicates
        out.append(
            f"{n.count} rows repeat an earlier '{spec.key}' and were left out "
            f"(first at lines {', '.join(map(str, n.lines))})."
        )
    for col, p in sorted(table.invalid.items()):
        out.append(
            f"{p.count} values in '{col}' could not be read as a {spec.columns[col]} "
            f"and were treated as empty (first at lines {', '.join(map(str, p.lines))})."
        )
    for col, n in sorted(table.blank.items()):
        if spec.columns[col] in ("number", "category") and n:
            out.append(f"{n} rows have an empty '{col}'.")
    end = period_end(period, spec.period)
    if last_date < end:
        out.append(
            f"{period} is incomplete: the data ends on {last_date.isoformat()}, "
            f"the period on {end.isoformat()}. Comparing it with a full period understates it."
        )
    return out


def compute(spec: Spec, table: Table) -> Result:
    if not table.rows:
        raise SpecError("the file has no usable rows")
    kind, pcol = spec.period, spec.period_column
    labelled = [(period_of(r.values[pcol], kind), r) for r in table.rows]  # type: ignore[arg-type]
    by_period: dict[str, list[Row]] = {}
    for label, r in labelled:
        by_period.setdefault(label, []).append(r)
    labels = sorted(by_period)
    calendar = period_range(labels[0], labels[-1], kind)

    period = labels[-1] if spec.report_period == "latest" else spec.report_period
    if period not in by_period:
        raise SpecError(
            f"report_period '{period}' has no rows (periods in the data: {labels[0]} to {labels[-1]})"
        )
    idx = calendar.index(period)
    previous = calendar[idx - 1] if idx > 0 else ""
    window = calendar[max(0, idx - spec.trend_periods + 1) : idx + 1]

    results: list[MetricResult] = []
    for m in spec.metrics:
        series = [(p, compute_metric(m, by_period.get(p, []))) for p in window]
        cur = compute_metric(m, by_period[period])
        prev = compute_metric(m, by_period.get(previous, [])) if previous else None
        # a period with no rows at all has no value to compare against
        if previous and previous not in by_period and m.agg != "count":
            prev = None
        results.append(MetricResult(m, cur, prev, series))

    last_date = max(r.values[pcol] for r in by_period[period])  # type: ignore[type-var]
    notes = _data_notes(spec, table, period, last_date)  # type: ignore[arg-type]
    notes += list(spec.notes)

    breakdowns: list[BreakdownResult] = []
    scope = by_period[period]
    for b in spec.breakdowns:
        metrics = [spec.metric(mid) for mid in b.metrics]
        groups: dict[str, list[Row]] = {}
        for r in scope:
            groups.setdefault(str(r.values.get(b.by) or "(blank)"), []).append(r)
        first = metrics[0]
        total = compute_metric(first, scope) if first.agg in ("count", "sum") else None
        scored = []
        for name, rows in groups.items():
            vals = {m.id: compute_metric(m, rows) for m in metrics}
            scored.append((name, rows, vals))
        scored.sort(key=lambda t: (-(t[2][first.id] if t[2][first.id] is not None else -math.inf), t[0]))
        kept, rest = scored[: b.top], scored[b.top :]
        out_rows = [GroupRow(n, v, _share(v[first.id], total)) for n, _, v in kept]
        if rest:
            other_rows = [r for _, rows, _ in rest for r in rows]
            vals = {m.id: compute_metric(m, other_rows) for m in metrics}
            out_rows.append(GroupRow(f"Other ({len(rest)} more)", vals, _share(vals[first.id], total)))
        breakdowns.append(BreakdownResult(b, out_rows))

    return Result(
        spec=spec,
        table=table,
        period=period,
        previous_period=previous,
        periods=window,
        metrics=results,
        breakdowns=breakdowns,
        notes=notes,
        rows_in_period=len(scope),
    )


def _share(v: float | None, total: float | None) -> float | None:
    if v is None or not total:
        return None
    return v / total * 100.0
