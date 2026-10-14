"""Turn free-text notes into structured, checkable facts.

A note can only justify a cost rise if we can state, in code, (a) which routes it covers,
(b) when it is in force, and (c) that it says costs went *up*. Anything we cannot establish
defaults to "no effect", so a note we misread can never produce a false "justified".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

ALL_ROUTES = "all routes"

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# Checked first: any of these means the note gives no reason for a cost rise.
NO_EFFECT_CUES = [
    "not significantly affected", "were not affected", "no significant disruption",
    "no major disruption", "remained stable", "remained normal", "returned to normal",
    "without a rate change", "not part of this dataset", "absorbed by transporters",
]
DECREASE_CUES = ["improved road conditions", "prices fell", "prices dropped", "cheaper", "cost reduction"]
INCREASE_CUES = ["surcharge", "higher", "pushing up", "rose", "price hike", "went up",
                 "detour", "disrupted", "increase"]

_RANGE = re.compile(r"from\s+([A-Za-z]{3,9})\.?\s+(\d{1,2})\s+to\s+([A-Za-z]{3,9})\.?\s+(\d{1,2})", re.I)
_PCT_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*%")
_STARTS = re.compile(r"\bstarting\s+(?:this\s+week|from)\b", re.I)


@dataclass(frozen=True)
class NoteFacts:
    note_id: str
    note_date: date
    applies_to: str
    text: str
    route: str | None          # None means "all routes"
    effect: str                # "increase" | "decrease" | "none"
    window_start: date
    window_end: date | None    # None = open-ended (a persistent change)
    persistent: bool
    magnitude_pct: tuple[float, float] | None
    window_basis: str          # how the window was derived, for the audit trail

    @property
    def covers_all_routes(self) -> bool:
        return self.route is None

    def effective_end(self, baseline_weeks: int) -> date:
        """Last day this note can explain a rise measured against an N-week average.

        A persistent change (e.g. a fuel price step) stops showing up as a *rise* once the
        trailing baseline consists entirely of post-change weeks.
        """
        if self.window_end is not None:
            return self.window_end
        return self.window_start + timedelta(weeks=baseline_weeks) - timedelta(days=1)

    def gap_days(self, week_of: date, baseline_weeks: int) -> int:
        """0 if the Monday-Sunday week overlaps the note's period, else days between them."""
        week_end = week_of + timedelta(days=6)
        if week_end < self.window_start:
            return (self.window_start - week_end).days
        end = self.effective_end(baseline_weeks)
        return (week_of - end).days if week_of > end else 0


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _month_day(token_month: str, day: str, year: int) -> date | None:
    month = MONTHS.get(token_month[:3].lower())
    if month is None:
        return None
    try:
        return date(year, month, int(day))
    except ValueError:
        return None


def classify_effect(text: str) -> str:
    low = text.lower()
    if any(cue in low for cue in NO_EFFECT_CUES):
        return "none"
    if any(cue in low for cue in DECREASE_CUES):
        return "decrease"
    if any(cue in low for cue in INCREASE_CUES):
        return "increase"
    return "none"


def parse_window(text: str, note_date: date) -> tuple[date, date | None, bool, str]:
    """Return (start, end, persistent, basis). Order: explicit range, 'starting this week', note week."""
    m = _RANGE.search(text)
    if m:
        start = _month_day(m.group(1), m.group(2), note_date.year)
        end = _month_day(m.group(3), m.group(4), note_date.year)
        if start and end:
            if end < start:  # range wraps a year boundary
                end = end.replace(year=end.year + 1)
            return start, end, False, "explicit date range in the note"
    if _STARTS.search(text):
        return monday_of(note_date), None, True, "'starting this week' (open-ended change)"
    start = monday_of(note_date)
    return start, start + timedelta(days=6), False, "the note's own week (no explicit range)"


def parse_note(note_id: str, note_date: str, applies_to: str, text: str) -> NoteFacts:
    d = pd.Timestamp(note_date).date()
    scope = applies_to.strip()
    route = None if scope.lower() == ALL_ROUTES else scope
    effect = classify_effect(text)
    start, end, persistent, basis = parse_window(text, d)
    pct = _PCT_RANGE.search(text)
    magnitude = (float(pct.group(1)), float(pct.group(2))) if pct and effect == "increase" else None
    return NoteFacts(note_id, d, scope, text.strip(), route, effect, start, end, persistent, magnitude, basis)


def load_notes(path) -> list[NoteFacts]:
    df = pd.read_csv(path, dtype=str)
    notes = [parse_note(r.note_id, r.date, r.applies_to, r.note) for r in df.itertuples()]
    return sorted(notes, key=lambda n: n.note_id)
