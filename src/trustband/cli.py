"""TrustBand command-line entry point.

This is a stub scaffolded in Phase 0.1. The full CLI (``trustband run ...``)
is implemented in Phase 3 once the orchestrator exists.
"""

from __future__ import annotations

import sys

from trustband import __version__


def main(argv: list[str] | None = None) -> int:
    """Run the TrustBand CLI.

    Args:
        argv: Optional argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    args = sys.argv[1:] if argv is None else argv
    print(f"TrustBand {__version__} — Don't just write code, earn the merge.")
    print(f"CLI not yet implemented (Phase 3). Received args: {args}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
