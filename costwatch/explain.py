"""Plain-English reasons, assembled from verified facts only.

Every sentence is a template filled from (a) numbers we computed and (b) the note's own
text, quoted verbatim. Nothing is free-generated, so an explanation cannot invent a cause.
"""
from __future__ import annotations

from datetime import date

from . import config
from .verdict import Verdict


def fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


def _rise(vs_own: float, vs_peer: float | None) -> str:
    text = f"{fmt_pct(vs_own)} vs this route's past average"
    if vs_peer is not None:
        text += f" and {fmt_pct(vs_peer)} vs similar-length routes"
    return text


def render_reason(v: Verdict, week_of: date, vs_own: float, vs_peer: float | None) -> str:
    rise = _rise(vs_own, vs_peer)

    if v.justified:
        n = v.note
        end = n.effective_end(config.BASELINE_WEEKS)
        magnitude = ""
        if n.magnitude_pct:
            lo, hi = n.magnitude_pct
            magnitude = f" The note puts the effect at roughly {lo:g}-{hi:g}%, consistent with this rise."
        return (f"Matches note {n.note_id} dated {n.note_date}: \"{n.text}\" "
                f"The week of {week_of} falls inside the note's window ({n.window_start} to {end}).{magnitude} "
                f"The cost rise ({rise}) has a clear explanation.")

    if v.note is None:
        return (f"No matching note found for this route or date range. "
                f"Cost rise ({rise}) looks unexplained and worth a human review.")

    n = v.note
    text = (f"No genuine justification found. Closest note: {n.note_id} ({n.note_date}): \"{n.text}\" "
            f"That note {v.detail}.")
    if v.nearby:
        o = v.nearby[0]
        text += f" Another nearby note, {o.note.note_id} ({o.note.note_date}), {o.detail}."
        verdict_line = f" Neither explains this week's cost rise ({rise})."
    else:
        verdict_line = f" It does not explain this week's cost rise ({rise})."
    return text + verdict_line + " Flagged for human review."
