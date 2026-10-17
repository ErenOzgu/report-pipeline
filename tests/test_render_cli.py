import json
import re

import pytest

from report_pipeline.cli import main
from report_pipeline.narrative import summarise
from report_pipeline.render import markdown, render_html

from .conftest import EXAMPLE, ROWS, SPEC, build, write_case


def test_two_builds_are_byte_identical(tmp_path, capsys):
    for name in ("a", "b"):
        assert main(["build", str(EXAMPLE), "--out", str(tmp_path / name)]) == 0
    capsys.readouterr()
    for f in ("report.md", "report.html", "facts.json", "narrative.json"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes(), f


def test_everything_from_the_data_is_escaped_in_html(tmp_path):
    evil = '"<script>alert(1)</script>"'
    rows = ROWS + [f"x{i},2026-09-0{i},{evil},5,1" for i in range(1, 5)]  # 4 rows: it is a top group
    rows += [f"y{i},2026-09-1{i},a|b,5,1" for i in range(1, 4)]
    spec, _, _, facts = build(write_case(tmp_path, rows))
    html = render_html(facts, spec, summarise(facts))
    assert "<script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    md = markdown(facts, spec, summarise(facts))
    assert "a\\|b" in md


def test_the_html_is_self_contained(case):
    spec, _, _, facts = case
    html = render_html(facts, spec, summarise(facts))
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html and "<link" not in html and " src=" not in html
    assert "prefers-color-scheme:dark" in html and "viewport" in html


def test_the_markdown_has_the_sections_and_the_provenance(example):
    spec, _, _, facts = example
    md = markdown(facts, spec, summarise(facts))
    for h in (
        "## Summary",
        "## Key numbers",
        "## Trend",
        "## By category",
        "## Data notes",
        "## How the numbers were computed",
    ):
        assert h in md
    assert "Written by rules from the figures below." in md
    assert re.search(r"sha256 `[0-9a-f]{12}`", md)
    assert "- **Tickets that took over 24 h**: share of rows where resolution_hours > 24" in md


def test_every_figure_in_the_report_tables_is_in_the_facts(example):
    from report_pipeline import fmt
    from report_pipeline.facts import allowed_numbers

    spec, _, _, facts = example
    md = markdown(facts, spec, summarise(facts))
    allowed = allowed_numbers(facts)
    table_lines = [ln for ln in md.splitlines() if ln.startswith("|") and not ln.startswith("|---")]
    for ln in table_lines:
        for tok in fmt.numbers_in(ln):
            assert fmt.normalise(tok) in allowed, ln


def test_build_writes_the_four_files(tmp_path, capsys):
    out = tmp_path / "o"
    assert main(["build", str(EXAMPLE), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Support tickets: 2026-09, 1142 rows used" in text and "summary by rules" in text
    facts = json.loads((out / "facts.json").read_text())
    assert facts["schema"] == 1 and facts["source"]["rows_used"] == 1142
    nar = json.loads((out / "narrative.json").read_text())
    assert nar["source"] == "rules" and nar["figures_checked"] > 10


def test_period_override(tmp_path, capsys):
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--period", "2026-07"]) == 0
    assert "2026-07" in capsys.readouterr().out
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--period", "1999-01"]) == 1
    assert "has no rows" in capsys.readouterr().err


def test_llm_flag_needs_a_key_and_uses_the_model_when_given(tmp_path, capsys, monkeypatch, anthropic):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--llm"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", anthropic.url)
    anthropic.reply = "Tickets opened were 224 in 2026-09, up 9.8% from 204 in 2026-08."
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--llm"]) == 0
    assert "summary by model" in capsys.readouterr().out
    md = (tmp_path / "report.md").read_text()
    assert "and checked: all" in md and "Tickets opened were 224" in md
    anthropic.reply = "Tickets opened were 300 in 2026-09."
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--llm"]) == 0
    cap = capsys.readouterr()
    assert "model summary rejected" in cap.err
    md = (tmp_path / "report.md").read_text()
    assert (
        "was rejected (figures that are not in the data: 300)" in md and "Tickets opened were 300" not in md
    )
    nar = json.loads((tmp_path / "narrative.json").read_text())
    assert nar["rejected_model_text"].startswith("Tickets opened were 300")


def test_fail_on_notes(tmp_path):
    assert main(["build", str(EXAMPLE), "--out", str(tmp_path), "--fail-on-notes"]) == 3
    clean = write_case(tmp_path / "c", ROWS) if (tmp_path / "c").mkdir() is None else None
    assert main(["build", str(clean), "--out", str(tmp_path / "o"), "--fail-on-notes"]) == 0


def test_check_command(tmp_path, capsys):
    out = tmp_path / "o"
    main(["build", str(EXAMPLE), "--out", str(out)])
    capsys.readouterr()
    good = tmp_path / "good.txt"
    good.write_text("Tickets opened: 224 in 2026-09, up 9.8% from 204.")
    assert main(["check", str(good), str(out / "facts.json")]) == 0
    assert "ok: " in capsys.readouterr().out
    bad = tmp_path / "bad.txt"
    bad.write_text("Tickets opened fell 9.8% to 224, and 17 customers left.")
    assert main(["check", str(bad), str(out / "facts.json")]) == 1
    out_text = capsys.readouterr().out
    assert "FAILED" in out_text and "17" in out_text and "direction contradicts" in out_text


def test_validate_and_errors(tmp_path, capsys):
    assert main(["validate", str(EXAMPLE)]) == 0
    assert "ok: 6 metrics, 2 breakdowns, 1147 rows" in capsys.readouterr().out
    broken = write_case(tmp_path, ROWS, SPEC.replace('agg = "sum"', 'agg = "total"'))
    assert main(["validate", str(broken)]) == 1
    assert "unknown agg 'total'" in capsys.readouterr().err
    assert main(["build", str(tmp_path / "missing.toml")]) == 1


@pytest.mark.parametrize("flag", ["--version"])
def test_version(flag, capsys):
    with pytest.raises(SystemExit) as e:
        main([flag])
    assert e.value.code == 0
