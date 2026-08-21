from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from minimal_agora.analysis import (
    aggregate_outcomes,
    compare_runs,
    compute_agent_calibration,
    compute_outcome_coverage,
    detect_convergence,
    format_report,
    load_trajectories,
    save_artifacts,
    save_report,
)
from minimal_agora.env import load_env
from minimal_agora.logging_config import configure_logging
from minimal_agora.runner import run_batch, run_particle_filter
from minimal_agora.scenario import load_scenario


def main() -> int:
    load_env()
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
    run_parser.add_argument(
        "--provider",
        choices=["subprocess", "anthropic", "litellm"],
        default=None,
        help="LLM provider backend (default: subprocess)",
    )
    run_parser.add_argument("--model", default=None, help="Model name (provider-specific)")
    run_parser.add_argument(
        "--api-base",
        default=None,
        help="API base URL (anthropic base_url / litellm api_base). Defaults to the provider's env var.",
    )
    run_parser.add_argument(
        "--api-key",
        default=None,
        help="API key (overrides ANTHROPIC_API_KEY / provider env vars).",
    )

    report_parser = subparsers.add_parser("report", help="Generate report from completed run")
    report_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    report_parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text", help="Output format")

    viz_parser = subparsers.add_parser("visualize", help="Generate plots from completed run")
    viz_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    viz_parser.add_argument("--fields", nargs="+", default=None, help="State fields to plot over time")
    viz_parser.add_argument("--populations", nargs="+", default=None, help="Population names for score plots")
    viz_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for population plots")
    viz_parser.add_argument(
        "--types", nargs="+", default=None,
        choices=["outcomes", "steps", "timelines", "populations", "comparison", "wildcards", "agents"],
        help="Plot types to generate (default: all)",
    )

    dash_parser = subparsers.add_parser("dashboard", help="Launch live web dashboard")
    dash_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    dash_parser.add_argument("-p", "--port", type=int, default=8765, help="Server port")
    dash_parser.add_argument("--fields", nargs="+", default=None, help="State fields to track")
    dash_parser.add_argument("--populations", nargs="+", default=None, help="Population names")
    dash_parser.add_argument("--scores", nargs="+", default=None, help="Score fields for populations")

    validate_parser = subparsers.add_parser("validate", help="Validate a scenario YAML/JSON file")
    validate_parser.add_argument("scenario", type=Path, help="Path to scenario YAML/JSON")

    init_parser = subparsers.add_parser("init-scenario", help="Generate a template scenario YAML file")
    init_parser.add_argument("name", help="Scenario name")
    init_parser.add_argument("--mode", choices=["counterfactual", "open_ended", "population"], default="counterfactual", help="Simulation mode")
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing file")

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
    compare_parser.add_argument(
        "--plots", type=Path, default=None, metavar="DIR",
        help="Generate comparison plots in the given directory",
    )

    cal_parser = subparsers.add_parser("calibration", help="Show per-agent calibration metrics")
    cal_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    cal_parser.add_argument(
        "--format", dest="output_format", choices=["text", "json"], default="text",
        help="Output format",
    )

    coverage_parser = subparsers.add_parser("coverage", help="Show outcome space coverage metrics")
    coverage_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    coverage_parser.add_argument(
        "--format", dest="output_format", choices=["text", "json"], default="text",
        help="Output format",
    )

    explore_parser = subparsers.add_parser("explore", help="Generate interactive Plotly report")
    explore_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    explore_parser.add_argument("--fields", nargs="+", default=None, help="State fields to visualize (default: auto-detect)")
    explore_parser.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path")
    explore_parser.add_argument("--open", action="store_true", help="Open in browser after generating")

    explore3d_parser = subparsers.add_parser("explore-3d", help="Generate 3D state-space explorer")
    explore3d_parser.add_argument("run_dir", nargs="?", type=Path, default=None, help="Path to run output directory (default: latest in runs/)")
    explore3d_parser.add_argument("-o", "--output", type=Path, default=None, help="Output HTML path")
    explore3d_parser.add_argument("--open", action="store_true", help="Open in browser after generating")

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
    elif args.command == "calibration":
        return cmd_calibration(args)
    elif args.command == "coverage":
        return cmd_coverage(args)
    elif args.command == "explore":
        return cmd_explore(args)
    elif args.command == "explore-3d":
        return cmd_explore_3d(args)
    elif args.command == "version":
        return cmd_version()
    else:
        parser.print_help()
        return 1


