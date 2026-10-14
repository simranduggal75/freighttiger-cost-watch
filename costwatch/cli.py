"""Command line: `python -m costwatch run` and `python -m costwatch ask "..."`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import config, pipeline, qa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="costwatch", description="Shipping-cost watchdog")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="analyse shipments and write outputs/")
    run.add_argument("--data-dir", type=Path, default=config.DATA_DIR)
    run.add_argument("--out-dir", type=Path, default=config.OUT_DIR)
    run.add_argument("--retriever", choices=["auto", "embeddings", "tfidf"], default="auto")

    ask = sub.add_parser("ask", help="ask a question about the findings")
    ask.add_argument("question")
    ask.add_argument("--out-dir", type=Path, default=config.OUT_DIR)

    args = parser.parse_args(argv)
    if args.command == "run":
        summary = pipeline.run(args.data_dir, args.out_dir, args.retriever)
        print(json.dumps({k: v for k, v in summary.items() if k != "settings"}, indent=2))
    else:
        print(qa.Assistant(args.out_dir).ask(args.question))
    return 0
