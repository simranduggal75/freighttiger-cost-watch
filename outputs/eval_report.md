# Evaluation report

## 1. Labeled set

22/22 labeled route-weeks behave as expected.

| result | route | week_of | expected | got |
|---|---|---|---|---|
| PASS | Delhi-Jaipur | 2024-11-11 | flagged | Yes / - |
| PASS | Delhi-Jaipur | 2024-11-18 | flagged | Yes / - |
| PASS | Chennai-Bangalore | 2025-03-10 | flagged | Yes / - |
| PASS | Chennai-Bangalore | 2025-03-17 | flagged | Yes / - |
| PASS | Mumbai-Pune | 2025-09-15 | flagged | Yes / - |
| PASS | Mumbai-Pune | 2025-11-17 | flagged | Yes / - |
| PASS | Mumbai-Pune | 2025-12-01 | flagged | Yes / - |
| PASS | Mumbai-Delhi | 2025-05-12 | flagged | Yes / - |
| PASS | Ahmedabad-Mumbai | 2025-01-20 | justified N002 | No (justified) / N002 |
| PASS | Chennai-Bangalore | 2025-02-24 | justified N001 | No (justified) / N001 |
| PASS | Chennai-Bangalore | 2025-03-03 | justified N001 | No (justified) / N001 |
| PASS | Delhi-Jaipur | 2025-05-05 | justified N003 | No (justified) / N003 |
| PASS | Mumbai-Delhi | 2025-05-05 | justified N003 | No (justified) / N003 |
| PASS | Mumbai-Pune | 2025-05-05 | justified N003 | No (justified) / N003 |
| PASS | Mumbai-Delhi | 2024-07-29 | normal | absent |
| PASS | Delhi-Jaipur | 2024-05-20 | normal | absent |
| PASS | Kolkata-Bhubaneswar | 2025-06-09 | normal | absent |
| PASS | Delhi-Chennai | 2024-02-05 | normal | absent |
| PASS | Ahmedabad-Mumbai | 2024-04-22 | normal | absent |
| PASS | Ahmedabad-Mumbai | 2025-01-27 | normal | absent |
| PASS | Kolkata-Bhubaneswar | 2024-06-17 | normal | absent |
| PASS | Chennai-Bangalore | 2025-04-07 | normal | absent |

Caveat: labels were written from the notes and a read of the data, so this is a regression set, not independent ground truth.

## 2. Citation audit (hallucination check)

7 justified rows re-checked against a hand-written truth table (`eval/note_truth.py`): **0 problems**.


## 3. Threshold sensitivity

| Z_STRONG | Z_MARKET | review rows | false alarms in quiet Jan-Oct 2024 |
|---|---|---|---|
| 2.5 | 1.25 | 32 | 1 |
| 2.5 | 1.5 | 27 | 1 |
| 2.5 | 2.0 | 25 | 1 |
| 3.0 | 1.25 | 27 | 0 |
| 3.0 | 1.5 | 22 | 0 | <- chosen
| 3.0 | 2.0 | 18 | 0 |
| 3.5 | 1.25 | 24 | 0 |
| 3.5 | 1.5 | 19 | 0 |
| 3.5 | 2.0 | 15 | 0 |
