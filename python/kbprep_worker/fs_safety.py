"""Safe filesystem deletion helpers for cleanup and publishing paths."""

from __future__ import annotations

import os
import shutil
import stat
import time
from pathlib import Path


def safe_rmtree(
    path: Path,
    *,
    root: Path,
    dry_run: bool = False,
    retries: int = 2,
    retry_delay: float = 0.05,
) -> bool:
    """Remove a directory after proving it stays inside root.

    Returns True when the path exists and would be removed. Raises RuntimeError
    with a diagnostic message when removal fails after retries.
    """
    target = _resolve_inside_root(path, root)
    if not target.exists():
        return False
    if not target.is_dir():
        raise RuntimeError(f"Refusing to remove non-directory with safe_rmtree: {target}")
    if dry_run:
        return True

    attempts = max(1, retries)
    last_error: BaseException | None = None
    for attempt in range(attempts):
        try:
            shutil.rmtree(target, onerror=_make_writable)
            return True
        except Exception as exc:  # pragma: no cover - exercised by mocked failure.
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(max(0.0, retry_delay))
    raise RuntimeError(f"Failed to remove directory {target}: {last_error}") from last_error


def safe_unlink(path: Path, *, root: Path, dry_run: bool = False) -> bool:
    """Remove a file after proving it stays inside root."""
    target = _resolve_inside_root(path, root)
    if not target.exists():
        return False
    if target.is_dir():
        raise RuntimeError(f"Refusing to unlink directory with safe_unlink: {target}")
    if dry_run:
        return True
    try:
        target.unlink()
        return True
    except Exception as exc:
        raise RuntimeError(f"Failed to remove file {target}: {exc}") from exc


def _resolve_inside_root(path: Path, root: Path) -> Path:
    root_resolved = root.resolve()
    target = path.resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise RuntimeError(f"Refusing to delete outside root: {target}")
    return target


def _make_writable(function, path, excinfo) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        function(path)
    except Exception as exc:
        raise excinfo[1] from exc
