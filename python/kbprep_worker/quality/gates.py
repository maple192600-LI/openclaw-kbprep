"""Named quality gates, next actions, and handoff tasks."""

import json
from pathlib import Path

def _build_quality_gates(strict_errors: list[str], warnings: list[str], report: dict) -> tuple[list[dict], list[dict]]:
    gate_order = [
        "conversion_integrity",
        "cleanup_safety",
        "splitting_integrity",
        "review_safety",
        "export_readiness",
    ]
    descriptions = {
        "conversion_integrity": "Converted Markdown preserves source structure, readable text, and source-linked assets.",
        "cleanup_safety": "Cleaning removes pollution without deleting protected knowledge.",
        "splitting_integrity": "Chunks keep Markdown structure intact for review and Obsidian.",
        "review_safety": "AI or human review patches are validated before publication.",
        "export_readiness": "Final Obsidian/Markdown output may be published.",
    }
    grouped_errors = {name: [] for name in gate_order}
    grouped_warnings = {name: [] for name in gate_order}

    for error in strict_errors:
        gate = _quality_gate_for_message(error)
        grouped_errors[gate].append(error)
        if gate != "export_readiness":
            grouped_errors["export_readiness"].append(error)

    for warning in warnings:
        grouped_warnings[_quality_gate_for_message(warning, is_warning=True)].append(warning)

    gates = []
    for name in gate_order:
        checked = name != "review_safety" or bool(report.get("review_applied_at"))
        errors = grouped_errors[name]
        gate_warnings = grouped_warnings[name]
        if errors:
            status = "fail"
        elif gate_warnings:
            status = "warn"
        elif checked:
            status = "pass"
        else:
            status = "not_checked"
        gates.append({
            "name": name,
            "status": status,
            "checked": checked,
            "description": descriptions[name],
            "strict_errors": errors,
            "warnings": gate_warnings,
        })

    return gates, _next_actions_from_gates(gates)

def _quality_gate_for_message(message: str, is_warning: bool = False) -> str:
    text = message or ""
    if (
        text.startswith("E_TEXT_LAYER_")
        or text.startswith("E_CONVERTED_TEXT_")
        or text.startswith("E_SOURCE_CONVERSION_LOSS")
        or text.startswith("E_CONVERSION_STRUCTURE_LOSS")
        or text.startswith("W_SOURCE_TEXT_LAYER")
        or text.startswith("W_PDF_TEXT_LAYER")
        or "referenced image files are missing" in text
        or "SVG diagram files" in text
    ):
        return "conversion_integrity"
    if "broken code" in text or "broken table" in text or "broken ordered list" in text or "block trace" in text:
        return "splitting_integrity"
    if is_warning and ("chunk" in text.lower() or "split" in text.lower()):
        return "splitting_integrity"
    if text.startswith("E_QA_FAILED") or text.startswith("W_QA") or "discard" in text.lower() or "CTA" in text or "QR" in text:
        return "cleanup_safety"
    return "export_readiness"

def _next_actions_from_gates(gates: list[dict]) -> list[dict]:
    action_by_gate = {
        "conversion_integrity": {
            "action": "inspect_or_rerun_conversion",
            "target": "converted_md_and_source_evidence",
            "reason": "Converted Markdown lost structure, unreadable text, or source-linked assets.",
        },
        "cleanup_safety": {
            "action": "update_cleaning_rules_or_review_pack",
            "target": "cleaning_rules",
            "reason": "Cleaning left pollution behind or removed content that should be protected.",
        },
        "splitting_integrity": {
            "action": "adjust_splitter_or_chunking",
            "target": "splitter",
            "reason": "Chunking broke Markdown structures needed by AI review and Obsidian.",
        },
        "review_safety": {
            "action": "validate_review_patch",
            "target": "review_patch",
            "reason": "Review changes must be checked before publication.",
        },
        "export_readiness": {
            "action": "block_export",
            "target": "latest_outputs",
            "reason": "Strict quality errors remain, so final Obsidian/Markdown output must not be published.",
        },
    }
    actions = []
    seen: set[tuple[str, str, str]] = set()
    for gate in gates:
        if gate.get("status") != "fail":
            continue
        name = str(gate.get("name"))
        base = action_by_gate.get(name)
        if not base:
            continue
        key = (name, base["action"], base["target"])
        if key in seen:
            continue
        seen.add(key)
        actions.append({
            "gate": name,
            **base,
            "strict_error_count": len(gate.get("strict_errors") or []),
        })
    return actions

