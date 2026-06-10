"""Locked JSONL storage for feedback rule records."""

import json
import os
from pathlib import Path
from typing import BinaryIO, Any

from ..envelope import fail

class _JsonlFileLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: BinaryIO | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        handle = self.handle
        if os.name == "nt":
            msvcrt: Any = __import__("msvcrt")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl: Any = __import__("fcntl")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self.handle:
            return
        handle = self.handle
        if os.name == "nt":
            msvcrt: Any = __import__("msvcrt")
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl: Any = __import__("fcntl")
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()

def _append_jsonl_locked(path: Path, payload: dict) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with _JsonlFileLock(lock_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)

def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                fail("E_INVALID_INPUT", f"Invalid JSON in {path}:{line_no}: {exc}")
            if not isinstance(value, dict):
                fail("E_INVALID_INPUT", f"Rule proposal in {path}:{line_no} must be an object")
            rows.append(value)
    return rows
