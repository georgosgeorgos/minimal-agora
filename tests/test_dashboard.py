import json
import tempfile
from pathlib import Path

from minimal_agora.dashboard import (
    DashboardHandler,
    _auto_detect_fields,
    _collect_data,
    _collect_events,
    _list_runs,
    _load_dashboard_trajectories,
    _summarize_results,
    generate_static_dashboard,
)
from minimal_agora.models import (
    Proposal,
    Resolution,
    Step,
    Trajectory,
    TrajectoryOutcome,
)


def _make_trajectory(
    tid: int,
    outcome: str,
    steps_data: list[dict],
    proposals: list[list[Proposal]] | None = None,
    resolutions: list[Resolution | None] | None = None,
) -> Trajectory:
    steps = []
    for i, state in enumerate(steps_data):
        ps = proposals[i] if proposals and i < len(proposals) else []
        res = resolutions[i] if resolutions and i < len(resolutions) else None
        steps.append(
            Step(
                step_number=i,
                state_before=steps_data[i - 1] if i > 0 else {},
                state_after=state,
                proposals=ps,
                resolution=res,
            )
        )
    return Trajectory(
        scenario_name="test",
        trajectory_id=tid,
        steps=steps,
        outcome=TrajectoryOutcome(
            classification=outcome,
            final_step=len(steps) - 1,
            final_state=steps_data[-1] if steps_data else {},
        ),
    )


def _write_trajectories(tmpdir: Path, trajectories: list[Trajectory]):
    for t in trajectories:
        tdir = tmpdir / f"trajectory_{t.trajectory_id:03d}"
        tdir.mkdir(parents=True)
        with open(tdir / "trajectory.json", "w") as f:
            f.write(t.model_dump_json(indent=2))


def _write_wildcard(tmpdir: Path, tid: int, step: int, name: str, desc: str = ""):
    tdir = tmpdir / f"trajectory_{tid:03d}" / "board"
    tdir.mkdir(parents=True, exist_ok=True)
    with open(tdir / f"wildcard_step_{step}.json", "w") as f:
        json.dump({"name": name, "description": desc}, f)


