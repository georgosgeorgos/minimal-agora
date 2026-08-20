from minimal_agora.board import compress_narrative
from minimal_agora.models import Scenario, SimMode


def _build_narrative(n_steps: int) -> str:
    parts = ["# Test — Narrative Log\n\n## Step 0 — Initial State\n\nInitial world state.\n"]
    for i in range(1, n_steps + 1):
        parts.append(f"\n## Step {i}\n\nSomething happened in step {i}. More details follow.\n")
    return "".join(parts)


def test_short_narrative_no_compression():
    narrative = _build_narrative(5)
    result = compress_narrative(narrative, window=20)
    assert result == narrative


def test_long_narrative_compresses_old_steps():
    narrative = _build_narrative(25)
    result = compress_narrative(narrative, window=20)
    assert "## Summary of Earlier Steps" in result
    for i in range(6, 26):
        assert f"## Step {i}\n" in result
    for i in range(1, 6):
        assert f"## Step {i}\n\n" not in result
    assert "Something happened in step 1." in result


def test_empty_narrative():
    result = compress_narrative("", window=20)
    assert result == ""


def test_window_one():
    narrative = _build_narrative(3)
    result = compress_narrative(narrative, window=1)
    assert "## Step 3" in result
    assert "## Step 1" not in result
    assert "## Step 2" not in result
    assert "## Summary of Earlier Steps" in result
    assert "Something happened in step 1." in result
    assert "Something happened in step 2." in result


def test_exactly_at_window_no_compression():
    narrative = _build_narrative(20)
    result = compress_narrative(narrative, window=20)
    assert result == narrative


def test_preserves_preamble_and_step_zero():
    narrative = _build_narrative(25)
    result = compress_narrative(narrative, window=20)
    assert "# Test — Narrative Log" in result
    assert "## Step 0 — Initial State" in result
    assert "Initial world state." in result


def test_recompression_preserves_existing_summary():
    narrative = _build_narrative(22)
    first = compress_narrative(narrative, window=20)
    assert "## Summary of Earlier Steps" in first

    extra = "\n## Step 23\n\nNew event in step 23. Extra details.\n"
    extended = first + extra
    second = compress_narrative(extended, window=20)

    assert "## Step 23" in second
    assert "Something happened in step 1." in second
    assert "Something happened in step 2." in second
    assert "Something happened in step 3." in second


def test_batch_compression_groups_ten():
    narrative = _build_narrative(35)
    result = compress_narrative(narrative, window=20)
    summary_start = result.index("## Summary of Earlier Steps")
    first_recent = result.index("## Step 16")
    summary_text = result[summary_start:first_recent]
    paragraphs = [p.strip() for p in summary_text.split("\n\n") if p.strip() and "## Summary" not in p]
    assert len(paragraphs) == 2


def test_default_narrative_window():
    scenario = Scenario(
        name="test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0},
    )
    assert scenario.narrative_window == 20


def test_narrative_window_field_set():
    scenario = Scenario(
        name="test",
        mode=SimMode.COUNTERFACTUAL,
        initial_state={"x": 0},
        narrative_window=10,
    )
    assert scenario.narrative_window == 10


def test_first_sentence_extraction_no_period():
    narrative = "# Log\n\n## Step 0 — Initial State\n\nInit\n"
    for i in range(1, 5):
        narrative += f"\n## Step {i}\n\nNo period here for step {i}\n"
    result = compress_narrative(narrative, window=2)
    assert "## Summary of Earlier Steps" in result
    assert "No period here for step 1" in result