def _resolve_run_dir(args) -> int | None:
    """If args.run_dir is None, find the most recently modified subdirectory under runs/.
    Returns 1 on failure (caller should return it), None on success (args.run_dir is set).
    """
    if args.run_dir is not None:
        return None
    runs_root = Path("runs")
    if not runs_root.exists():
        print("No runs/ directory found. Run a simulation first.")
        return 1
    subdirs = [d for d in runs_root.iterdir() if d.is_dir()]
    if not subdirs:
        print("No runs found in runs/")
        return 1
    latest = max(subdirs, key=lambda d: d.stat().st_mtime)
    args.run_dir = latest
    print(f"Using latest run: {latest}")
    return None


def _extract_numeric_field_paths(state: dict, prefix: str = "") -> list[str]:
    """Extract dot-separated paths to numeric values from a nested dict."""
    paths = []
    for key, value in state.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, (int, float)):
            paths.append(full)
        elif isinstance(value, dict):
            paths.extend(_extract_numeric_field_paths(value, full))
    return paths


def _create_provider(args):
    """Create an AgentProvider from CLI arguments."""
    provider_type = args.provider or "subprocess"

    if provider_type == "litellm":
        from minimal_agora.providers.litellm_provider import LiteLLMProvider

        kwargs: dict = {}
        if args.model:
            kwargs["model"] = args.model
        if args.api_base:
            kwargs["api_base"] = args.api_base
        if args.api_key:
            kwargs["api_key"] = args.api_key
        return LiteLLMProvider(**kwargs)

    if provider_type == "anthropic":
        from minimal_agora.providers.api_provider import AnthropicAPIProvider

        kwargs = {}
        if args.model:
            kwargs["model"] = args.model
        if args.api_base:
            kwargs["base_url"] = args.api_base
        if args.api_key:
            kwargs["api_key"] = args.api_key
        return AnthropicAPIProvider(**kwargs)

    from minimal_agora.providers.subprocess_provider import ClaudeSubprocessProvider

    return ClaudeSubprocessProvider()


def cmd_run(args) -> int:
    from minimal_agora.models import SimMode

    if not args.scenario.exists():
        print(f"Scenario file not found: {args.scenario}")
        return 1

    scenario = load_scenario(args.scenario)

    if args.mode:
        scenario.mode = SimMode(args.mode)
    if args.n_trajectories is not None:
        scenario.n_trajectories = args.n_trajectories
    if args.steps is not None:
        scenario.step_budget = args.steps
        scenario.termination["max_steps"] = args.steps

    if args.provider:
        from minimal_agora.agents import set_default_provider

        set_default_provider(_create_provider(args))

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
    err = _resolve_run_dir(args)
    if err is not None:
        return err
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
    err = _resolve_run_dir(args)
    if err is not None:
        return err
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
    err = _resolve_run_dir(args)
    if err is not None:
        return err
    from minimal_agora.dashboard import start_dashboard

    if not args.fields:
        trajectories = load_trajectories(args.run_dir)
        if trajectories and trajectories[0].steps:
            state = trajectories[0].steps[0].state_after
            detected = _extract_numeric_field_paths(state)
            if detected:
                args.fields = detected
                print(f"Auto-detected fields: {', '.join(detected)}")

    start_dashboard(
        args.run_dir,
        port=args.port,
        fields=args.fields,
        populations=args.populations,
        score_fields=args.scores,
    )
    return 0


def cmd_validate(args) -> int:
    from pydantic import ValidationError

    try:
        load_scenario(args.scenario)
        print("Valid")
        return 0
    except ValidationError as e:
        print("Invalid scenario:")
        for err in e.errors():
            loc = " → ".join(str(l) for l in err["loc"])
            print(f"  {loc}: {err['msg']}")
        return 1
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
                "role": "constraint_evaluator",
                "name": f"{name}_constraint_evaluator",
                "perspective": "You evaluate proposed changes for plausibility and constraint compliance.",
            },
            {
                "role": "resolver",
                "name": f"{name}_resolver",
                "perspective": "You synthesize proposals and evaluations into a resolution.",
            },
        ]

    import yaml

    filename = f"{name}.yaml"
    filepath = Path(filename)
    if filepath.exists() and not args.force:
        print(f"File already exists: {filepath}. Use --force to overwrite.")
        return 1

    with open(filepath, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False)

    print(f"Created scenario template: {filename}")
    return 0


