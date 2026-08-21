from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from minimal_agora.providers.protocol import AgentInvocationResult

logger = structlog.stdlib.get_logger(__name__)


class ClaudeSubprocessProvider:
    """Provider that invokes the ``claude -p`` CLI subprocess."""

    def __init__(
        self,
        max_turns: int = 1,
        output_format: str = "text",
    ) -> None:
        self.max_turns = max_turns
        self.output_format = output_format

    def build_command(self, prompt: str, workspace: Path) -> list[str]:
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            self.output_format,
            "--max-turns",
            str(self.max_turns),
            "--allowedTools",
            "Read,Write,Bash",
            "--add-dir",
            str(workspace),
        ]

    async def invoke(
        self,
        prompt: str,
        workspace: Path,
        timeout: int = 300,
        model: str | None = None,
        temperature: float | None = None,
    ) -> AgentInvocationResult:
        cmd = self.build_command(prompt, workspace)
        if model:
            cmd.extend(["--model", model])

        logger.debug("provider.invoke", provider="claude-subprocess", workspace=str(workspace))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise TimeoutError(f"Agent timed out after {timeout}s")

        if proc.returncode != 0:
            err = stderr.decode() if stderr else "unknown error"
            raise RuntimeError(f"Agent failed (exit {proc.returncode}): {err}")

        output = stdout.decode().strip()

        estimated_input = len(prompt) // 4
        estimated_output = len(output) // 4

        logger.debug(
            "provider.invoke.done",
            provider="claude-subprocess",
            output_length=len(output),
            estimated_input_tokens=estimated_input,
            estimated_output_tokens=estimated_output,
        )

        return AgentInvocationResult(
            output=output,
            tokens_used=estimated_input + estimated_output,
            model=model or "claude-via-cli",
            input_tokens=estimated_input,
            output_tokens=estimated_output,
        )
