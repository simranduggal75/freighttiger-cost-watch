"""Adversarial cases for the trust gate: each one is a way a careless system would hallucinate."""
from datetime import date

from costwatch.notes import parse_note
from costwatch.verdict import check_note, decide

ROUTE = "Chennai-Bangalore"


def note(nid, d, applies, text):
    return parse_note(nid, d, applies, text)


FLOOD = note("N1", "2025-02-24", ROUTE,
             "Heavy flooding disrupted truck movement from Feb 24 to Mar 8, forcing detours and "
             "higher trip costs. Roads were passable again by Mar 9.")
DIESEL = note("N3", "2025-05-05", "All Routes",
              "Diesel prices rose nationwide starting this week, pushing up costs across all routes by roughly 5-7%.")
NEUTRAL = note("N5", "2025-03-03", ROUTE, "Maintenance caused minor delays; costs were not significantly affected.")
NORMAL = note("N9", "2025-03-17", ROUTE, "The route returned to normal conditions after repairs were completed.")
OTHER_ROUTE = note("N2", "2025-02-24", "Delhi-Jaipur",
                   "Heavy flooding disrupted truck movement from Feb 24 to Mar 8, with higher trip costs.")


def verdict(notes, week, vs_own=20.0, trigger="own-history", spread=3.0, route=ROUTE):
    return decide(notes, route, date.fromisoformat(week), vs_own, spread, trigger)


def test_note_in_window_justifies():
    v = verdict([FLOOD], "2025-02-24")
    assert v.justified and v.note.note_id == "N1"


def test_week_overlapping_end_of_window_still_justified():
    assert verdict([FLOOD], "2025-03-03").justified      # Mar 3-9 overlaps Feb 24-Mar 8


def test_week_after_window_is_not_justified():
    v = verdict([FLOOD], "2025-03-10")
    assert not v.justified and v.code == "window_ended"


def test_note_for_a_different_route_never_applies():
    v = verdict([OTHER_ROUTE], "2025-02-24")
    assert not v.justified


def test_note_saying_costs_not_affected_does_not_justify():
    assert NEUTRAL.effect == "none"
    assert not verdict([NEUTRAL], "2025-03-03").justified


def test_returned_to_normal_is_not_a_reason_for_a_rise():
    assert NORMAL.effect == "none"
    assert not verdict([NORMAL], "2025-03-17").justified


def test_note_that_starts_later_cannot_explain_earlier_week():
    v = check_note(DIESEL, ROUTE, date(2025, 3, 10), 20.0, 3.0, "own-history")
    assert not v.justified and v.code == "not_yet"
    assert not verdict([DIESEL], "2025-03-10").justified     # and decide() agrees


def test_note_far_from_the_week_is_not_cited_at_all():
    v = verdict([DIESEL], "2024-11-11")                      # six months before the note
    assert not v.justified and v.note is None and v.code == "no_note"


def test_all_routes_note_justifies_a_matching_sized_rise():
    assert verdict([DIESEL], "2025-05-05", vs_own=6.5).justified


def test_rise_far_bigger_than_quantified_effect_is_not_justified():
    v = verdict([DIESEL], "2025-05-12", vs_own=11.6)
    assert not v.justified and v.code == "magnitude"


def test_persistent_step_expires_once_baseline_absorbs_it():
    v = verdict([DIESEL], "2025-07-14", vs_own=6.0)          # 10 weeks after the step
    assert not v.justified and v.code == "window_ended"
    assert not verdict([DIESEL], "2025-09-15", vs_own=6.0).justified


def test_all_routes_cause_cannot_explain_gap_to_peers():
    v = verdict([DIESEL], "2025-05-05", vs_own=6.0, trigger="similar-routes")
    assert not v.justified and v.code == "all_routes_vs_peers"


def test_no_notes_means_no_citation():
    v = verdict([], "2025-05-05")
    assert not v.justified and v.note is None


def test_route_specific_note_preferred_over_all_routes():
    v = verdict([DIESEL, FLOOD], "2025-02-24")
    assert v.justified and v.note.note_id == "N1"
