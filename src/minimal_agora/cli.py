from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from minimal_agora.analysis import (
    aggregate_outcomes,
    compare_runs,
    detect_convergence,
    format_report,
    load_trajectories,
    save_artifacts,
    save_report,
)
from minimal_agora.logging_config import configure_logging
from minimal_agora.runner import run_batch, run_particle_filter
from minimal_agora.scenario import load_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description="minimal-agora — counterfactual world simulation")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable DEBUG level logging")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a simulation scenario")
    run_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")
    run_parser.add_argument("-o", "--output", type=Path, default=Path("runs"), help="Output directory")
    run_parser.add_argument("-n", "--n-trajectories", type=int, default=None, help="Override number of trajectories")
    run_parser.add_argument("-m", "--mode", choices=["counterfactual", "open_ended", "population"], default=None, help="Override simulation mode")
    run_parser.add_argument("-c", "--concurrency", type=int, default=2, help="Max parallel trajectories")
    run_parser.add_argument("--steps", type=int, default=None, help="Override step budget")
    run_parser.add_argument("--timeout", type=int, default=300, help="Agent timeout in seconds")
    run_parser.add_argument("--dry-run", action="store_true", help="Validate and summarize scenario without running")

    report_parser = subparsers.add_parser("report", help="Generate report from completed run")
    report_parser.add_argument("run_dir", type=Path, help="Path to run output directory")
    report_parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text", help="Output format")

    viz_parser = subparsers.add_parser("visualize", help="Generate plots from completed run")
    viz_parser.add_argument("run_dir", type=Path, help="Path to run output directory")
    viz_parser.add_argument("--fields", nargs="+", default=None, help="State fields to plot over time")
    viz_parser.add_argument("--populations", nargs="+", default=None, help="Population names for score plots")
    viz_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for population plots")

    dash_parser = subparsers.add_parser("dashboard", help="Launch live web dashboard")
    dash_parser.add_argument("run_dir", type=Path, help="Path to run output directory")
    dash_parser.add_argument("-p", "--port", type=int, default=8765, help="Server port")
    dash_parser.add_argument("--fields", nargs="+", default=None, help="State fields to track")
    dash_parser.add_argument("--populations", nargs="+", default=None, help="Population names")
    dash_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for populations")

    validate_parser = subparsers.add_parser("validate", help="Validate a scenario YAML/JSON file")
    validate_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")

    init_parser = subparsers.add_parser("init-scenario", help="Generate a template scenario YAML file")
    init_parser.add_argument("name", help="Scenario name")
    init_parser.add_argument("--mode", choices=["counterfactual", "open_ended", "population"], default="counterfactual", help="Simulation mode")

    agents_parser = subparsers.add_parser("agents", help="List agents/entities from a scenario")
    agents_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")

    compare_parser = subparsers.add_parser("compare", help="Compare outcomes from two runs")
    compare_parser.add_argument("dir_a", type=Path, help="Path to first run directory")
    compare_parser.add_argument("dir_b", type=Path, help="Path to second run directory")
    compare_parser.add_argument("--alpha", type=float, default=0.05, help="Significance level")
    compare_parser.add_argument(
        "--format", dest="output_format", choices=["text", "json"], default="text",
        help="Output format",
    )

    subparsers.add_parser("version", help="Show version info")

    args = parser.parse_args()
    configure_logging(verbose=args.verbose)

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "report":
        return cmd_report(args)
    elif args.command == "visualize":
        return cmd_visualize(args)
    elif args.command == "dashboard":
        return cmd_dashboard(args)
    elif args.command == "validate":
        return cmd_validate(args)
    elif args.command == "init-scenario":
        return cmd_init_scenario(args)
    elif args.command == "agents":
        return cmd_agents(args)
    elif args.command == "compare":
        return cmd_compare(args)
    elif args.command == "version":
        return cmd_version()
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

    if args.dry_run:
        agents = scenario.agents
        entities = scenario.entities
        if agents:
            print("Agents:")
            for a in agents:
                print(f"  - {a.name} ({a.role.value})")
        if entities:
            print("Entities:")
            for e in entities:
                print(f"  - {e.name} ({e.type.value})")
        print("\nDry run complete. Scenario is valid.")
        return 0

    if scenario.resampling:
        trajectories = asyncio.run(
            run_particle_filter(scenario, output_dir, args.concurrency, args.timeout)
        )
    else:
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

    if args.output_format == "json":
        print(result.model_dump_json(indent=2))
    else:
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


