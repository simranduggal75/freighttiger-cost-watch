"""The trust gate: decide "justified" vs "unexplained" from structured note facts only.

A note justifies a flagged week only if ALL of these hold:
  1. scope     - it names this route, or all routes;
  2. effect    - it says costs went up (not "no impact", not a decrease);
  3. window    - the week overlaps the period the note is in force (a persistent change such
                 as a fuel step only counts while the 8-week baseline still straddles it);
  4. magnitude - if the note quantifies the effect, the observed rise is no bigger than that
                 (plus ordinary noise), so a +30% jump is not "explained" by a 5-7% fuel move;
  5. relative  - a cause that hits all routes equally cannot explain a gap vs similar routes.
Anything else is "unexplained". There is no fuzzy middle: no note -> flagged for review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from . import config
from .notes import NoteFacts


@dataclass(frozen=True)
class Verdict:
    justified: bool
    note: NoteFacts | None            # justifying note, or the nearest rejected one
    code: str                         # machine-readable outcome
    detail: str = ""                  # short human phrase explaining a rejection
    nearby: tuple["Verdict", ...] = ()  # other rejected notes close in time (for the explanation)


def expected_rise_pct(note: NoteFacts, week_of: date) -> float | None:
    """Largest rise vs the 8-week average this note can account for in this week."""
    if note.magnitude_pct is None:
        return None
    hi = note.magnitude_pct[1] / 100
    if not note.persistent:
        return hi * 100
    weeks_in = max(0, (week_of - note.window_start).days // 7)
    baseline_share_after_step = min(weeks_in, config.BASELINE_WEEKS) / config.BASELINE_WEEKS
    return ((1 + hi) / (1 + hi * baseline_share_after_step) - 1) * 100


def check_note(note: NoteFacts, route: str, week_of: date, vs_own_pct: float,
               own_spread: float, trigger: str) -> Verdict:
    if note.route is not None and note.route.lower() != route.lower():
        return Verdict(False, note, "wrong_route", f"covers {note.route}, not {route}")
    if note.effect == "none":
        return Verdict(False, note, "no_effect", "describes no cost impact")
    if note.effect == "decrease":
        return Verdict(False, note, "decrease", "describes an improvement, not a cost rise")

    week_end = week_of + timedelta(days=6)
    if week_end < note.window_start:
        return Verdict(False, note, "not_yet", f"only takes effect from {note.window_start}")
    end = note.effective_end(config.BASELINE_WEEKS)
    if week_of > end:
        why = (f"covered {note.window_start} to {end}, which ended before this week"
               if note.window_end is not None else
               f"is a step change from {note.window_start} that the route's 8-week average already absorbs")
        return Verdict(False, note, "window_ended", why)

    if note.covers_all_routes and "similar-routes" in trigger:
        return Verdict(False, note, "all_routes_vs_peers",
                       "applies to all routes equally, so it cannot explain a gap versus similar routes")

    expected = expected_rise_pct(note, week_of)
    if expected is not None and vs_own_pct - expected > config.Z_MARKET * own_spread:
        return Verdict(False, note, "magnitude",
                       f"accounts for at most about {expected:.0f}% of a rise, "
                       f"but this week is {vs_own_pct:+.1f}% above the route's past average")
    return Verdict(True, note, "justified", "")


def decide(ranked_notes: list[NoteFacts], route: str, week_of: date, vs_own_pct: float,
           own_spread: float, trigger: str) -> Verdict:
    """Run the gate over the retrieved notes (already scope-filtered, best match first)."""
    results = [check_note(n, route, week_of, vs_own_pct, own_spread, trigger) for n in ranked_notes]

    passing = [r for r in results if r.justified]
    if passing:  # route-specific beats all-routes; ties keep retrieval order (stable sort)
        return sorted(passing, key=lambda r: r.note.covers_all_routes)[0]

    near = sorted(
        ((r.note.gap_days(week_of, config.BASELINE_WEEKS), rank, r) for rank, r in enumerate(results)
         if r.note.gap_days(week_of, config.BASELINE_WEEKS) <= config.NEAR_NOTE_DAYS),
        key=lambda t: (t[0], t[1]),
    )
    if not near:
        return Verdict(False, None, "no_note", "no note covers this route in this period")
    best = near[0][2]
    return Verdict(False, best.note, best.code, best.detail, nearby=tuple(t[2] for t in near[1:2]))
