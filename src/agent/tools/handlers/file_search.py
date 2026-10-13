"""
Scoped File Search Handler.
Provides read-only file discovery strictly confined to authorized filesystem roots.
Enforces symlink confinement, forbidden directory exclusion, and path canonicalization.
Zero file writes or modifications.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.policy_engine import DEFAULT_AUTHORIZED_ROOTS, FORBIDDEN_SEARCH_DIRECTORIES, PolicyEngine
from src.agent.tools.models import ExecutionStatus, ToolResult
from src.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

SKIP_FOLDERS = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".idea", ".vscode"}


def search_files(
    pattern: str,
    root_dir: str | None = None,
    extension: str | None = None,
    max_results: int = 20,
    policy_engine: PolicyEngine | None = None,
    **kwargs: Any,
) -> ToolResult:
    """
    Searches for files matching a pattern or extension within an authorized root directory.
    Guarantees confinement and rejects traversal attempts.
    """
    if not pattern and not extension:
        return ToolResult.fail("Search requires either a filename pattern or an extension.")

    search_root = Path(root_dir).resolve() if root_dir else PROJECT_ROOT.resolve()

    # Verify authorization with PolicyEngine if supplied, or default rules
    if policy_engine:
        decision = policy_engine.evaluate("search_files", {"root_dir": str(search_root)})
        if not decision.allowed:
            return ToolResult.fail(f"Access Denied: {decision.reason}")
    else:
        # Default confinement check
        is_contained = any(
            search_root == auth or auth in search_root.parents
            for auth in DEFAULT_AUTHORIZED_ROOTS
        )
        if not is_contained:
            return ToolResult.fail(
                f"Access Denied: Directory '{search_root}' is outside authorized search roots."
            )

        root_lower = str(search_root).lower()
        for forbidden in FORBIDDEN_SEARCH_DIRECTORIES:
            if forbidden in root_lower:
                return ToolResult.fail(
                    f"Access Denied: Directory '{search_root}' is inside forbidden system folder."
                )

    if not search_root.exists() or not search_root.is_dir():
        return ToolResult.fail(f"Directory '{search_root}' does not exist or is not a directory.")

    pattern_lower = pattern.lower().strip() if pattern else ""
    ext_clean = extension.lower().strip() if extension else ""
    if ext_clean and not ext_clean.startswith("."):
        ext_clean = f".{ext_clean}"

    bounded_max = max(1, min(int(max_results), 50))
    hits: list[dict[str, Any]] = []

    effective_roots = (
        policy_engine.authorized_roots
        if policy_engine is not None
        else DEFAULT_AUTHORIZED_ROOTS
    )

    try:
        for current_root, dirs, files in os.walk(search_root, topdown=True, followlinks=False):
            # Prune skipped folders in-place
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_FOLDERS and not d.startswith(".")]

            # Verify current directory has not escaped via traversal or symlink
            curr_path = Path(current_root).resolve()
            if not any(curr_path == auth or auth in curr_path.parents for auth in effective_roots):
                continue

            for filename in files:
                filename_lower = filename.lower()

                # Extension filter
                if ext_clean and not filename_lower.endswith(ext_clean):
                    continue

                # Pattern filter
                if pattern_lower and pattern_lower not in filename_lower:
                    continue

                file_path = curr_path / filename
                # If file is a symlink, verify its resolved destination
                if file_path.is_symlink():
                    try:
                        resolved_link = file_path.resolve()
                        if not any(resolved_link == auth or auth in resolved_link.parents for auth in effective_roots):
                            continue
                    except Exception:
                        continue

                try:
                    stat = file_path.stat()
                    mtime_iso = datetime.fromtimestamp(stat.st_mtime, tzinfo=timezone.utc).isoformat()
                    size_bytes = stat.st_size
                except Exception:
                    mtime_iso = None
                    size_bytes = 0

                hits.append(
                    {
                        "name": filename,
                        "path": str(file_path),
                        "size_bytes": size_bytes,
                        "is_directory": False,
                        "modified_at": mtime_iso,
                    }
                )

                if len(hits) >= bounded_max:
                    break

            if len(hits) >= bounded_max:
                break

        summary_msg = (
            f"Found {len(hits)} matching files in '{search_root}'."
            if hits
            else f"No files matching '{pattern or ext_clean}' found in '{search_root}'."
        )

        return ToolResult.ok(
            {
                "results": hits,
                "count": len(hits),
                "root_dir": str(search_root),
                "pattern": pattern,
                "extension": ext_clean,
                "summary": summary_msg,
            }
        )
    except Exception as e:
        logger.error("Error during file search in %s: %s", search_root, e)
        return ToolResult.fail(f"Filesystem error during search: {e}")