def cmd_validate(args) -> int:
    try:
        load_scenario(args.scenario)
        print("Valid")
        return 0
    except (OSError, ValueError, KeyError) as e:
        print(f"Invalid: {e}")
        return 1


def cmd_init_scenario(args) -> int:
    from minimal_agora.models import SimMode

    mode = SimMode(args.mode)
    name = args.name

    template: dict = {
        "name": name,
        "mode": mode.value,
        "n_trajectories": 5,
        "step_budget": 20,
        "description": f"Template scenario: {name}",
        "initial_state": {
            "world": {"step": 0},
        },
        "rules": [],
        "termination": {
            "max_steps": 20,
        },
    }

    if mode == SimMode.POPULATION:
        template["entities"] = [
            {
                "name": "population_a",
                "type": "population",
                "state_prefix": "populations.population_a",
                "initial_state": {"strength": 50},
                "agents": [
                    {
                        "role": "actor",
                        "name": f"{name}_actor",
                        "perspective": "You represent population A.",
                    }
                ],
                "can_interact_with": [],
            }
        ]
    else:
        template["agents"] = [
            {
                "role": "actor",
                "name": f"{name}_actor",
                "perspective": "You propose changes to the world state.",
            },
            {
                "role": "critic",
                "name": f"{name}_critic",
                "perspective": "You evaluate proposed changes for plausibility.",
            },
            {
                "role": "judge",
                "name": f"{name}_judge",
                "perspective": "You synthesize proposals and critiques into a resolution.",
            },
        ]

    import yaml

    filename = f"{name}.yaml"
    with open(filename, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False)

    print(f"Created scenario template: {filename}")
    return 0


def cmd_agents(args) -> int:
    scenario = load_scenario(args.scenario)

    if scenario.agents:
        print(f"Scenario: {scenario.name}")
        print(f"Mode: {scenario.mode.value}")
        print()
        print("Agents:")
        for a in scenario.agents:
            print(f"  - {a.name} ({a.role.value})")
    if scenario.entities:
        if not scenario.agents:
            print(f"Scenario: {scenario.name}")
            print(f"Mode: {scenario.mode.value}")
            print()
        print("Entities:")
        for e in scenario.entities:
            print(f"  - {e.name} ({e.type.value})")
            for a in e.agents:
                print(f"      {a.name} ({a.role.value})")
    return 0


def cmd_compare(args) -> int:
    traj_a = load_trajectories(args.dir_a)
    traj_b = load_trajectories(args.dir_b)

    if not traj_a:
        print(f"No trajectories found in {args.dir_a}")
        return 1
    if not traj_b:
        print(f"No trajectories found in {args.dir_b}")
        return 1

    result = compare_runs(
        traj_a, traj_b,
        name_a=args.dir_a.name,
        name_b=args.dir_b.name,
        alpha=args.alpha,
    )

    if args.output_format == "json":
        print(result.model_dump_json(indent=2))
    else:
        print("=== Cross-Run Comparison ===")
        print(f"{result.run_a_name} (n={result.n_trajectories_a}) vs "
              f"{result.run_b_name} (n={result.n_trajectories_b})")
        print()
        print("Outcome comparisons:")
        for c in result.outcome_comparisons:
            sig = " *" if c["significant"] else ""
            print(f"  {c['category']}: {c['rate_a']:.1%} vs {c['rate_b']:.1%} "
                  f"(p={c['p_value']:.4f}){sig}")
        if result.metric_comparisons:
            print()
            print("Metric comparisons:")
            for m in result.metric_comparisons:
                print(f"  {m['metric']}: {m['mean_a']:.2f} vs {m['mean_b']:.2f} "
                      f"(d={m['cohens_d']:.3f}, {m['interpretation']})")
        print()
        print(result.summary)
    return 0


def cmd_version() -> int:
    from importlib.metadata import version

    try:
        v = version("minimal-agora")
    except (ImportError, ModuleNotFoundError):
        v = "unknown"
    print(f"minimal-agora {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
