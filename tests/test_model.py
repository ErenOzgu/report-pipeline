"""The optional model step, against a local server that has the shape of the Messages API."""

import json

from report_pipeline.narrative import SYSTEM, check_text, deterministic_summary, summarise

GOOD = "Orders rose 25.0% to 5 in 2026-09, from 4 in 2026-08. Revenue was 175.00 EUR, up 75.0%."


def run(anthropic, facts, reply, **kw):
    anthropic.reply = reply
    return summarise(facts, use_model=True, api_key="sk-test", base_url=anthropic.url, **kw)


def test_a_text_with_only_known_figures_is_used(anthropic, case):
    _, _, _, facts = case
    n = run(anthropic, facts, GOOD)
    assert n.source == "model" and n.text == GOOD and not n.rejected
    assert n.check.numbers_checked >= 6


def test_a_made_up_figure_rejects_the_text_and_the_rules_summary_is_used(anthropic, case):
    _, _, _, facts = case
    n = run(anthropic, facts, "Orders were 5 in 2026-09. Revenue reached 190.00 EUR, a record.")
    assert n.source == "rules" and n.text == deterministic_summary(facts)
    assert "190.00" in n.rejected
    assert n.rejection_reasons == ["figures that are not in the data: 190.00"]


def test_a_contradicting_direction_rejects_the_text(anthropic, case):
    _, _, _, facts = case
    n = run(anthropic, facts, "Orders fell 25.0% to 5 in 2026-09 from 4 in 2026-08.")
    assert n.source == "rules" and "direction contradicts" in n.rejection_reasons[0]


def test_an_api_error_falls_back_without_raising(anthropic, case):
    _, _, _, facts = case
    anthropic.status = 529
    n = run(anthropic, facts, GOOD)
    assert n.source == "rules" and "529" in n.error and n.text == deterministic_summary(facts)


def test_an_unreachable_api_falls_back(anthropic, case):
    _, _, _, facts = case
    url = anthropic.url
    anthropic.close()
    n = summarise(facts, use_model=True, api_key="k", base_url=url)
    assert n.source == "rules" and "cannot reach the API" in n.error


def test_the_request_carries_the_facts_and_never_a_row(anthropic, example):
    _, table, _, facts = example
    run(anthropic, facts, "x")
    req = anthropic.requests[-1]
    body = json.loads(req["body"])
    content = body["messages"][0]["content"]
    assert req["path"] == "/v1/messages"
    assert req["headers"]["x-api-key"] == "sk-test" and req["headers"]["anthropic-version"] == "2023-06-01"
    assert body["system"] == SYSTEM
    # the aggregates are there...
    assert "Tickets opened: 224 in 2026-09" in content and "By category" in content
    # ...and nothing that only exists in the rows
    raw = req["body"].decode()
    for needle in ("T-1000", "Customer-0", "agent-0", "sha256"):
        assert needle not in raw, f"{needle!r} from the data reached the API"
    sample = table.rows[10].values
    assert str(sample["ticket_id"]) not in raw


def test_the_prompt_tells_the_model_the_rules_the_checker_enforces():
    for phrase in ("exactly as it appears", "as digits", "Do not compute new numbers", "up", "down"):
        assert phrase in SYSTEM


def test_a_rejected_text_is_kept_for_inspection_and_would_fail_the_check(anthropic, case):
    _, _, _, facts = case
    n = run(anthropic, facts, "Revenue reached 190.00 EUR.")
    assert not check_text(n.rejected, facts).ok
