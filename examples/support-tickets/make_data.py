"""Generate the synthetic support-ticket CSV used by the example and the tests.

Everything here is made up: ticket ids, customers ("Customer-017") and agents ("agent-03") are
sequence numbers, and the distributions are invented. The seed is fixed, so the file is reproducible:

    python examples/support-tickets/make_data.py > examples/support-tickets/tickets.csv
"""

from __future__ import annotations

import csv
import math
import random
import sys
from datetime import date, timedelta

SEED = 20261017
CATEGORIES = {  # name -> (share in April, share in September, median hours)
    "Billing": (0.22, 0.30, 9.0),
    "Login": (0.20, 0.17, 3.0),
    "Performance": (0.14, 0.16, 20.0),
    "Bug report": (0.24, 0.20, 30.0),
    "Feature request": (0.12, 0.10, 48.0),
    "Other": (0.08, 0.07, 6.0),
}
CHANNELS = {"Email": 0.52, "Chat": 0.33, "Phone": 0.15}
MONTHS = [(2026, 4, 168), (2026, 5, 181), (2026, 6, 190), (2026, 7, 176), (2026, 8, 205), (2026, 9, 224)]


def month_days(year: int, month: int) -> list[date]:
    d, out = date(year, month, 1), []
    while d.month == month:
        out.append(d)
        d += timedelta(days=1)
    return out


def pick(rng: random.Random, weights: dict[str, float]) -> str:
    names, w = zip(*weights.items(), strict=True)
    return rng.choices(names, weights=w)[0]


def main() -> None:
    rng = random.Random(SEED)
    rows: list[list[str]] = []
    n = 0
    for mi, (year, month, count) in enumerate(MONTHS):
        t = mi / (len(MONTHS) - 1)
        shares = {c: a + (b - a) * t for c, (a, b, _) in CATEGORIES.items()}
        days = [d for d in month_days(year, month) if d.weekday() < 6]  # no Sundays
        for _ in range(count):
            n += 1
            cat = pick(rng, shares)
            median = CATEGORIES[cat][2] * (1.0 + 0.04 * mi if cat == "Billing" else 1.0)
            hours = round(rng.lognormvariate(math.log(median), 0.8), 1)
            sat = None
            if rng.random() < 0.62:  # most customers do not answer the survey
                base = 4.6 - min(hours, 72) / 24.0 + rng.gauss(0, 0.7)
                sat = str(max(1, min(5, round(base))))
            rows.append(
                [
                    f"T-{100000 + n}",
                    rng.choice(days).isoformat(),
                    cat,
                    pick(rng, CHANNELS),
                    f"Customer-{rng.randint(1, 140):03d}",
                    f"agent-{rng.randint(1, 8):02d}",
                    str(hours),
                    sat or "",
                ]
            )
    # a few rows that are wrong the way real exports are wrong
    for i in rng.sample(range(len(rows)), 6):
        rows[i][6] = "n/a"
    for i in rng.sample(range(len(rows)), 2):
        rows[i][1] = ""
    for i in rng.sample(range(len(rows)), 3):
        rows.append(list(rows[i]))  # an exported twice
    rows.sort(key=lambda r: (r[1] == "", r[1], r[0]))
    out = csv.writer(sys.stdout, lineterminator="\n")
    out.writerow(
        [
            "ticket_id",
            "opened",
            "category",
            "channel",
            "customer",
            "agent",
            "resolution_hours",
            "satisfaction",
        ]
    )
    out.writerows(rows)


if __name__ == "__main__":
    main()