class TestTrajectoryTimelines:
    def test_per_trajectory_data_structure(self):
        t1 = _make_trajectory(0, "A", [{"x": 10}, {"x": 20}])
        t2 = _make_trajectory(1, "B", [{"x": 15}, {"x": 25}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1, t2])
            data = _collect_data(run_dir, ["x"], [], [])

        tt = data["trajectory_timelines"]
        assert "x" in tt
        assert "0" in tt["x"]
        assert "1" in tt["x"]
        assert tt["x"]["0"] == [{"step": 0, "value": 10}, {"step": 1, "value": 20}]
        assert tt["x"]["1"] == [{"step": 0, "value": 15}, {"step": 1, "value": 25}]

    def test_nested_field(self):
        t1 = _make_trajectory(
            0,
            "A",
            [
                {"life": {"complexity": 5}},
                {"life": {"complexity": 15}},
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, ["life.complexity"], [], [])

        tt = data["trajectory_timelines"]
        assert tt["life.complexity"]["0"] == [
            {"step": 0, "value": 5},
            {"step": 1, "value": 15},
        ]

    def test_missing_field_skipped(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}, {"y": 2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, ["x"], [], [])

        tt = data["trajectory_timelines"]
        assert tt["x"]["0"] == [{"step": 0, "value": 1}]

    def test_no_fields_empty(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, [], [], [])

        assert data["trajectory_timelines"] == {}

    def test_non_numeric_values_excluded(self):
        t1 = _make_trajectory(0, "A", [{"x": "text"}, {"x": 10}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, ["x"], [], [])

        tt = data["trajectory_timelines"]
        assert tt["x"]["0"] == [{"step": 1, "value": 10}]


class TestResultsSummary:
    def test_describes_leading_outcome_and_quality_limit(self):
        trajectories = [
            _make_trajectory(0, "persian_dominance", [{"x": 1}] * 20),
            _make_trajectory(1, "persian_dominance", [{"x": 2}] * 20),
            _make_trajectory(2, "balance_of_power", [{"x": 3}] * 20),
        ]
        summary = _summarize_results(
            trajectories,
            {"persian_dominance": 2, "balance_of_power": 1},
            [{"type": "validation"}],
        )

        assert "2 of 3 trajectories (67%)" in summary["headline"]
        assert "20 steps" in summary["detail"]
        assert "1 validation warning" in summary["detail"]
        assert "do not establish outcome probabilities" in summary["caveat"]

    def test_static_dashboard_includes_sibling_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            _write_trajectories(first, [_make_trajectory(0, "A", [{"x": 1}])])
            _write_trajectories(second, [_make_trajectory(0, "B", [{"y": 2}])])
            output = root / "dashboard.html"

            generate_static_dashboard(first, output_path=output)
            html = output.read_text()

        assert "const EMBEDDED_RUNS = [{" in html
        assert '"dirname": "first"' in html
        assert '"dirname": "second"' in html
        assert '"headline": "A was the final classification' in html


class TestWildcardEvents:
    def test_wildcard_events_have_name(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            _write_wildcard(run_dir, 0, 0, "pandemic", "a global pandemic")
            events = _collect_events([t1], run_dir)

        wc_events = [e for e in events if e["type"] == "wildcard"]
        assert len(wc_events) == 1
        assert wc_events[0]["name"] == "pandemic"
        assert wc_events[0]["step"] == 0


class TestProposalAcceptance:
    def test_accepted_when_keys_overlap(self):
        proposals = [
            [
                Proposal(
                    agent="agent-a",
                    role="actor",
                    proposed_changes={"gdp": 100},
                    reasoning="should grow",
                )
            ]
        ]
        resolutions = [
            Resolution(
                state_delta={"gdp": 100},
                narrative="gdp grew",
            )
        ]
        t1 = _make_trajectory(0, "A", [{"gdp": 100}], proposals, resolutions)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            events = _collect_events([t1], run_dir)

        prop_events = [e for e in events if e["type"] == "proposal"]
        assert len(prop_events) == 1
        assert prop_events[0]["accepted"] is True

    def test_not_accepted_when_keys_differ(self):
        proposals = [
            [
                Proposal(
                    agent="agent-a",
                    role="actor",
                    proposed_changes={"gdp": 100},
                    reasoning="should grow",
                )
            ]
        ]
        resolutions = [
            Resolution(
                state_delta={"population": 50},
                narrative="population grew",
            )
        ]
        t1 = _make_trajectory(0, "A", [{"population": 50}], proposals, resolutions)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            events = _collect_events([t1], run_dir)

        prop_events = [e for e in events if e["type"] == "proposal"]
        assert len(prop_events) == 1
        assert prop_events[0]["accepted"] is False

    def test_not_accepted_without_resolution(self):
        proposals = [
            [
                Proposal(
                    agent="agent-b",
                    role="actor",
                    proposed_changes={"x": 1},
                    reasoning="increase x",
                )
            ]
        ]
        t1 = _make_trajectory(0, "A", [{"x": 1}], proposals, [None])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            events = _collect_events([t1], run_dir)

        prop_events = [e for e in events if e["type"] == "proposal"]
        assert len(prop_events) == 1
        assert prop_events[0]["accepted"] is False

    def test_multiple_agents_counted(self):
        proposals = [
            [
                Proposal(
                    agent="alice", role="actor", proposed_changes={"gdp": 50}, reasoning="grow gdp"
                ),
                Proposal(
                    agent="bob",
                    role="constraint_evaluator",
                    proposed_changes={"risk": 10},
                    reasoning="add risk",
                ),
            ]
        ]
        resolutions = [Resolution(state_delta={"gdp": 50}, narrative="done")]
        t1 = _make_trajectory(0, "A", [{"gdp": 50}], proposals, resolutions)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            events = _collect_events([t1], run_dir)

        prop_events = [e for e in events if e["type"] == "proposal"]
        assert len(prop_events) == 2
        alice_event = next(e for e in prop_events if e["agent"] == "alice")
        bob_event = next(e for e in prop_events if e["agent"] == "bob")
        assert alice_event["accepted"] is True
        assert bob_event["accepted"] is False


class TestListRuns:
    def test_lists_run_directories(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_root = Path(tmpdir)
            run_a = runs_root / "run-alpha"
            run_a.mkdir()
            _write_trajectories(run_a, [t1])

            run_b = runs_root / "run-beta"
            run_b.mkdir()

            runs = _list_runs(runs_root, run_a)

        names = [r["dirname"] for r in runs]
        assert "run-alpha" in names
        assert "run-beta" not in names

    def test_marks_current_run(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_root = Path(tmpdir)
            run_a = runs_root / "run-alpha"
            run_a.mkdir()
            _write_trajectories(run_a, [t1])

            runs = _list_runs(runs_root, run_a)

        current = [r for r in runs if r["current"]]
        assert len(current) == 1
        assert current[0]["dirname"] == "run-alpha"

    def test_reads_scenario_name_from_trajectory(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_root = Path(tmpdir)
            run_dir = runs_root / "my-run"
            run_dir.mkdir()
            _write_trajectories(run_dir, [t1])

            runs = _list_runs(runs_root, run_dir)

        assert runs[0]["scenario"] == "test"

    def test_counts_trajectories(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])
        t2 = _make_trajectory(1, "B", [{"x": 2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_root = Path(tmpdir)
            run_dir = runs_root / "my-run"
            run_dir.mkdir()
            _write_trajectories(run_dir, [t1, t2])

            runs = _list_runs(runs_root, run_dir)

        assert runs[0]["n_trajectories"] == 2

    def test_reads_outcomes_from_report(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            runs_root = Path(tmpdir)
            run_dir = runs_root / "my-run"
            run_dir.mkdir()
            _write_trajectories(run_dir, [t1])
            (run_dir / "report.json").write_text(json.dumps({"outcomes": {"A": 1}}))

            runs = _list_runs(runs_root, run_dir)

        assert runs[0]["outcomes"] == {"A": 1}

    def test_selected_run_uses_its_own_fields_and_stays_in_runs_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_a = root / "run-a"
            run_b = root / "run-b"
            run_a.mkdir()
            run_b.mkdir()
            _write_trajectories(run_a, [_make_trajectory(0, "A", [{"x": 1}])])
            _write_trajectories(run_b, [_make_trajectory(0, "B", [{"y": 2}])])

            handler = object.__new__(DashboardHandler)
            handler.runs_root = root
            handler.run_dir = run_a
            handler.path = "/api/data?run=run-b"
            selected = handler._resolve_run_dir()
            fields = _auto_detect_fields(selected)
            data = _collect_data(selected, fields, [], [])
            assert selected == run_b
            assert fields == ["y"]
            assert list(data["timelines"]) == ["y"]

            handler.path = "/api/data?run=.."
            assert handler._resolve_run_dir() == run_a

    def test_recovers_completed_run_from_step_checkpoints(self):
        trajectory = _make_trajectory(0, "stagnation", [{"oxygen": 1}, {"oxygen": 2}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "intelligence"
            history = run_dir / "trajectory_000" / "history"
            history.mkdir(parents=True)
            for step in trajectory.steps:
                (history / f"step_{step.step_number:03d}_full.json").write_text(
                    step.model_dump_json()
                )
            artifacts = run_dir / "artifacts"
            artifacts.mkdir()
            (artifacts / "summary.json").write_text(
                json.dumps(
                    {
                        "scenario": "intelligence",
                        "trajectories": [
                            {"id": 0, "n_steps": 2, "outcome": "stagnation", "final_step": 1}
                        ],
                    }
                )
            )
            (run_dir / "report.json").write_text(
                json.dumps({"scenario_name": "intelligence", "outcomes": {"stagnation": 1}})
            )

            loaded = _load_dashboard_trajectories(run_dir)
            runs = _list_runs(run_dir.parent, run_dir)
            data = _collect_data(run_dir, None, [], [])

        assert len(loaded) == 1
        assert loaded[0].outcome.classification == "stagnation"
        assert runs[0]["n_trajectories"] == 1
        assert data["total_steps"] == 2
        assert list(data["timelines"]) == ["oxygen"]

    def test_nonexistent_runs_root_returns_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            current = Path(tmpdir) / "current"
            current.mkdir()
            missing = Path(tmpdir) / "nonexistent"

            runs = _list_runs(missing, current)

        assert len(runs) == 1
        assert runs[0]["current"] is True


class TestCollectDataRunDir:
    def test_returns_run_dir_name(self):
        t1 = _make_trajectory(0, "A", [{"x": 1}])

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            _write_trajectories(run_dir, [t1])
            data = _collect_data(run_dir, [], [], [])

        assert data["n_trajectories"] == 1
