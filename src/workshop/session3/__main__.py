"""Offline commands; no live execution mode is provided by Session 3."""
import argparse
from pathlib import Path
from .core import demo, compare, export
from .context import context


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("demo", help="Create labelled fixed-script success/failure examples")
    create.add_argument("--output", type=Path, required=True)
    for name in ("compare", "export", "context"):
        command = commands.add_parser(name, help="Inspect existing artifacts without model calls")
        command.add_argument("--input", type=Path, required=True)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            demo(args.output)
            print("Created scripted wiring/permission examples; no model calls or prompt evaluation.")
        else:
            result = {"compare": compare, "export": export, "context": context}[args.command](args.input, args.output)
            label = "Private local context" if args.command == "context" else f"Projected {args.command}"
            print(f"{label}: {result}")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        # Do not echo imported paths, values, exception payloads or credentials.
        parser.exit(1, f"Session 3 stopped ({type(exc).__name__}). Check artifact provenance, the one-change rule and new output paths.\n")


if __name__ == "__main__":
    main()
