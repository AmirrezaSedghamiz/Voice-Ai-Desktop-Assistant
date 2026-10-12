"""
Local Audit Logger: Records actions, tool invocations, and policy evaluations locally.
Performs redaction of sensitive patterns (tokens, passwords, keys) and guarantees zero telemetry.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("assistant.audit")

REDACTION_PATTERNS = [
    (re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?"), r"\1: [REDACTED]"),
    (re.compile(r"bearer\s+[a-zA-Z0-9_\-\.]{15,}", re.IGNORECASE), "Bearer [REDACTED]"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED-CARD]"),
]


def redact_sensitive_text(text: str) -> str:
    """Applies privacy redaction regexes to arbitrary text."""
    if not isinstance(text, str):
        return text
    redacted = text
    for pattern, repl in REDACTION_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


class AuditLogger:
    """Manages local JSONL audit trail."""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.log_dir / "audit.jsonl"

    def log_event(
        self,
        event_type: str,
        user_input: str,
        proposed_action: dict[str, Any] | None = None,
        policy_decision: str = "PERMITTED",
        policy_reason: str = "OK",
        model_output: str = "",
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Writes an audited, redacted record to local disk."""
        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event_type": event_type,
            "user_input": redact_sensitive_text(user_input),
            "proposed_action": proposed_action,
            "policy_decision": policy_decision,
            "policy_reason": policy_reason,
            "model_output": redact_sensitive_text(model_output),
            "metrics": metrics or {},
        }

        try:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("Failed to write to local audit log: %s", e)
