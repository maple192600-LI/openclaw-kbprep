"""
JSON envelope helpers for stdout communication with TypeScript layer.

In CLI mode (default): ok/fail write to stdout and sys.exit().
In server mode: ok/fail write a line to stdout without exiting, including _jobId.
"""
import json
import sys
from typing import Any

_SERVER_MODE = False
_CURRENT_JOB_ID = ""


def set_server_mode(enabled: bool):
    global _SERVER_MODE
    _SERVER_MODE = enabled


def set_current_job_id(job_id: str):
    global _CURRENT_JOB_ID
    _CURRENT_JOB_ID = job_id


def is_server_mode() -> bool:
    return _SERVER_MODE


def ok(data: dict[str, Any] | None = None, metrics: dict[str, Any] | None = None, warnings: list[str] | None = None) -> dict:
    """Write a success envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": True,
        "data": data or {},
        "metrics": metrics or {},
        "warnings": warnings or [],
    }
    if _SERVER_MODE and _CURRENT_JOB_ID:
        envelope["_jobId"] = _CURRENT_JOB_ID

    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    if _SERVER_MODE:
        sys.stdout.write("\n")
    sys.stdout.flush()
    if not _SERVER_MODE:
        sys.exit(0)
    return envelope


def fail(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    recoverable: bool = True,
    suggested_action: str = "Check input and retry.",
) -> dict:
    """Write a failure envelope to stdout."""
    envelope: dict[str, Any] = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "recoverable": recoverable,
            "suggested_action": suggested_action,
            "details": details or {},
        },
        "warnings": warnings or [],
    }
    if _SERVER_MODE and _CURRENT_JOB_ID:
        envelope["_jobId"] = _CURRENT_JOB_ID

    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    if _SERVER_MODE:
        sys.stdout.write("\n")
    sys.stdout.flush()
    if not _SERVER_MODE:
        sys.exit(1)
    return envelope
