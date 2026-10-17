"""Markdown and HTML from the facts. Nothing is computed here: every figure is read from the facts."""

from __future__ import annotations

import html

from .narrative import Narrative
from .spec import Condition, Metric, Spec


def _cond(c: Condition) -> str:
    v = list(c.value) if isinstance(c.value, tuple) else c.value
    return f"{c.column} {c.op} {v}"


def describe(m: Metric) -> str:
    where = " and ".join(_cond(c) for c in m.where)
    if m.agg == "count":
        return "number of rows" + (f" where {where}" if where else "")
    if m.agg == "rate":
        return f"share of rows where {where}, in percent of all rows of the period"
    base = {
        "distinct": f"number of different values of `{m.column}`",
        "sum": f"sum of `{m.column}`",
        "mean": f"mean of `{m.column}`",
        "median": f"median of `{m.column}`",
        "min": f"smallest `{m.column}`",
        "max": f"largest `{m.column}`",
        "p90": f"90th percentile of `{m.column}`",
        "p95": f"95th percentile of `{m.column}`",
    }[m.agg]
    return base + (f", over rows where {where}" if where else "")


def provenance(n: Narrative) -> str:
    if n.source == "model":
        c = n.check
        return (
            f"Written by {n.model} and checked: all {c.numbers_checked if c else 0} figures in it are in the data, "
            "and its ups and downs match the changes."
        )
    if n.rejected:
        return (
            f"A summary written by {n.model} was rejected ({'; '.join(n.rejection_reasons)}). "
            "The summary below is the rules' own."
        )
    if n.error:
        return f"The model could not be used ({n.error}). The summary below is the rules' own."
    return "Written by rules from the figures below."


def _cell(s: str) -> str:
    return s.replace("|", "\\|")


def markdown(facts: dict, spec: Spec, narrative: Narrative) -> str:
    src = facts["source"]
    out = [f"# {facts['title']}", ""]
    vs = f" compared with {facts['previous_period']}" if facts["previous_period"] else ""
    out.append(
        f"**{facts['period']}**{vs}. Source: `{src['file']}`, {src['rows_used']:,} rows used "
        f"({src['rows_in_period']:,} in the period), sha256 `{src['sha256'][:12]}`."
    )
    out += ["", "## Summary", "", narrative.text, "", f"_{provenance(narrative)}_", ""]

    out += ["## Key numbers", ""]
    prev = facts["previous_period"] or "previous"
    out.append(f"| Metric | {facts['period']} | {prev} | Change |")
    out.append("|---|---:|---:|---:|")
    for m in facts["metrics"]:
        out.append(
            f"| {_cell(m['label'])} | {m['current_text']} | {m['previous_text'] or '-'} | {m['delta_text'] or '-'} |"
        )
    out.append("")

    periods = [s["period"] for s in facts["metrics"][0]["series"]]
    if len(periods) > 1:
        out += ["## Trend", "", "| Metric | " + " | ".join(periods) + " |", "|---|" + "---:|" * len(periods)]
        for m in facts["metrics"]:
            out.append(f"| {_cell(m['label'])} | " + " | ".join(s["text"] for s in m["series"]) + " |")
        out.append("")

    for b in facts["breakdowns"]:
        names = {m["id"]: m["label"] for m in facts["metrics"]}
        cols = [names[mid] for mid in b["metrics"]]
        has_share = any(r["share_text"] for r in b["rows"])
        out += [f"## {b['label']}", ""]
        out.append(f"| {b['by'].capitalize()} | " + " | ".join(cols) + (" | Share |" if has_share else " |"))
        out.append("|---|" + "---:|" * (len(cols) + (1 if has_share else 0)))
        for r in b["rows"]:
            cells = [r["values"][mid] for mid in b["metrics"]]
            out.append(
                f"| {_cell(r['name'])} | "
                + " | ".join(cells)
                + (f" | {r['share_text'] or '-'} |" if has_share else " |")
            )
        out.append("")

    out += ["## Data notes", ""]
    out += [f"- {n}" for n in facts["notes"]] or ["- No problems found in the data."]
    out += ["", "## How the numbers were computed", ""]
    for m in spec.metrics:
        out.append(f"- **{m.label}**: {describe(m)}.")
    out += [
        "",
        f"Periods are calendar {spec.period}s of `{spec.period_column}`. The change compares with the period "
        "just before. Percentiles interpolate linearly between ranks. Figures are rounded half up.",
        "",
    ]
    return "\n".join(out)


