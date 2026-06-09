"""Read bounded run artifacts for feedback learning."""

import json
from pathlib import Path

from .patterns import _optional_string

def _run_artifacts(run_dir: Path) -> dict:
    quality = _read_json_file(run_dir / "quality_report.json")
    metadata = _read_json_file(run_dir / "run_metadata.json")
    prepare_payload = metadata.get("prepare_payload") if isinstance(metadata.get("prepare_payload"), dict) else {}
    input_path = prepare_payload.get("input_path") if isinstance(prepare_payload.get("input_path"), str) else ""
    source_identity = _metadata_source_identity(metadata, input_path)
    texts = {
        "discarded": _read_text_sample(run_dir / "discarded.md"),
        "cleaned": _read_text_sample(run_dir / "cleaned.md"),
        "review_needed": _read_text_sample(run_dir / "review_needed.md"),
    }
    failed_gates = []
    gates = quality.get("quality_gates", [])
    if isinstance(gates, list):
        for gate in gates:
            if isinstance(gate, dict) and gate.get("status") == "fail" and isinstance(gate.get("name"), str):
                failed_gates.append(gate["name"])
    strict_errors = quality.get("strict_errors", [])
    context = {
        "source_type": quality.get("source_type") if isinstance(quality.get("source_type"), str) else "",
        "profile": quality.get("profile") if isinstance(quality.get("profile"), str) else "",
        "document_type": quality.get("document_type") if isinstance(quality.get("document_type"), str) else "",
        "failed_gates": failed_gates,
        "strict_error_count": len(strict_errors) if isinstance(strict_errors, list) else 0,
        "input_path": input_path,
        "source_name": _optional_string(source_identity.get("source_name")) or (Path(input_path).name if input_path else ""),
        "source_identity": source_identity,
        "files_seen": [
            name for name in ("quality_report.json", "discarded.md", "cleaned.md", "review_needed.md")
            if (run_dir / name).exists()
        ],
    }
    return {"context": context, "texts": texts}

def _metadata_source_identity(metadata: dict, input_path: str) -> dict:
    raw = metadata.get("source_identity")
    if isinstance(raw, dict):
        identity = dict(raw)
    elif isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {}
        identity = parsed if isinstance(parsed, dict) else {"source_identity": raw.strip()}
    else:
        identity = {}
    if input_path:
        identity.setdefault("input_path", input_path)
        identity.setdefault("source_path", input_path)
        identity.setdefault("source_name", Path(input_path).name)
    return identity

def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}

def _read_text_sample(path: Path, max_chars: int = 100_000) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except Exception:
        return ""
