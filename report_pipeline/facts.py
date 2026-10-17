"""Turn a Result into the facts file: every number of the report, already written the way it is shown.

The facts file is the contract. The report is rendered from it, a model may only write about what is in
it, and the checker looks every figure of a text up in it.
"""

from __future__ import annotations

from decimal import Decimal

from . import fmt
from .metrics import MetricResult, Result

SCHEMA = 1


def _delta_texts(mr: MetricResult) -> tuple[str, str, str]:
    """(percent or points text, absolute text, sentence fragment) for the change from the last period."""
    m = mr.metric
    if mr.delta_abs is None:
        return "", "", ""
    if mr.is_rate:
        pts = fmt.signed(mr.delta_abs, max(m.decimals, 1), "pp")
        return pts, pts, pts
    absolute = fmt.signed(mr.delta_abs, m.decimals, m.unit)
    if mr.delta_pct is None:
        return "", absolute, absolute
    pct = fmt.signed(mr.delta_pct, 1, "%")
    return pct, absolute, pct


def metric_statement(mr: MetricResult, period: str, previous: str) -> str:
    m = mr.metric
    cur = fmt.value(mr.current, m.decimals, m.unit)
    if mr.previous is None:
        return f"{m.label}: {cur} in {period}"
    prev = fmt.value(mr.previous, m.decimals, m.unit)
    _, _, frag = _delta_texts(mr)
    tail = f" ({frag})" if frag else ""
    return f"{m.label}: {cur} in {period}; {prev} in {previous}{tail}"


def build_facts(res: Result) -> dict:
    spec = res.spec
    metrics = []
    for mr in res.metrics:
        m = mr.metric
        pct_text, abs_text, _ = _delta_texts(mr)
        metrics.append(
            {
                "id": m.id,
                "label": m.label,
                "unit": m.unit,
                "better": m.better,
                "current": mr.current,
                "current_text": fmt.value(mr.current, m.decimals, m.unit),
                "previous": mr.previous,
                "previous_text": fmt.value(mr.previous, m.decimals, m.unit)
                if mr.previous is not None
                else "",
                "delta_abs": mr.delta_abs,
                "delta_abs_text": abs_text,
                "delta_pct": mr.delta_pct,
                "delta_text": pct_text,
                "delta_sign": (0 if not mr.delta_abs else (1 if mr.delta_abs > 0 else -1))
                if mr.delta_abs is not None
                else None,
                "statement": metric_statement(mr, res.period, res.previous_period),
                "series": [
                    {"period": p, "value": v, "text": fmt.value(v, m.decimals, m.unit)} for p, v in mr.series
                ],
            }
        )
    breakdowns = []
    for br in res.breakdowns:
        rows = []
        for g in br.rows:
            vals = {}
            for mid in br.breakdown.metrics:
                m = spec.metric(mid)
                vals[mid] = fmt.value(g.values[mid], m.decimals, m.unit)
            rows.append(
                {
                    "name": g.name,
                    "values": vals,
                    "share_text": fmt.value(g.share, 1, "%") if g.share is not None else "",
                }
            )
        breakdowns.append(
            {
                "id": br.breakdown.id,
                "label": br.breakdown.label,
                "by": br.breakdown.by,
                "metrics": list(br.breakdown.metrics),
                "rows": rows,
            }
        )
    return {
        "schema": SCHEMA,
        "title": spec.title,
        "period": res.period,
        "previous_period": res.previous_period,
        "period_kind": spec.period,
        "source": {
            "file": res.table.file_name,
            "rows_read": res.table.rows_read,
            "rows_used": len(res.table.rows),
            "rows_in_period": res.rows_in_period,
            "sha256": res.table.sha256,
        },
        "metrics": metrics,
        "breakdowns": breakdowns,
        "notes": res.notes,
    }


def strings(facts: dict) -> list[str]:
    """Every piece of text in the facts that may contain a figure a text is allowed to repeat."""
    out = [facts["title"], facts["period"], facts["previous_period"]]
    src = facts["source"]
    out += [str(src["rows_read"]), str(src["rows_used"]), str(src["rows_in_period"])]
    for m in facts["metrics"]:
        out += [
            m["label"],
            m["statement"],
            m["current_text"],
            m["previous_text"],
            m["delta_text"],
            m["delta_abs_text"],
        ]
        for s in m["series"]:
            out += [s["period"], s["text"]]
    for b in facts["breakdowns"]:
        out.append(b["label"])
        for r in b["rows"]:
            out += [r["name"], r["share_text"], *r["values"].values()]
    out += facts["notes"]
    return out


def allowed_numbers(facts: dict) -> set[Decimal]:
    """Numbers a text may contain: every figure in the facts, compared by value and without sign."""
    allowed: set[Decimal] = set()
    for s in strings(facts):
        for tok in fmt.numbers_in(s):
            allowed.add(fmt.normalise(tok))
    return allowed


def for_model(facts: dict) -> str:
    """The facts as plain lines for a prompt. No rows, only aggregates."""
    lines = [
        f"Report: {facts['title']}",
        f"Period: {facts['period']} (compared with {facts['previous_period'] or 'nothing earlier'})",
        "",
        "Key figures:",
    ]
    for m in facts["metrics"]:
        lines.append(f"- {m['statement']}")
    for b in facts["breakdowns"]:
        lines += ["", f"{b['label']} (by {b['by']}):"]
        for r in b["rows"]:
            vals = ", ".join(f"{mid}: {txt}" for mid, txt in r["values"].items())
            share = f", share {r['share_text']}" if r["share_text"] else ""
            lines.append(f"- {r['name']}: {vals}{share}")
    if facts["notes"]:
        lines += ["", "Notes about the data:"]
        lines += [f"- {n}" for n in facts["notes"]]
    return "\n".join(lines)