# -- HTML ----------------------------------------------------------------------------------------
CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#1b2430;--muted:#5d6b7c;--line:#e2e6ec;--accent:#2b6cb0;--good:#1a7f4b;--bad:#b42318;--bar:#c7d7ec}
@media (prefers-color-scheme:dark){:root{--bg:#10151c;--card:#171e27;--ink:#e6ebf2;--muted:#93a1b3;--line:#273140;--accent:#6aa7ff;--good:#4cc38a;--bad:#ff7b72;--bar:#2a3f5f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:960px;margin:0 auto;padding:32px 16px 64px}h1{font-size:1.8rem;margin:0 0 4px}h2{font-size:1.15rem;margin:36px 0 12px}
.sub{color:var(--muted);font-size:.9rem}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.summary p{margin:0 0 8px;font-size:1.05rem}.prov{color:var(--muted);font-size:.85rem;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}.k .label{color:var(--muted);font-size:.85rem}
.k .num{font-size:1.9rem;font-weight:650;letter-spacing:-.02em}.chip{font-size:.85rem;font-weight:600}.good{color:var(--good)}.bad{color:var(--bad)}.flat{color:var(--muted)}
svg.spark{display:block;margin-top:6px;width:100%;height:34px}table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}th:first-child,td:first-child{text-align:left}
th{color:var(--muted);font-weight:600}.scroll{overflow-x:auto}.barcell{position:relative}.bar{position:absolute;left:0;top:0;bottom:0;background:var(--bar);z-index:0;border-radius:0 4px 4px 0}
.barcell span{position:relative;z-index:1}ul{padding-left:20px}li{margin:4px 0}code{font-size:.88em}
"""


def _inline(text: str) -> str:
    """Escape, then turn `code` spans into <code>."""
    parts = html.escape(text).split("`")
    return "".join(f"<code>{x}</code>" if i % 2 else x for i, x in enumerate(parts))


def _spark(series: list[dict]) -> str:
    vals = [s["value"] for s in series]
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return ""
    lo, hi = min(v for _, v in pts), max(v for _, v in pts)
    span = (hi - lo) or 1.0
    n = len(vals) - 1
    coords = " ".join(f"{i / n * 120:.1f},{30 - (v - lo) / span * 26:.1f}" for i, v in pts)
    last_i, last_v = pts[-1]
    cx, cy = last_i / n * 120, 30 - (last_v - lo) / span * 26
    return (
        f'<svg class="spark" viewBox="0 0 120 34" preserveAspectRatio="none" role="img" aria-label="trend">'
        f'<polyline fill="none" stroke="var(--accent)" stroke-width="1.6" points="{coords}"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.4" fill="var(--accent)"/></svg>'
    )


def _chip(m: dict) -> str:
    if not m["delta_text"]:
        return '<span class="chip flat">no change figure</span>'
    sign, better = m["delta_sign"], m["better"]
    cls = "flat" if sign == 0 or better == "none" else ("good" if (sign > 0) == (better == "up") else "bad")
    return (
        f'<span class="chip {cls}">{html.escape(m["delta_text"])} vs {html.escape(m["previous_text"])}</span>'
    )


def render_html(facts: dict, spec: Spec, narrative: Narrative) -> str:
    e = html.escape
    src = facts["source"]
    p: list[str] = []
    p.append(f"<h1>{e(facts['title'])}</h1>")
    vs = f" compared with {e(facts['previous_period'])}" if facts["previous_period"] else ""
    p.append(
        f'<p class="sub"><strong>{e(facts["period"])}</strong>{vs}. Source <code>{e(src["file"])}</code>, '
        f"{src['rows_used']:,} rows used ({src['rows_in_period']:,} in the period), sha256 <code>{e(src['sha256'][:12])}</code>.</p>"
    )
    p.append(
        f'<div class="card summary"><p>{e(narrative.text)}</p><p class="prov">{e(provenance(narrative))}</p></div>'
    )
    p.append('<h2>Key numbers</h2><div class="grid">')
    for m in facts["metrics"]:
        p.append(
            f'<div class="card k"><div class="label">{e(m["label"])}</div><div class="num">{e(m["current_text"])}</div>'
            f"{_chip(m)}{_spark(m['series'])}</div>"
        )
    p.append("</div>")
    periods = [s["period"] for s in facts["metrics"][0]["series"]]
    if len(periods) > 1:
        p.append('<h2>Trend</h2><div class="card scroll"><table><thead><tr><th>Metric</th>')
        p.append("".join(f"<th>{e(x)}</th>" for x in periods) + "</tr></thead><tbody>")
        for m in facts["metrics"]:
            p.append(
                f"<tr><td>{e(m['label'])}</td>"
                + "".join(f"<td>{e(s['text'])}</td>" for s in m["series"])
                + "</tr>"
            )
        p.append("</tbody></table></div>")
    names = {m["id"]: m["label"] for m in facts["metrics"]}
    for b in facts["breakdowns"]:
        has_share = any(r["share_text"] for r in b["rows"])
        p.append(
            f'<h2>{e(b["label"])}</h2><div class="card scroll"><table><thead><tr><th>{e(b["by"].capitalize())}</th>'
        )
        p.append(
            "".join(f"<th>{e(names[mid])}</th>" for mid in b["metrics"])
            + ("<th>Share</th>" if has_share else "")
            + "</tr></thead><tbody>"
        )
        for r in b["rows"]:
            share = ""
            if has_share:
                width = float(r["share_text"].rstrip("%")) if r["share_text"] else 0.0
                share = f'<td class="barcell"><div class="bar" style="width:{min(width, 100):.1f}%"></div><span>{e(r["share_text"] or "-")}</span></td>'
            p.append(
                f"<tr><td>{e(r['name'])}</td>"
                + "".join(f"<td>{e(r['values'][mid])}</td>" for mid in b["metrics"])
                + share
                + "</tr>"
            )
        p.append("</tbody></table></div>")
    p.append('<h2>Data notes</h2><div class="card"><ul>')
    p.append("".join(f"<li>{e(n)}</li>" for n in facts["notes"]) or "<li>No problems found in the data.</li>")
    p.append('</ul></div><h2>How the numbers were computed</h2><div class="card"><ul>')
    for m in spec.metrics:
        p.append(f"<li><strong>{e(m.label)}</strong>: {_inline(describe(m))}.</li>")
    p.append(
        f'</ul><p class="sub">Periods are calendar {e(spec.period)}s of <code>{e(spec.period_column)}</code>. The change compares '
        "with the period just before. Percentiles interpolate linearly between ranks. Figures are rounded half up.</p></div>"
    )
    body = "\n".join(p)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{e(facts['title'])} - {e(facts['period'])}</title><style>{CSS}</style></head>"
        f"<body><main>\n{body}\n</main></body></html>\n"
    )
