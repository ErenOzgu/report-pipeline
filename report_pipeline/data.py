"""Read the CSV with the types the spec declares, and keep count of what could not be read."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date

from .spec import Spec, SpecError

_NUM = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")


@dataclass
class Row:
    line: int  # line number in the file (the header is line 1)
    values: dict[str, object]


@dataclass
class Problem:
    count: int = 0
    lines: list[int] = field(default_factory=list)

    def add(self, line: int) -> None:
        self.count += 1
        if len(self.lines) < 3:
            self.lines.append(line)


@dataclass
class Table:
    rows: list[Row]
    rows_read: int
    sha256: str
    file_name: str
    skipped_no_date: Problem = field(default_factory=Problem)
    duplicates: Problem = field(default_factory=Problem)
    invalid: dict[str, Problem] = field(default_factory=dict)  # column -> unreadable values
    blank: dict[str, int] = field(default_factory=dict)  # column -> empty cells (in the rows that were used)


def parse_date(s: str) -> date | None:
    m = _DATE.match(s)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def load_table(spec: Spec) -> Table:
    try:
        raw = spec.path.read_bytes()
    except OSError as exc:
        raise SpecError(f"cannot read {spec.path}: {exc}") from exc
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=spec.delimiter)
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise SpecError(f"{spec.path.name} is empty") from None
    missing = [c for c in spec.columns if c not in header]
    if missing:
        names = ", ".join(repr(c) for c in missing)
        raise SpecError(f"{spec.path.name} has no column {names} (header: {', '.join(header)})")
    idx = {c: header.index(c) for c in spec.columns}

    table = Table(rows=[], rows_read=0, sha256=hashlib.sha256(raw).hexdigest(), file_name=spec.path.name)
    seen: set[object] = set()
    for cells in reader:
        line = reader.line_num  # the physical line, also when a quoted field spans several
        if not any(c.strip() for c in cells):
            continue  # an empty line is not a row
        table.rows_read += 1
        values: dict[str, object] = {}
        bad: list[str] = []
        blank: list[str] = []
        for col, typ in spec.columns.items():
            cell = cells[idx[col]].strip() if idx[col] < len(cells) else ""
            if cell == "":
                values[col] = None
                blank.append(col)
            elif typ == "number":
                if _NUM.match(cell):
                    values[col] = float(cell)
                else:
                    values[col] = None
                    bad.append(col)
            elif typ == "date":
                d = parse_date(cell)
                values[col] = d
                if d is None:
                    bad.append(col)
            else:
                values[col] = cell
        if values[spec.period_column] is None:
            table.skipped_no_date.add(line)
            continue
        if spec.key is not None:
            k = values[spec.key]
            if k is not None and k in seen:
                table.duplicates.add(line)
                continue
            seen.add(k)
        for col in bad:
            table.invalid.setdefault(col, Problem()).add(line)
        for col in blank:
            table.blank[col] = table.blank.get(col, 0) + 1
        table.rows.append(Row(line, values))
    return table
