from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from minimal_agora.analysis import (
    aggregate_outcomes,
    detect_convergence,
    format_report,
    load_trajectories,
    save_artifacts,
    save_report,
)
from minimal_agora.runner import run_batch
from minimal_agora.scenario import load_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="minimal-agora — counterfactual world simulation")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")
    run_parser.add_argument("-o", "--output", type=Path, default=Path("runs"), help="Output directory")
    run_parser.add_argument("-n", "--n-trajectories", type=int, default=None, help="Override number of trajectories")
    run_parser.add_argument("-m", "--mode", choices=["counterfactual", "open_ended", "population"], default=None, help="Override simulation mode")
    run_parser.add_argument("-c", "--concurrency", type=int, default=2, help="Max parallel trajectories")
    run_parser.add_argument("--steps", type=int, default=None, help="Override step budget")
    run_parser.add_argument("--timeout", type=int, default=300, help="Agent timeout in seconds")

    report_parser = subparsers.add_parser("report", help="Generate report from completed run")
    report_parser.add_argument("run_dir", type=Path, help="Path to run output directory")

    viz_parser = subparsers.add_parser("visualize", help="Generate plots from completed run")
    viz_parser.add_argument("run_dir", type=Path, help="Path to run output directory")
    viz_parser.add_argument("--fields", nargs="+", default=None, help="State fields to plot over time")
    viz_parser.add_argument("--populations", nargs="+", default=None, help="Population names for score plots")
    viz_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for population plots")
    viz_parser.add_argument(
        "--types", nargs="+", default=None,
        choices=["outcomes", "steps", "timelines", "populations", "comparison", "wildcards", "agents"],
        help="Plot types to generate (default: all)",
    )

    dash_parser = subparsers.add_parser("dashboard", help="Launch live web dashboard")
    dash_parser.add_argument("run_dir", type=Path, help="Path to run output directory")
    dash_parser.add_argument("-p", "--port", type=int, default=8765, help="Server port")
    dash_parser.add_argument("--fields", nargs="+", default=None, help="State fields to track")
    dash_parser.add_argument("--populations", nargs="+", default=None, help="Population names")
    dash_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for populations")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "visualize":
        return cmd_visualize(args)
    elif args.command == "dashboard":
        return cmd_dashboard(args)
    else:
        parser.print_help()
        return 1


def cmd_run(args) -> int:
    from minimal_agora.models import SimMode

    scenario = load_scenario(args.scenario)

    if args.mode:
        scenario.mode = SimMode(args.mode)
    if args.n_trajectories is not None:
        scenario.n_trajectories = args.n_trajectories
    if args.steps is not None:
        scenario.step_budget = args.steps
        scenario.termination["max_steps"] = args.steps

    output_dir = args.output / scenario.name
    has_entities = len(scenario.entities) > 0
    sim_type = "population" if has_entities else "flat"

    print(f"Running scenario: {scenario.name}")
    print(f"Mode: {scenario.mode.value} ({sim_type})")
    print(f"Trajectories: {scenario.n_trajectories}")
    if has_entities:
        pops = [e for e in scenario.entities if e.type.value == "population"]
        forces = [e for e in scenario.entities if e.type.value == "force"]
        print(f"Populations: {', '.join(e.name for e in pops)}")
        if forces:
            print(f"Forces: {', '.join(e.name for e in forces)}")
    print(f"Step budget: {scenario.step_budget}")
    print(f"Output: {output_dir}")
    print()

    trajectories = asyncio.run(
        run_batch(scenario, output_dir, args.concurrency, args.timeout)
    )

    question = scenario.outcome.question if scenario.outcome else ""
    result = aggregate_outcomes(trajectories, question)
    save_report(result, output_dir)
    save_artifacts(trajectories, output_dir)

    print()
    print(format_report(result))

    warnings = detect_convergence(trajectories)
    for w in warnings:
        print(f"\n⚠ {w}")

    return 0


def cmd_report(args) -> int:
    trajectories = load_trajectories(args.run_dir)
    if not trajectories:
        print(f"No trajectories found in {args.run_dir}")
        return 1

    result = aggregate_outcomes(trajectories)
    print(format_report(result))
    return 0


def cmd_visualize(args) -> int:
    from minimal_agora.visualize import generate_all_plots

    print(f"Generating plots from: {args.run_dir}")
    paths = generate_all_plots(
        args.run_dir,
        fields=args.fields,
        populations=args.populations,
        score_fields=args.scores,
        plot_types=args.types,
    )

    if paths:
        print(f"\nGenerated {len(paths)} plots in {args.run_dir / 'plots'}")
    return 0


def cmd_dashboard(args) -> int:
    from minimal_agora.dashboard import start_dashboard

    start_dashboard(
        args.run_dir,
        port=args.port,
        fields=args.fields,
        populations=args.populations,
        score_fields=args.scores,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
