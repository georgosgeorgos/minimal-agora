from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from worldsim.analysis import aggregate_outcomes, format_report, load_trajectories, save_report
from worldsim.runner import run_batch
from worldsim.scenario import load_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="worldsim — counterfactual world simulation")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")
    run_parser.add_argument("-o", "--output", type=Path, default=Path("runs"), help="Output directory")
    run_parser.add_argument("-c", "--concurrency", type=int, default=2, help="Max parallel trajectories")
    run_parser.add_argument("--timeout", type=int, default=300, help="Agent timeout in seconds")

    report_parser = subparsers.add_parser("report", help="Generate report from completed run")
    report_parser.add_argument("run_dir", type=Path, help="Path to run output directory")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "report":
        return cmd_report(args)
    else:
        parser.print_help()
        return 1


def cmd_run(args) -> int:
    scenario = load_scenario(args.scenario)
    output_dir = args.output / scenario.name

    print(f"Running scenario: {scenario.name}")
    print(f"Mode: {scenario.mode.value}")
    print(f"Trajectories: {scenario.n_trajectories}")
    print(f"Step budget: {scenario.step_budget}")
    print(f"Output: {output_dir}")
    print()

    trajectories = asyncio.run(
        run_batch(scenario, output_dir, args.concurrency, args.timeout)
    )

    question = scenario.outcome.question if scenario.outcome else ""
    result = aggregate_outcomes(trajectories, question)
    save_report(result, output_dir)

    print()
    print(format_report(result))
    return 0


def cmd_report(args) -> int:
    trajectories = load_trajectories(args.run_dir)
    if not trajectories:
        print(f"No trajectories found in {args.run_dir}")
        return 1

    result = aggregate_outcomes(trajectories)
    print(format_report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
