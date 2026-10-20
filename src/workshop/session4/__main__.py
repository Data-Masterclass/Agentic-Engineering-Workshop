"""Terminal entry point; human approval only recommends text, never sends email."""
import argparse
from pathlib import Path
from .data import SCENARIOS
from .runner import experiment


def main():
    parser = argparse.ArgumentParser(description="Session 4: investigate, consult correspondence, review a manual follow-up")
    parser.add_argument("--mode", choices=("scripted", "live"), default="scripted")
    parser.add_argument("--scenario", choices=("all", *SCENARIOS), default="all")
    parser.add_argument("--output", type=Path, required=True, help="New local directory; existing results are never overwritten")
    parser.add_argument("--investigation-allowance", default="0", help="USD conservative reservation per invoice investigation")
    parser.add_argument("--followup-allowance", default="0", help="USD conservative reservation per follow-up")
    parser.add_argument("--experiment-allowance", default="0", help="USD reservation cap across this invocation")
    args = parser.parse_args()
    try:
        rows = experiment(args.output, mode=args.mode, scenario=args.scenario, investigation_allowance=args.investigation_allowance, followup_allowance=args.followup_allowance, experiment_allowance=args.experiment_allowance)
    except FileExistsError:
        parser.exit(2, "Output directory already exists; choose a new directory.\n")
    except Exception as exc:
        # Never print arbitrary setup/provider exception payloads.
        parser.exit(2, f"Session 4 could not start/continue ({type(exc).__name__}). Check mode, approved settings, explicit allowances, and saved results.\n")
    for row in rows:
        print(row["scenario"], row["invoice_recommendation"], row["followup_action"], row["draft_review"], row["mode"])


if __name__ == "__main__":
    main()
