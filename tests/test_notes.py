from datetime import date

from costwatch.notes import classify_effect, parse_note, parse_window


def test_explicit_range_is_parsed_with_year_from_note_date():
    start, end, persistent, _ = parse_window("closed from Feb 24 to Mar 8 for repairs", date(2025, 2, 24))
    assert (start, end, persistent) == (date(2025, 2, 24), date(2025, 3, 8), False)


def test_range_wrapping_new_year():
    start, end, _, _ = parse_window("disruption from Dec 28 to Jan 3", date(2024, 12, 28))
    assert end == date(2025, 1, 3)


def test_starting_this_week_is_open_ended_from_that_weeks_monday():
    start, end, persistent, _ = parse_window("rates rose starting this week", date(2025, 5, 7))  # a Wednesday
    assert start == date(2025, 5, 5) and end is None and persistent


def test_note_without_range_covers_its_own_week_only():
    start, end, persistent, _ = parse_window("a festival week surcharge", date(2025, 1, 22))
    assert (start, end, persistent) == (date(2025, 1, 20), date(2025, 1, 26), False)


def test_no_effect_cues_beat_increase_cues():
    # contains "delays" and "costs" but explicitly says costs were not affected
    assert classify_effect("Maintenance caused minor delays; costs were not significantly affected.") == "none"
    assert classify_effect("compliance costs were absorbed by transporters without a rate change") == "none"


def test_increase_and_decrease_detected():
    assert classify_effect("a temporary surcharge was applied") == "increase"
    assert classify_effect("improved road conditions after resurfacing") == "decrease"


def test_unknown_language_defaults_to_no_effect():
    assert classify_effect("the weather was pleasant") == "none"   # never guess a reason


def test_magnitude_range_extracted_only_for_increases():
    n = parse_note("N", "2025-05-05", "All Routes", "Diesel rose starting this week, costs up by roughly 5-7%.")
    assert n.magnitude_pct == (5.0, 7.0) and n.route is None
    quiet = parse_note("M", "2025-05-05", "All Routes", "No change; a 5-7% fee was absorbed without a rate change.")
    assert quiet.magnitude_pct is None
