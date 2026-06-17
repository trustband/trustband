"""Apply TrustBand patches and render diffs against a target repository."""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from pathlib import Path

from trustband.contracts import Patch


class PatchApplyError(RuntimeError):
    """Raised when a patch cannot be applied safely."""


def _safe_target(root: Path, relative_path: str) -> Path:
    """Return a path under ``root``, rejecting absolute or escaping paths."""
    if not relative_path:
        raise PatchApplyError("patch path is empty")
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PatchApplyError(f"unsafe patch path: {relative_path}")
    return root / candidate


def apply_patch(work: Path, patch: Patch) -> None:
    """Apply replacements, text edits, and deletes to ``work``."""
    for change in patch.changes:
        target = _safe_target(work, change.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new_content)
    for edit in patch.edits:
        target = _safe_target(work, edit.path)
        if not target.exists():
            raise PatchApplyError(f"cannot edit missing file: {edit.path}")
        original = target.read_text()
        count = original.count(edit.find)
        if count == 0:
            raise PatchApplyError(f"edit target not found in {edit.path}")
        if count > 1 and not edit.replace_all:
            raise PatchApplyError(
                f"edit target is ambiguous in {edit.path}; set replace_all=true"
            )
        limit = -1 if edit.replace_all else 1
        target.write_text(original.replace(edit.find, edit.replace, limit))
    for delete in patch.deletes:
        target = _safe_target(work, delete.path)
        if target.exists():
            target.unlink()


def render_diff(repo_path: str | Path, patches: Iterable[Patch]) -> str:
    """Render patches as unified diff blocks against ``repo_path``."""
    root = Path(repo_path)
    patch_list = list(patches)
    touched_paths: list[str] = []
    for patch in patch_list:
        for path in patch.touched_paths:
            if path not in touched_paths:
                touched_paths.append(path)
    originals: dict[str, str | None] = {}
    updated: dict[str, str | None] = {}
    for path in touched_paths:
        target = _safe_target(root, path)
        originals[path] = target.read_text() if target.exists() else None
        updated[path] = originals[path]

    for patch in patch_list:
        for change in patch.changes:
            updated[change.path] = change.new_content
        for edit in patch.edits:
            original = updated.get(edit.path)
            if original is None:
                raise PatchApplyError(f"cannot edit missing file: {edit.path}")
            count = original.count(edit.find)
            if count == 0:
                raise PatchApplyError(f"edit target not found in {edit.path}")
            if count > 1 and not edit.replace_all:
                raise PatchApplyError(
                    f"edit target is ambiguous in {edit.path}; set replace_all=true"
                )
            limit = -1 if edit.replace_all else 1
            updated[edit.path] = original.replace(edit.find, edit.replace, limit)
        for delete in patch.deletes:
            updated[delete.path] = None

    blocks: list[str] = []
    for path, original in originals.items():
        original_text = original or ""
        updated_text = updated[path] or ""
        diff = difflib.unified_diff(
            original_text.splitlines(keepends=True),
            updated_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
        blocks.append("".join(diff))
    return "\n".join(block for block in blocks if block)
