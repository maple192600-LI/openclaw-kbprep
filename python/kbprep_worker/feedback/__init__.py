"""Feedback package public compatibility surface."""

from .command import run
from .jsonl_store import _append_jsonl_locked

__all__ = ["run", "_append_jsonl_locked"]