def _write_quality_gate_artifacts(report: dict, gates: list[dict], run_p: Path) -> dict:
    gate_dir = run_p / "quality_gates"
    gate_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for index, gate in enumerate(gates, start=1):
        name = str(gate.get("name") or f"gate_{index}")
        artifact = {
            "schema": "kbprep.quality_gate.v1",
            "execution_order": index,
            "gate": gate,
            "input_artifacts": _quality_gate_input_artifacts(name, run_p),
            "blocks_publication": name == "export_readiness" and gate.get("status") == "fail",
            "quality_loop": report.get("quality_loop", {}),
            "source_type": report.get("source_type"),
            "profile": report.get("profile"),
            "document_type": report.get("document_type"),
            "generated_from": str(run_p / "quality_report.json"),
        }
        target = gate_dir / f"{name}.json"
        target.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
        paths[name] = str(target)
    return paths

def _quality_gate_input_artifacts(gate: str, run_p: Path) -> list[str]:
    common = [
        run_p / "quality_report.json",
        run_p / "blocks.jsonl",
    ]
    by_gate = {
        "conversion_integrity": [
            run_p / "conversion_report.json",
            run_p / "converted.md",
            run_p / "source_conversion_integrity.json",
        ],
        "cleanup_safety": [
            run_p / "cleaned.md",
            run_p / "discarded.md",
            run_p / "review_needed.md",
        ],
        "splitting_integrity": [
            run_p / "chunks",
            run_p / "parts",
        ],
        "review_safety": [
            run_p / "review_pack.json",
        ],
        "export_readiness": [
            run_p / "cleaned.md",
            run_p / "obsidian",
            run_p / "audit.md",
        ],
    }
    paths = [*common, *by_gate.get(gate, [])]
    return [str(path) for path in paths]

def _quality_tasks_from_actions(report: dict, actions: list[dict], run_p: Path) -> dict:
    tasks = []
    gates_by_name = {
        str(gate.get("name")): gate
        for gate in report.get("quality_gates", [])
        if isinstance(gate, dict)
    }
    for index, action in enumerate(actions, start=1):
        gate = str(action.get("gate") or "export_readiness")
        task_gate = "quality_loop" if action.get("action") == "stop_iteration" else gate
        tasks.append(_quality_task_for_action(report, action, run_p, index, task_gate, gates_by_name.get(gate, {})))
    return {
        "schema": "kbprep.quality_tasks.v1",
        "run_dir": str(run_p),
        "source_type": report.get("source_type"),
        "profile": report.get("profile"),
        "document_type": report.get("document_type"),
        "quality_loop": report.get("quality_loop", {}),
        "tasks": tasks,
    }

