from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AuditContext:
    input_name: str
    file_hash: str
    plugin_version: str
    mineru_version: str
    python_version: str
    runtime: dict[str, Any]
    diagnosis: dict[str, Any]
    blocks: list[dict[str, Any]]
    quality_report: dict[str, Any]
    warnings: list[str]
    strict_errors: list[str]


def generate_audit_md(context: AuditContext) -> str:
    return _generate_audit_md(
        input_name=context.input_name,
        file_hash=context.file_hash,
        plugin_version=context.plugin_version,
        mineru_version=context.mineru_version,
        python_version=context.python_version,
        runtime=context.runtime,
        diagnosis=context.diagnosis,
        blocks=context.blocks,
        quality_report=context.quality_report,
        warnings=context.warnings,
        strict_errors=context.strict_errors,
    )


def _generate_audit_md(
    input_name: str,
    file_hash: str,
    plugin_version: str,
    mineru_version: str,
    python_version: str,
    runtime: dict,
    diagnosis: dict,
    blocks: list[dict],
    quality_report: dict,
    warnings: list[str],
    strict_errors: list[str],
) -> str:
    lines = [
        "# kbprep audit",
        "",
        "## Input",
        f"Filename: {input_name}",
        f"SHA256: {file_hash}",
        f"Plugin version: {plugin_version}",
        f"MinerU version: {mineru_version}",
        f"Python version: {python_version}",
        f"Python executable: {runtime.get('python_executable', 'unknown')}",
        f"MinerU path: {runtime.get('mineru_path', 'unknown')}",
        f"Torch: {runtime.get('torch', 'unknown')}",
        f"CUDA available: {runtime.get('torch_cuda_available', 'unknown')}",
        f"CUDA version: {runtime.get('torch_cuda_version', 'unknown')}",
        f"MinerU device: {runtime.get('mineru_device', 'unknown')}",
        "",
        "## Diagnosis",
        f"Format: {diagnosis.get('detected_format', 'unknown')}",
        f"Text layer health: {diagnosis.get('text_layer_health', 'unknown')}",
        f"Garbled ratio: {diagnosis.get('text_quality', {}).get('garbled_ratio', 'N/A')}",
        f"Needs OCR: {diagnosis.get('needs_ocr', 'unknown')}",
        "",
    ]

    status_counts = {}
    for b in blocks:
        s = b.get("status", "unclassified")
        status_counts[s] = status_counts.get(s, 0) + 1

    lines.append("## Block Statistics")
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.append("")

    discard_blocks = [b for b in blocks if b.get("status") == "discard"]
    if discard_blocks:
        lines.append("## Deleted Content")
        for b in discard_blocks[:50]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {btype}, reason: {reason}")
        if len(discard_blocks) > 50:
            lines.append(f"- ... and {len(discard_blocks) - 50} more")
        lines.append("")

    evidence_blocks = [b for b in blocks if b.get("status") == "evidence"]
    if evidence_blocks:
        lines.append("## Evidence")
        for b in evidence_blocks[:30]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            lines.append(f"- {bid}: {btype}")
        lines.append("")

    risk_blocks = [b for b in blocks if b.get("status") == "keep" and b.get("risk_tags")]
    if risk_blocks:
        lines.append("## High-Risk Kept Content")
        for b in risk_blocks[:30]:
            bid = b.get("block_id", "?")
            tags = ", ".join(b.get("risk_tags", []))
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {tags}, reason: {reason}")
        lines.append("")

    review_blocks = [b for b in blocks if b.get("status") == "review"]
    if review_blocks:
        lines.append("## Needs Review")
        for b in review_blocks[:30]:
            bid = b.get("block_id", "?")
            btype = b.get("type", "unknown")
            reason = b.get("reason", "")
            lines.append(f"- {bid}: {btype}, reason: {reason}")
        lines.append("")

    if warnings:
        lines.append("## Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    if strict_errors:
        lines.append("## Strict Errors")
        for e in strict_errors:
            lines.append(f"- {e}")
        lines.append("")

    return "\n".join(lines)
