"""The summary paragraph: written by rules, or by a model that is checked and, if it fails, replaced."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import fmt
from .facts import allowed_numbers, for_model

DEFAULT_MODEL = "claude-sonnet-5-5"
API_VERSION = "2023-06-01"

SYSTEM = """You write the summary paragraph of a business report from a list of verified facts.

Rules:
- Use only the facts you are given. Do not add causes, forecasts or comparisons that are not in them.
- Write every number exactly as it appears in the facts, as digits. Do not compute new numbers: no sums, \
differences, ratios, averages, and no rounding or rewording of a figure ("about 400" is not allowed).
- Say "up" or "down" only as the facts' signs say. If a note says a period is incomplete, mention it.
- 3 to 5 sentences of plain prose. No lists, no headings, no preamble."""

UP = {
    "up",
    "rose",
    "risen",
    "rise",
    "rises",
    "increase",
    "increased",
    "increases",
    "grew",
    "grow",
    "grown",
    "growth",
    "higher",
    "climbed",
    "jumped",
    "gained",
    "more",
}
DOWN = {
    "down",
    "fell",
    "fallen",
    "falls",
    "fall",
    "decrease",
    "decreased",
    "decreases",
    "dropped",
    "drop",
    "lower",
    "declined",
    "decline",
    "shrank",
    "slipped",
    "less",
    "fewer",
    "reduced",
}
_WORD = re.compile(r"[A-Za-z]+")


# -- the deterministic summary -------------------------------------------------------------------
def deterministic_summary(facts: dict) -> str:
    sentences: list[str] = []
    period, prev = facts["period"], facts["previous_period"]
    for m in facts["metrics"]:
        cur = m["current_text"]
        if m["previous_text"] and m["delta_text"]:
            sign = m["delta_sign"]
            if sign == 0:
                sentences.append(f"{m['label']}: {cur} in {period}, unchanged from {prev}.")
                continue
            word = "up" if sign > 0 else "down"
            amount = m["delta_text"].lstrip("+-")
            sentences.append(
                f"{m['label']}: {cur} in {period}, {word} {amount} from {m['previous_text']} in {prev}."
            )
        elif m["previous_text"]:
            sentences.append(f"{m['label']}: {cur} in {period} ({m['previous_text']} in {prev}).")
        else:
            sentences.append(f"{m['label']}: {cur} in {period}.")
    for b in facts["breakdowns"]:
        top = next((r for r in b["rows"] if not r["name"].startswith("Other (")), None)
        if top and top["share_text"]:
            first = b["metrics"][0]
            sentences.append(
                f"The largest {b['by']} is {top['name']} with {top['values'][first]} "
                f"({top['share_text']} of the total)."
            )
    for n in facts["notes"]:
        if "incomplete" in n:
            sentences.append(n)
    return " ".join(sentences)


# -- the check -----------------------------------------------------------------------------------
@dataclass
class Check:
    unknown_numbers: list[str] = field(default_factory=list)
    wrong_direction: list[str] = field(default_factory=list)
    numbers_checked: int = 0

    @property
    def ok(self) -> bool:
        return not self.unknown_numbers and not self.wrong_direction

    def problems(self) -> list[str]:
        out = []
        if self.unknown_numbers:
            out.append("figures that are not in the data: " + ", ".join(self.unknown_numbers))
        for s in self.wrong_direction:
            out.append("direction contradicts the data: " + s)
        return out


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)


def _direction_near(sentence: str, start: int, end: int, reach: int = 28) -> str | None:
    best: tuple[int, str] | None = None
    for w in _WORD.finditer(sentence):
        word = w.group(0).lower()
        kind = "up" if word in UP else ("down" if word in DOWN else None)
        if kind is None:
            continue
        dist = start - w.end() if w.end() <= start else (w.start() - end if w.start() >= end else 0)
        if dist <= reach and (best is None or dist < best[0]):
            best = (dist, kind)
    return best[1] if best else None


def check_text(text: str, facts: dict) -> Check:
    """Every figure must be in the facts, and "up" or "down" next to a change must match its sign."""
    res = Check()
    allowed = allowed_numbers(facts)
    seen_unknown: dict[str, None] = {}
    # change figures -> sign(s) of the metrics they belong to
    change: dict[object, set[int]] = {}
    for m in facts["metrics"]:
        if m["delta_sign"] in (1, -1):
            for t in (m["delta_text"], m["delta_abs_text"]):
                for tok in fmt.numbers_in(t):
                    change.setdefault(fmt.normalise(tok), set()).add(m["delta_sign"])

    for sent in _sentences(text):
        for m in fmt.NUMBER.finditer(sent):
            res.numbers_checked += 1
            val = fmt.normalise(m.group(0))
            if val not in allowed:
                seen_unknown.setdefault(m.group(0), None)
                continue
            signs = change.get(val)
            if signs and len(signs) == 1:
                direction = _direction_near(sent, m.start(), m.end())
                expected = "up" if next(iter(signs)) > 0 else "down"
                if direction and direction != expected:
                    snippet = sent.strip()
                    if snippet not in res.wrong_direction:
                        res.wrong_direction.append(snippet)
    res.unknown_numbers = list(seen_unknown)
    return res


# -- the model step ------------------------------------------------------------------------------
class ModelError(Exception):
    pass


def call_model(
    prompt: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    max_tokens: int = 500,
    timeout: float = 60,
) -> str:
    base = (base_url or os.environ.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com").rstrip("/")
    body = json.dumps(
        {
            "model": model or os.environ.get("REPORT_PIPELINE_MODEL") or DEFAULT_MODEL,
            "max_tokens": max_tokens,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode()
    req = urllib.request.Request(
        base + "/v1/messages",
        data=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
            "user-agent": "report-pipeline",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise ModelError(f"API returned {exc.code}: {exc.read(300).decode('utf-8', 'replace')}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ModelError(f"cannot reach the API: {exc}") from exc
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    if not text:
        raise ModelError("the API returned no text")
    return text


@dataclass
class Narrative:
    text: str
    source: str  # "rules" | "model"
    model: str = ""
    check: Check | None = None
    rejected: str = ""  # the model's text, when it failed the check
    rejection_reasons: list[str] = field(default_factory=list)
    error: str = ""


def summarise(
    facts: dict,
    use_model: bool = False,
    api_key: str = "",
    model: str | None = None,
    base_url: str | None = None,
) -> Narrative:
    fallback = deterministic_summary(facts)
    if not use_model:
        return Narrative(text=fallback, source="rules", check=check_text(fallback, facts))
    used = model or os.environ.get("REPORT_PIPELINE_MODEL") or DEFAULT_MODEL
    try:
        text = call_model(for_model(facts), api_key, model=used, base_url=base_url)
    except ModelError as exc:
        return Narrative(
            text=fallback, source="rules", model=used, error=str(exc), check=check_text(fallback, facts)
        )
    chk = check_text(text, facts)
    if chk.ok:
        return Narrative(text=text, source="model", model=used, check=chk)
    return Narrative(
        text=fallback,
        source="rules",
        model=used,
        check=check_text(fallback, facts),
        rejected=text,
        rejection_reasons=chk.problems(),
    )
