import argparse
import json
from pathlib import Path
from .runner import experiment


def main():
    parser = argparse.ArgumentParser(description="Provisional Session 2 four-run comparison")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing outputs are never overwritten")
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--labels", type=Path, help="Optional instructor-only labels outside participant files")
    args = parser.parse_args()
    rows = experiment(args.output, json.loads(args.config.read_text()), mode=args.mode,
                      labels=json.loads(args.labels.read_text()) if args.labels else None)
    for row in rows:
        print(row["case"], row["variant"], row["recommendation"], row["terminal"] or "completed", row["mode"])


if __name__ == "__main__":
    main()
