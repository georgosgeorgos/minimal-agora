"""Policy seam for embedded prompts versus workspace-file interaction."""

from __future__ import annotations

from pathlib import Path

from minimal_agora.agents import (
    parse_critique,
    parse_critique_from_text,
    parse_proposal,
    parse_proposal_from_text,
    parse_resolution,
    parse_resolution_from_text,
)
from minimal_agora.models import (
    BoardAccessMode,
    Critique,
    Proposal,
    Resolution,
)


def prompt_context(mode: BoardAccessMode, **embedded_values: object) -> dict[str, object]:
    """Return inline prompt values only when embedded access is selected."""
    if mode == BoardAccessMode.EMBEDDED:
        return embedded_values
    return {}


def ensure_provider_supports_board_access(mode: BoardAccessMode, provider: object) -> None:
    """Fail before execution when file mode lacks a workspace-capable provider."""
    if mode != BoardAccessMode.FILES:
        return
    if not getattr(provider, "supports_workspace_io", False):
        raise RuntimeError(
            "board_access=files requires a provider with workspace I/O support",
        )
    minimum_turns = getattr(provider, "minimum_workspace_turns", None)
    configured_turns = getattr(provider, "max_turns", None)
    if (
        minimum_turns is not None
        and configured_turns is not None
        and configured_turns < minimum_turns
    ):
        raise RuntimeError(
            f"board_access=files requires at least {minimum_turns} turns; "
            f"provider is configured for {configured_turns}",
        )


def parse_proposal_result(
    mode: BoardAccessMode,
    output: str | None,
    workspace: Path,
    agent_name: str,
    step: int,
) -> Proposal | None:
    if mode == BoardAccessMode.EMBEDDED and output:
        parsed = parse_proposal_from_text(output, agent_name)
        if parsed is not None:
            return parsed
    return parse_proposal(workspace, agent_name, step)


def parse_critique_result(
    mode: BoardAccessMode,
    output: str | None,
    workspace: Path,
    agent_name: str,
    step: int,
) -> Critique | None:
    if mode == BoardAccessMode.EMBEDDED and output:
        parsed = parse_critique_from_text(output, agent_name)
        if parsed is not None:
            return parsed
    return parse_critique(workspace, agent_name, step)


def parse_resolution_result(
    mode: BoardAccessMode,
    output: str | None,
    workspace: Path,
    step: int,
) -> Resolution | None:
    if mode == BoardAccessMode.EMBEDDED and output:
        parsed = parse_resolution_from_text(output)
        if parsed is not None:
            return parsed
    return parse_resolution(workspace, step)
