"""The report spec: a TOML file that says what the columns are and which numbers to compute."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

AGGS = {"count", "sum", "mean", "median", "min", "max", "p90", "p95", "distinct", "rate"}
NEEDS_COLUMN = AGGS - {"count", "rate"}
OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in"}
TYPES = {"text", "category", "number", "date"}
PERIODS = {"day", "week", "month"}
BETTER = {"up", "down", "none"}


class SpecError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    column: str
    op: str
    value: object


@dataclass(frozen=True)
class Metric:
    id: str
    label: str
    agg: str
    column: str | None = None
    where: tuple[Condition, ...] = ()
    unit: str = ""
    decimals: int = 0
    better: str = "none"


@dataclass(frozen=True)
class Breakdown:
    id: str
    label: str
    by: str
    metrics: tuple[str, ...]
    top: int = 10


@dataclass(frozen=True)
class Spec:
    title: str
    path: Path  # the CSV, resolved against the spec file
    delimiter: str
    key: str | None
    columns: dict[str, str]
    period_column: str
    period: str
    report_period: str  # "latest" or a period label
    trend_periods: int
    metrics: tuple[Metric, ...]
    breakdowns: tuple[Breakdown, ...] = ()
    notes: tuple[str, ...] = field(default=())

    def metric(self, metric_id: str) -> Metric:
        for m in self.metrics:
            if m.id == metric_id:
                return m
        raise KeyError(metric_id)


def _need(table: dict, key: str, where: str):
    if key not in table:
        raise SpecError(f"{where}: missing '{key}'")
    return table[key]


def _conditions(raw: list, columns: dict[str, str], where: str) -> tuple[Condition, ...]:
    out = []
    for i, c in enumerate(raw, start=1):
        w = f"{where}, condition {i}"
        col, op = _need(c, "column", w), _need(c, "op", w)
        if col not in columns:
            raise SpecError(f"{w}: unknown column '{col}'")
        if op not in OPS:
            raise SpecError(f"{w}: unknown op '{op}' (use one of {', '.join(sorted(OPS))})")
        value = _need(c, "value", w)
        if op in ("in", "not_in") and not isinstance(value, list):
            raise SpecError(f"{w}: '{op}' needs a list")
        if columns[col] == "number" and op not in ("in", "not_in") and not isinstance(value, (int, float)):
            raise SpecError(f"{w}: column '{col}' is a number, compare it with a number")
        out.append(Condition(col, op, tuple(value) if isinstance(value, list) else value))
    return tuple(out)


def load_spec(path: str | Path) -> Spec:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SpecError(f"cannot read {path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SpecError(f"{path}: not valid TOML: {exc}") from exc

    src = _need(raw, "source", "spec")
    columns = dict(_need(raw, "columns", "spec"))
    for name, typ in columns.items():
        if typ not in TYPES:
            raise SpecError(f"columns.{name}: unknown type '{typ}' (use one of {', '.join(sorted(TYPES))})")
    period_column = _need(raw, "period_column", "spec")
    if columns.get(period_column) != "date":
        raise SpecError(f"period_column '{period_column}' must be a column of type 'date'")
    period = raw.get("period", "month")
    if period not in PERIODS:
        raise SpecError(f"period must be one of {', '.join(sorted(PERIODS))}")
    key = src.get("key")
    if key is not None and key not in columns:
        raise SpecError(f"source.key '{key}' is not in [columns]")

    metrics: list[Metric] = []
    for i, m in enumerate(raw.get("metric", []), start=1):
        w = f"metric #{i}"
        mid = _need(m, "id", w)
        w = f"metric '{mid}'"
        agg = _need(m, "agg", w)
        if agg not in AGGS:
            raise SpecError(f"{w}: unknown agg '{agg}' (use one of {', '.join(sorted(AGGS))})")
        col = m.get("column")
        if agg in NEEDS_COLUMN and col is None:
            raise SpecError(f"{w}: agg '{agg}' needs a column")
        if col is not None and col not in columns:
            raise SpecError(f"{w}: unknown column '{col}'")
        if agg in AGGS - {"count", "rate", "distinct"} and col is not None and columns[col] != "number":
            raise SpecError(f"{w}: agg '{agg}' needs a number column, '{col}' is {columns[col]}")
        if agg == "rate" and not m.get("where"):
            raise SpecError(f"{w}: a rate needs a 'where' (the rows that count)")
        better = m.get("better", "none")
        if better not in BETTER:
            raise SpecError(f"{w}: better must be up, down or none")
        if any(x.id == mid for x in metrics):
            raise SpecError(f"{w}: duplicate id")
        metrics.append(
            Metric(
                id=mid,
                label=_need(m, "label", w),
                agg=agg,
                column=col,
                where=_conditions(m.get("where", []), columns, w),
                unit=m.get("unit", ""),
                decimals=int(m.get("decimals", 0)),
                better=better,
            )
        )
    if not metrics:
        raise SpecError("spec has no [[metric]]")

    breakdowns: list[Breakdown] = []
    for i, b in enumerate(raw.get("breakdown", []), start=1):
        w = f"breakdown #{i}"
        bid = _need(b, "id", w)
        by = _need(b, "by", w)
        if columns.get(by) not in ("category", "text"):
            raise SpecError(f"breakdown '{bid}': 'by' must be a category or text column")
        ids = tuple(_need(b, "metrics", w))
        for mid in ids:
            if mid not in {m.id for m in metrics}:
                raise SpecError(f"breakdown '{bid}': unknown metric '{mid}'")
        breakdowns.append(
            Breakdown(id=bid, label=b.get("label", bid), by=by, metrics=ids, top=int(b.get("top", 10)))
        )

    return Spec(
        title=raw.get("title", path.stem),
        path=(path.parent / _need(src, "path", "source")).resolve(),
        delimiter=src.get("delimiter", ","),
        key=key,
        columns=columns,
        period_column=period_column,
        period=period,
        report_period=str(raw.get("report_period", "latest")),
        trend_periods=int(raw.get("trend_periods", 6)),
        metrics=tuple(metrics),
        breakdowns=tuple(breakdowns),
        notes=tuple(raw.get("notes", [])),
    )
