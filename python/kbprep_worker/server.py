"""
server — long-running JSON-RPC worker process.

Receives one JSON request per line on stdin, writes one JSON response per line on stdout.
Heavy imports (torch, mineru) are deferred until a command needs them.
"""
import json
import sys
import logging
import threading

from .envelope import set_server_mode, set_current_job_id

logger = logging.getLogger(__name__)

# Lazy-loaded handlers
_handlers: dict[str, object] = {}


def _get_handler(command: str):
    if command in _handlers:
        return _handlers[command]

    if command == "preflight":
        from . import preflight as mod
        _handlers[command] = mod.run
    elif command == "convert":
        from . import convert as mod
        _handlers[command] = mod.run
    elif command == "split":
        from . import splitter_runner as mod
        _handlers[command] = mod.run
    elif command == "audit":
        from . import audit as mod
        _handlers[command] = mod.run
    elif command == "apply_patch":
        from . import patch_guard as mod
        _handlers[command] = mod.run
    elif command == "prepare":
        from . import prepare as mod
        _handlers[command] = mod.run
    elif command == "prepare_batch":
        from . import prepare_batch as mod
        _handlers[command] = mod.run
    else:
        return None

    return _handlers[command]


def main():
    set_server_mode(True)
    _setup_logging()

    logger.info("KBPrep worker server ready")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "SHUTDOWN":
            logger.info("Received SHUTDOWN, exiting")
            break

        try:
            req = json.loads(line)
            command = req.get("command", "")
            data = req.get("data", {})
            job_id = req.get("_jobId", "")
        except json.JSONDecodeError as e:
            _write_response("", {"ok": False, "error": {"code": "KBPREP_INVALID_INPUT", "message": f"Invalid JSON: {e}"}})
            continue

        handler = _get_handler(command)
        if handler is None:
            _write_response(job_id, {"ok": False, "error": {"code": "KBPREP_INVALID_INPUT", "message": f"Unknown command: {command}"}})
            continue

        # Set job_id so envelope ok()/fail() can include it in the response
        set_current_job_id(job_id)
        try:
            handler(data)
        except Exception as e:
            logger.exception("Error in %s", command)
            _write_response(job_id, {"ok": False, "error": {"code": "KBPREP_INTERNAL", "message": str(e)}})
        finally:
            set_current_job_id("")


def _write_response(job_id: str, envelope: dict):
    if job_id:
        envelope["_jobId"] = job_id
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _setup_logging():
    class JsonlHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            entry = {
                "level": record.levelname.lower(),
                "event": record.getMessage(),
            }
            if record.exc_info and record.exc_info[1]:
                entry["error"] = str(record.exc_info[1])
            sys.stderr.write(json.dumps(entry, ensure_ascii=False) + "\n")
            sys.stderr.flush()

    handler = JsonlHandler()
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(handler)


if __name__ == "__main__":
    main()
