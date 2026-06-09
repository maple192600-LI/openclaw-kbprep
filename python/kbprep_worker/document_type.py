"""Lightweight document type classification for rule selection."""

from __future__ import annotations

import re

from .document_type_signals import load_document_type_signals

SUPPORTED_DOCUMENT_TYPES = {"report", "course", "transcript", "webpage", "ebook", "code", "unknown"}


def classify_document_type(text: str, source_type: str = "", diagnosis: dict | None = None) -> dict:
    diagnosis = diagnosis or {}
    detected_format = str(diagnosis.get("detected_format") or "").lower()
    text_sample = (text or "")[:200_000]
    signals = load_document_type_signals()
    supported = set(signals.supported_document_types) or SUPPORTED_DOCUMENT_TYPES
    scores = {name: 0 for name in supported}
    reasons: dict[str, list[str]] = {name: [] for name in supported}

    def add(name: str, score: int, reason: str) -> None:
        if name not in scores:
            return
        scores[name] += score
        reasons[name].append(reason)

    normalized_source_type = str(source_type or "").lower()
    for hint in signals.source_type_hints:
        if normalized_source_type == hint.value:
            add(hint.document_type, hint.score, hint.reason)
    for hint in signals.format_hints:
        if detected_format == hint.value:
            add(hint.document_type, hint.score, hint.reason)
    for pattern in signals.content_patterns:
        if re.search(pattern.pattern, text_sample, pattern.flags):
            add(pattern.document_type, pattern.score, pattern.reason)

    best = max((name for name in supported if name != "unknown"), key=lambda name: scores.get(name, 0))
    best_score = scores[best]
    if best_score <= 0:
        return {
            "document_type": "unknown",
            "confidence": 0.1,
            "reasons": ["no strong document-type signals detected"],
            "scores": scores,
        }

    confidence = min(0.95, 0.35 + best_score / 12)
    return {
        "document_type": best,
        "confidence": round(confidence, 3),
        "reasons": reasons[best],
        "scores": scores,
    }
