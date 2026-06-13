"""TrustBand CLI: turn an issue into a verified, review-gated PR.

Offline default (``--bus memory --llm fake``) needs no API keys and runs
deterministically against the bundled fixture. Live mode (``--bus band``,
``--llm real``) is wired in Phase 4.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from trustband import __version__
from trustband.agents import Coder, Planner, Reviewer
from trustband.bus import AgentBus, InMemoryBus
from trustband.contracts import Issue
from trustband.demo import make_demo_fake_llm
from trustband.llm import LLMClient, RealLLM
from trustband.orchestrator import Orchestrator, RunResult

_TEST_RE = re.compile(r"`(test_[A-Za-z0-9_]+)`")


def load_issue(repo: str, issue_file: str, issue_id: str = "BUG-1") -> Issue:
    """Build an Issue from a repo path and a markdown issue file."""
    text = Path(issue_file).read_text() if issue_file else ""
    title = next((line.lstrip("# ").strip() for line in text.splitlines() if line.strip()), "issue")
    match = _TEST_RE.search(text)
    return Issue(
        id=issue_id,
        title=title,
        description=text,
        repo_path=repo,
        failing_test=match.group(1) if match else None,
    )


def _build_bus(kind: str) -> AgentBus:
    """Construct the collaboration layer for the chosen mode."""
    if kind == "memory":
        return InMemoryBus()
    raise SystemExit("the 'band' bus needs Phase 4 wiring + BAND_API_KEY; use --bus memory offline")


def _build_llm(kind: str) -> LLMClient:
    """Construct the LLM client for the chosen mode."""
    if kind == "fake":
        return make_demo_fake_llm()
    return RealLLM()


def _print_run(result: RunResult, bus: AgentBus) -> None:
    """Print the room transcript and the run outcome."""
    print("\n=== Band room transcript ===")
    for message in bus.history():
        to = f" -> {message.recipient}" if message.recipient else ""
        print(f"[{message.sender}{to}] ({message.kind}) {message.text}")
    verdict = result.verdict
    print("\n=== Verdict ===")
    print(
        f"  {verdict.verdict.value.upper()} | "
        f"newly_passing={verdict.newly_passing} | regressions={verdict.regressions}"
    )
    if result.decision is not None:
        print(f"=== Human gate: {result.decision.decision.value} by {result.decision.actor} ===")
    print(f"=== Merged: {result.merged} ===")
    if result.pr_path is not None:
        print(f"PR written to: {result.pr_path}")


def _cmd_run(args: argparse.Namespace) -> int:
    """Execute the 'run' subcommand."""
    issue = load_issue(args.repo, args.issue, args.issue_id)
    bus = _build_bus(args.bus)
    llm = _build_llm(args.llm)
    orchestrator = Orchestrator(
        bus,
        Planner(bus, llm),
        Coder(bus, llm),
        Reviewer(bus, llm),
        max_revisions=args.max_revisions,
    )
    result = orchestrator.run(issue)
    _print_run(result, bus)
    return 0 if result.merged else 1


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="trustband", description="Turn an issue into a verified, review-gated PR on Band."
    )
    parser.add_argument("--version", action="version", version=f"trustband {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    run = subparsers.add_parser("run", help="turn an issue into a verified PR")
    run.add_argument("--repo", required=True, help="path to the target repository")
    run.add_argument("--issue", required=True, help="path to the issue markdown file")
    run.add_argument("--issue-id", default="BUG-1", dest="issue_id", help="issue identifier")
    run.add_argument("--bus", choices=["memory", "band"], default="memory")
    run.add_argument("--llm", choices=["fake", "real"], default="fake")
    run.add_argument("--max-revisions", type=int, default=2, dest="max_revisions")

    args = parser.parse_args(argv)
    if args.command == "run":
        return _cmd_run(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