def cmd_agents(args) -> int:
    if not args.scenario.exists():
        print(f"Scenario file not found: {args.scenario}")
        return 1

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

    if args.plots:
        from minimal_agora.visualize_comparison import generate_comparison_plots

        paths = generate_comparison_plots(result, traj_a, traj_b, args.plots)
        print()
        for p in paths:
            print(f"  Plot saved: {p}")

    return 0


def cmd_calibration(args) -> int:
    err = _resolve_run_dir(args)
    if err is not None:
        return err
    trajectories = load_trajectories(args.run_dir)
    if not trajectories:
        print(f"No trajectories found in {args.run_dir}")
        return 1

    calibration = compute_agent_calibration(trajectories)

    if not calibration:
        print("No agent proposals found in this run.")
        return 0

    if args.output_format == "json":
        import json

        print(json.dumps(calibration, indent=2))
    else:
        # Column headers
        header = (
            f"{'Agent':<25} {'Made':>5} {'Accepted':>8} {'Acc%':>6} "
            f"{'Conf':>6} {'Cal':>6} {'Plaus':>6}"
        )
        print(f"=== Agent Calibration: {args.run_dir.name} ===\n")
        print(header)
        print("-" * len(header))
        for name, metrics in sorted(calibration.items()):
            plaus = (
                f"{metrics['mean_plausibility']:.2f}"
                if metrics["mean_plausibility"] is not None
                else "  n/a"
            )
            print(
                f"{name:<25} {metrics['proposals_made']:>5} "
                f"{metrics['proposals_accepted']:>8} "
                f"{metrics['acceptance_rate']:>5.0%} "
                f"{metrics['mean_confidence']:>6.2f} "
                f"{metrics['confidence_calibration']:>6.2f} "
                f"{plaus:>6}"
            )
        print()
        print("Cal = |confidence - acceptance_rate| (lower is better)")
        if any(m["mean_plausibility"] is not None for m in calibration.values()):
            print("Plaus = mean plausibility score from constraint evaluator critiques")
    return 0


def cmd_coverage(args) -> int:
    err = _resolve_run_dir(args)
    if err is not None:
        return err
    trajectories = load_trajectories(args.run_dir)
    if not trajectories:
        print(f"No trajectories found in {args.run_dir}")
        return 1

    metrics = compute_outcome_coverage(trajectories)

    if args.output_format == "json":
        import json

        print(json.dumps(metrics, indent=2))
    else:
        print(f"=== Outcome Coverage: {args.run_dir.name} ===\n")
        print(f"  Distinct outcomes:      {metrics['n_outcomes']}")
        print(f"  Outcome entropy:        {metrics['outcome_entropy']:.4f} bits")
        print(f"  Normalized entropy:     {metrics['normalized_entropy']:.4f}")
        print(f"  State space coverage:   {metrics['state_space_coverage']:.4f}")
        print(f"  Trajectory divergence:  {metrics['trajectory_divergence']:.4f}")
        print(f"  Coverage score:         {metrics['coverage_score']:.4f}")
        print()
        ne = metrics["normalized_entropy"]
        if ne < 0.3:
            print("Low entropy: trajectories are converging to similar outcomes.")
        elif ne > 0.8:
            print("High entropy: trajectories are exploring diverse outcomes.")
        else:
            print("Moderate entropy: some outcome diversity present.")
    return 0


def cmd_explore(args) -> int:
    err = _resolve_run_dir(args)
    if err:
        return err
    from minimal_agora.visualize_interactive import generate_interactive_report

    out = generate_interactive_report(
        args.run_dir,
        fields=args.fields,
        output_path=args.output,
    )
    print(f"Interactive report: {out}")
    if args.open:
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
    return 0


def cmd_explore_3d(args) -> int:
    err = _resolve_run_dir(args)
    if err:
        return err
    from minimal_agora.explorer_3d import generate_explorer

    out = generate_explorer(args.run_dir, output_path=args.output)
    print(f"3D explorer: {out}")
    if args.open:
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")
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