def _quality_task_for_action(report: dict, action: dict, run_p: Path, index: int, gate: str, gate_report: dict) -> dict:
    common_must_read = [
        str(run_p / "quality_report.json"),
        str(run_p / "conversion_report.json"),
        str(run_p / "blocks.jsonl"),
        str(run_p / "cleaned.md"),
        str(run_p / "discarded.md"),
        str(run_p / "review_needed.md"),
    ]
    gate_specific = {
        "conversion_integrity": {
            "goal": "Restore source-to-Markdown conversion integrity before any cleanup is trusted.",
            "background": "The converted Markdown or block trace is missing source structure, readable text, or source-linked assets.",
            "must_read_files": [
                *common_must_read,
                str(run_p / "converted.md"),
                str(run_p / "source_conversion_integrity.json"),
            ],
            "allowed_modifications": [
                "Adjust converter selection, conversion fallback, source-integrity checks, or converter-specific extraction code.",
                "Add focused fixtures that prove headings, tables, code blocks, images, and readable text survive conversion.",
            ],
            "forbidden_modifications": [
                "Do not edit source text to make the quality gate pass.",
                "Do not lower conversion thresholds without evidence from source and converted artifacts.",
                "Do not publish latest outputs while conversion_integrity is failing.",
            ],
            "implementation_steps": [
                "Compare the original source evidence with converted.md and source_conversion_integrity.json.",
                "Identify whether the loss happened during conversion, normalization, or blockification.",
                "Fix the narrow conversion path or mark the route unsupported if KBPrep cannot preserve the content yet.",
                "Rerun prepare with force=true and inspect quality_report.json.",
            ],
            "risk_points": [
                "OCR or PDF text-layer output can look readable while losing chapters or tables.",
                "A converter fallback may hide an unsupported format instead of reporting it clearly.",
            ],
        },
        "cleanup_safety": {
            "goal": "Adjust cleaning dictionaries or review decisions so pollution is removed without deleting source knowledge.",
            "background": "Cleaning left pollution in the kept output or discarded useful/protected information.",
            "must_read_files": [
                *common_must_read,
                "rules/base/obvious_noise.json",
                "rules/base/document_type_signals.json",
                "rules/document_types/",
                "rules/templates/",
                ".kbprep/rules/user/accepted_rules.jsonl",
            ],
            "allowed_modifications": [
                "Edit rule dictionaries, document-type dictionaries, or accepted user feedback rules with examples and counterexamples.",
                "Add tests proving the rule is active only for the intended profile or document type.",
            ],
            "forbidden_modifications": [
                "Do not edit source text or cleaned.md by hand to make the quality gate pass.",
                "Do not add platform or self-media cleanup terms to Python worker constants.",
                "Do not accept broad rules that match counterexamples from cleaned.md or review_needed.md.",
            ],
            "implementation_steps": [
                "Inspect discarded.md, cleaned.md, review_needed.md, and the cleanup_safety errors.",
                "Decide whether the issue is a missing discard rule, missing protect rule, wrong document type, or unsafe accepted feedback.",
                "Update the narrowest applicable dictionary or feedback rule.",
                "Rerun prepare or kbprep-feedback --accept-proposal with rerun verification.",
            ],
            "risk_points": [
                "Keyword-only cleanup can delete examples, platform policy text, parameters, or case details.",
                "A template rule can accidentally leak into the generic standard profile.",
            ],
        },
        "splitting_integrity": {
            "goal": "Fix chunking so Markdown structures remain valid for review and Obsidian output.",
            "background": "Chunk or part files broke code fences, tables, ordered lists, or block trace continuity.",
            "must_read_files": [
                *common_must_read,
                str(run_p / "chunks"),
                str(run_p / "parts"),
            ],
            "allowed_modifications": [
                "Adjust splitter logic, chunk boundary rules, or tests for long Markdown structures.",
            ],
            "forbidden_modifications": [
                "Do not remove code fences, table rows, or list markers to avoid splitter errors.",
                "Do not skip chunk generation when review_pack or Obsidian output depends on it.",
            ],
            "implementation_steps": [
                "Open the failing chunk or part files and locate the broken Markdown boundary.",
                "Trace the source block ids in blocks.jsonl.",
                "Adjust splitting to avoid cutting inside protected Markdown structures.",
                "Rerun the focused splitter and quality tests.",
            ],
            "risk_points": [
                "Long code blocks and tables can be valid in cleaned.md but invalid after chunking.",
            ],
        },
        "review_safety": {
            "goal": "Validate or repair review patch handling before publication.",
            "background": "AI or human review patches must not rewrite source text, erase trace metadata, or discard protected details.",
            "must_read_files": [
                *common_must_read,
                str(run_p / "review_pack.json"),
            ],
            "allowed_modifications": [
                "Adjust review patch validation, allowed metadata fields, or review_pack instructions.",
            ],
            "forbidden_modifications": [
                "Do not allow patches to replace block text, source line ranges, page ranges, or block ids.",
                "Do not bypass protected-block discard checks.",
            ],
            "implementation_steps": [
                "Inspect rejected patch details and review_pack.json.",
                "Tighten validation or ask for a corrected metadata-only patch.",
                "Apply the corrected patch and confirm review_safety is checked in quality_report.json.",
            ],
            "risk_points": [
                "A semantic review can silently summarize or delete source evidence if text rewrites are allowed.",
            ],
        },
        "export_readiness": {
            "goal": "Keep final publication blocked until every strict quality error is resolved.",
            "background": "Strict quality errors remain, so latest outputs and Obsidian/Markdown final deliverables must not be treated as accepted.",
            "must_read_files": common_must_read,
            "allowed_modifications": [
                "Fix the failing upstream gate before rerunning prepare.",
                "If iteration limit was reached, revise rules or conversion behavior before another run.",
            ],
            "forbidden_modifications": [
                "Do not manually copy run artifacts into latest outputs.",
                "Do not treat cleaned.md as final output while export_readiness is failing.",
            ],
            "implementation_steps": [
                "Resolve the non-export gate tasks first.",
                "Rerun prepare with force=true.",
                "Confirm export_readiness is pass and latest.json points to accepted final outputs.",
            ],
            "risk_points": [
                "Publishing failed runs pollutes Obsidian and hides missing or wrongly deleted information.",
            ],
        },
        "quality_loop": {
            "goal": "Stop repeated cleanup/review retries and fix the root cause before another iteration.",
            "background": "Quality still fails after the configured maximum review or cleanup iterations.",
            "must_read_files": [
                *common_must_read,
                str(run_p / "review_pack.json"),
                str(run_p / "source_conversion_integrity.json"),
            ],
            "allowed_modifications": [
                "Fix the failing conversion, cleaning, splitting, or review behavior identified by quality_gates.",
                "Add focused regression tests before rerunning the pipeline.",
            ],
            "forbidden_modifications": [
                "Do not increase max_quality_iterations just to make the run continue.",
                "Do not publish latest outputs while quality_loop status is iteration_limit_reached.",
            ],
            "implementation_steps": [
                "Read quality_loop, quality_gates, strict_errors, and the task list in quality_report.json.",
                "Pick the first non-export failing gate and fix that root cause.",
                "Rerun prepare with force=true after the root cause is fixed.",
                "Confirm quality_loop status is passed before writing to Obsidian or latest outputs.",
            ],
            "risk_points": [
                "Repeating the same AI review or cleanup pass can hide a broken rule or converter path.",
            ],
        },
    }
    spec = gate_specific.get(gate, gate_specific["export_readiness"])
    return {
        "id": f"quality-task-{index:02d}-{gate.replace('_', '-')}",
        "gate": gate,
        "action": action.get("action"),
        "target": action.get("target"),
        "goal": spec["goal"],
        "background": spec["background"],
        "must_read_files": spec["must_read_files"],
        "allowed_modifications": spec["allowed_modifications"],
        "forbidden_modifications": spec["forbidden_modifications"],
        "implementation_steps": spec["implementation_steps"],
        "risk_points": spec["risk_points"],
        "test_commands": [
            "npm test",
            "npm run pack:check",
        ],
        "acceptance_criteria": [
            "quality_report.json has no strict_errors for this gate.",
            "quality_report.json quality_gates marks this gate as pass or non-failing.",
            "latest.json is updated only after export_readiness passes.",
        ],
        "review_after_completion": [
            "Re-open quality_report.json, discarded.md, and review_needed.md.",
            "Confirm no protected source detail was removed and no pollution remains in final output.",
        ],
        "rollback_plan": [
            "Revert only the rule or code change introduced for this task.",
            "Restore the previous accepted_rules.jsonl entry if a feedback rule caused the regression.",
        ],
        "evidence": {
            "strict_error_count": action.get("strict_error_count", 0),
            "strict_errors": gate_report.get("strict_errors", []),
            "warnings": gate_report.get("warnings", []),
            "quality_loop": report.get("quality_loop", {}),
        },
    }
