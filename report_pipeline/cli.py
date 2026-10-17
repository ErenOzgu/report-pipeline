"""Command line: build a report, check a text against the facts, validate a spec."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .data import load_table
from .facts import build_facts
from .metrics import compute
from .narrative import check_text, summarise
from .render import markdown, render_html
from .spec import SpecError, load_spec


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="report-pipeline", description="CSV in, report out.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="compute the numbers and write the report")
    b.add_argument("spec", help="the report spec (TOML)")
    b.add_argument("--out", default="report-out", help="output directory (default report-out)")
    b.add_argument("--period", help="report on this period instead of the one in the spec")
    b.add_argument(
        "--llm", action="store_true", help="let a model write the summary (needs ANTHROPIC_API_KEY)"
    )
    b.add_argument("--model")
    b.add_argument(
        "--fail-on-notes", action="store_true", help="exit 3 if the data had problems worth a note"
    )

    c = sub.add_parser("check", help="check a text against a facts file: every figure must be in it")
    c.add_argument("text", help="a text file ('-' for stdin)")
    c.add_argument("facts", help="facts.json written by build")

    v = sub.add_parser("validate", help="check a spec and the CSV header, compute nothing")
    v.add_argument("spec")
    return p


def _build(a: argparse.Namespace) -> int:
    spec = load_spec(a.spec)
    if a.period:
        from dataclasses import replace

        spec = replace(spec, report_period=a.period)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if a.llm and not key:
        print("error: --llm needs ANTHROPIC_API_KEY in the environment", file=sys.stderr)
        return 2
    table = load_table(spec)
    res = compute(spec, table)
    facts = build_facts(res)
    narrative = summarise(facts, use_model=a.llm, api_key=key, model=a.model)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "facts.json").write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "report.md").write_text(markdown(facts, spec, narrative), encoding="utf-8")
    (out / "report.html").write_text(render_html(facts, spec, narrative), encoding="utf-8")
    (out / "narrative.json").write_text(
        json.dumps(
            {
                "source": narrative.source,
                "model": narrative.model,
                "text": narrative.text,
                "figures_checked": narrative.check.numbers_checked if narrative.check else 0,
                "rejected_model_text": narrative.rejected,
                "rejection_reasons": narrative.rejection_reasons,
                "error": narrative.error,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{facts['title']}: {facts['period']}, {len(table.rows)} rows used, {len(facts['notes'])} data notes"
    )
    print(f"summary by {narrative.source}" + (f" ({narrative.model})" if narrative.source == "model" else ""))
    if narrative.rejected:
        print("model summary rejected: " + "; ".join(narrative.rejection_reasons), file=sys.stderr)
    print(f"wrote {out}/report.md, report.html, facts.json, narrative.json")
    if a.fail_on_notes and facts["notes"]:
        return 3
    return 0


def _check(a: argparse.Namespace) -> int:
    text = sys.stdin.read() if a.text == "-" else Path(a.text).read_text(encoding="utf-8")
    facts = json.loads(Path(a.facts).read_text(encoding="utf-8"))
    chk = check_text(text, facts)
    if chk.ok:
        print(f"ok: {chk.numbers_checked} figures checked, all are in the facts")
        return 0
    print("FAILED")
    for problem in chk.problems():
        print(f"- {problem}")
    return 1


def _validate(a: argparse.Namespace) -> int:
    spec = load_spec(a.spec)
    table = load_table(spec)
    print(
        f"ok: {len(spec.metrics)} metrics, {len(spec.breakdowns)} breakdowns, "
        f"{table.rows_read} rows in {table.file_name}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    a = _parser().parse_args(argv)
    try:
        return {"build": _build, "check": _check, "validate": _validate}[a.cmd](a)
    except SpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except BrokenPipeError:
        sys.stderr.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
