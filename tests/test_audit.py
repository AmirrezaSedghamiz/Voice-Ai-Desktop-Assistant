"""
Tests for local audit logging and sensitive information redaction.
"""

import json
from pathlib import Path
from src.agent.audit_log import AuditLogger, redact_sensitive_text


def test_sensitive_text_redaction():
    sample_text = "My secret token is api_key=sk-1234567890abcdef and password: supersecret123"
    redacted = redact_sensitive_text(sample_text)
    assert "sk-1234567890abcdef" not in redacted
    assert "supersecret123" not in redacted
    assert "[REDACTED]" in redacted

    bearer_sample = "Authorization: Bearer mysecretbearertoken123456"
    redacted_bearer = redact_sensitive_text(bearer_sample)
    assert "mysecretbearertoken123456" not in redacted_bearer
    assert "Bearer [REDACTED]" in redacted_bearer


def test_audit_log_record_writing(tmp_path: Path):
    logger = AuditLogger(tmp_path)
    logger.log_event(
        event_type="test_event",
        user_input="Hello password=mysecretpassword",
        proposed_action={"action": "get_system_status"},
        policy_decision="PERMITTED",
        policy_reason="Safe tool",
        model_output="Here is system status: healthy",
    )

    assert logger.audit_file.exists()
    with open(logger.audit_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "test_event"
        assert "mysecretpassword" not in record["user_input"]
        assert record["policy_decision"] == "PERMITTED"
