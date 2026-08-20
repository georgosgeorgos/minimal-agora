"""Environment loading for provider configuration.

Loads a local ``.env`` file (when `python-dotenv` is installed) so API keys
and endpoint URLs can be kept out of the shell history and process list.
Existing environment variables always take precedence over ``.env`` values —
``.env`` only fills in variables that are not already set.
"""

from __future__ import annotations

try:
    from dotenv import find_dotenv, load_dotenv  # type: ignore[import-not-found]

    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


def load_env() -> None:
    """Load variables from a ``.env`` file into the process environment.

    No-op when `python-dotenv` is not installed. The file is resolved relative
    to the current working directory (walking up the tree), so a ``.env`` next
    to where you invoke ``minimal-agora`` is picked up — not one relative to
    the installed package. Existing environment variables are never overwritten
    by ``.env`` values, so real env vars (and explicit ``--api-key`` CLI
    flags, which are applied later by the providers) always win.
    """
    if _HAS_DOTENV:
        path = find_dotenv(usecwd=True)
        if path:
            load_dotenv(path)
