"""Run the whole pipeline 3 times in fresh processes and prove the outputs are identical.

Each run uses a different PYTHONHASHSEED so any accidental dependence on dict/set ordering
would show up. Writes outputs/repro_report.md.   Usage: python scripts/repro_check.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["output.csv", "weekly_metrics_full.csv", "note_facts.csv", "retrieval_trace.csv", "run_log.json", "cost_log.md"]
RUNS = 3


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    digests = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(RUNS):
            out = Path(tmp) / f"run{i + 1}"
            env = {**os.environ, "PYTHONHASHSEED": str(1000 + 7 * i)}
            subprocess.run([sys.executable, "-m", "costwatch", "run", "--out-dir", str(out)],
                           cwd=ROOT, env=env, check=True, capture_output=True)
            digests.append({f: sha(out / f) for f in FILES})
            print(f"run {i + 1} done")

    lines = ["# Reproducibility check", "",
             f"{RUNS} untouched runs, each a fresh process with a different PYTHONHASHSEED.", "",
             "| file | " + " | ".join(f"run {i + 1}" for i in range(RUNS)) + " | identical |",
             "|---|" + "---|" * RUNS + "---|"]
    all_ok = True
    for f in FILES:
        hashes = [d[f] for d in digests]
        same = len(set(hashes)) == 1
        all_ok &= same
        lines.append(f"| {f} | " + " | ".join(h[:12] for h in hashes) + f" | {'yes' if same else '**NO**'} |")
    lines += ["", f"**Result: {'IDENTICAL - flags, numbers, cited notes and wording match byte for byte' if all_ok else 'MISMATCH'}.**"]
    (ROOT / "outputs" / "repro_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
