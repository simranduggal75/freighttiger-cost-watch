"""Hand-written ground truth for the 10 notes, deliberately independent of costwatch.notes.

Used only by the evaluator to audit the system's citations. Each entry says which route a
note covers, the dates it is in force, and whether it describes a cost *increase*.
Source: context_notes.csv read by a human. Update this file if the notes file changes.
"""
from datetime import date

OPEN = date(9999, 12, 31)

NOTE_TRUTH = {
    "N001": dict(route="Chennai-Bangalore", start=date(2025, 2, 24), end=date(2025, 3, 8), raises_cost=True),
    "N002": dict(route="Ahmedabad-Mumbai", start=date(2025, 1, 20), end=date(2025, 1, 26), raises_cost=True),
    "N003": dict(route="*", start=date(2025, 5, 5), end=OPEN, raises_cost=True),
    "N004": dict(route="*", start=date(2024, 3, 11), end=date(2024, 3, 17), raises_cost=False),  # not in dataset
    "N005": dict(route="Mumbai-Delhi", start=date(2024, 7, 29), end=date(2024, 8, 4), raises_cost=False),
    "N006": dict(route="*", start=date(2025, 9, 22), end=date(2025, 9, 28), raises_cost=False),
    "N007": dict(route="Delhi-Jaipur", start=date(2024, 5, 20), end=date(2024, 5, 26), raises_cost=False),
    "N008": dict(route="Kolkata-Bhubaneswar", start=date(2025, 6, 9), end=date(2025, 6, 15), raises_cost=False),
    "N009": dict(route="Chennai-Bangalore", start=date(2025, 3, 17), end=date(2025, 3, 23), raises_cost=False),
    "N010": dict(route="*", start=date(2025, 10, 27), end=date(2025, 11, 2), raises_cost=False),
}
