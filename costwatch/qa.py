"""Ask questions about the findings in plain English. Answers come only from output.csv /
weekly_metrics_full.csv / note_facts - nothing is generated, so nothing can be invented."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import config

MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]


def _find_routes(question: str, routes: list[str]) -> list[str]:
    q = question.lower()
    exact = [r for r in routes if all(part.lower() in q for part in r.split("-"))]
    if exact:
        return exact
    return [r for r in routes if any(part.lower() in q for part in r.split("-"))]


def _find_month(question: str):
    q = question.lower()
    month = next((i + 1 for i, m in enumerate(MONTHS) if re.search(rf"\b{m}\b|\b{m[:3]}\b", q)), None)
    year = re.search(r"\b(20\d{2})\b", q)
    return month, int(year.group(1)) if year else None


class Assistant:
    def __init__(self, out_dir: Path = config.OUT_DIR):
        out_dir = Path(out_dir)
        self.review = pd.read_csv(out_dir / "output.csv", dtype=str, keep_default_na=False)
        self.full = pd.read_csv(out_dir / "weekly_metrics_full.csv", keep_default_na=False)
        self.facts = pd.read_csv(out_dir / "note_facts.csv", dtype=str, keep_default_na=False)
        self.review["_dt"] = pd.to_datetime(self.review.week_of)

    def ask(self, question: str) -> str:
        note = re.search(r"\bN\d{3}\b", question.upper())
        if note:
            return self._note(note.group(0))
        routes = _find_routes(question, sorted(self.full.route.unique()))
        month, year = _find_month(question)
        if routes or month:
            return self._findings(routes, month, year)
        if re.search(r"unexplained|flagged|review|suspicious|worst", question.lower()):
            return self._findings([], None, None, only_flagged=True)
        return ("I can answer from this run's results. Try: 'why did Chennai-Bangalore get pricier in "
                "March 2025?', 'which routes are unexplained?', or 'what does N003 say?'")

    def _note(self, note_id: str) -> str:
        row = self.facts[self.facts.note_id == note_id]
        if row.empty:
            return f"There is no note {note_id} in the notes file."
        r = row.iloc[0]
        raw = pd.read_csv(config.DATA_DIR / config.NOTES_FILE, dtype=str)
        text = raw.loc[raw.note_id == note_id, "note"].iloc[0] if (raw.note_id == note_id).any() else ""
        return (f"{note_id} ({r.note_date}, applies to {r.applies_to}): \"{text}\" "
                f"Read as: effect on cost = {r.effect}; in force {r.window_start} to {r.window_end}.")

    def _findings(self, routes, month, year, only_flagged: bool = False) -> str:
        df = self.review
        if routes:
            df = df[df.route.isin(routes)]
        if month:
            df = df[df._dt.dt.month == month]
        if year:
            df = df[df._dt.dt.year == year]
        if only_flagged:
            df = df[df.flagged == "Yes"]
        scope = ", ".join(routes) if routes else "any route"
        when = f" in {MONTHS[month - 1].title()}{' ' + str(year) if year else ''}" if month else ""
        if df.empty:
            return (f"Nothing for {scope}{when}: no week crossed the review threshold in this run, "
                    f"so I have no unusual cost rise to explain there.")
        lines = [f"From this run's results, {len(df)} week(s) for {scope}{when}:"]
        for r in df.itertuples():
            verdict = "FLAGGED (unexplained)" if r.flagged == "Yes" else f"justified by {r.matched_note_id}"
            lines.append(f"- {r.route}, week of {r.week_of}: {r.cost_per_tonne_km} per tonne-km, "
                         f"{r.vs_own_history}; {verdict}. {r.reason}")
        return "\n".join(lines)
