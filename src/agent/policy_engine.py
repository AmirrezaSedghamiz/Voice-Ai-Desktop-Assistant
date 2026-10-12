"""
Policy Engine: Independently enforces permissions and boundaries.
Treats model outputs as untrusted. Never allows prompt injection or untrusted text
to grant shell execution, arbitrary file writes, raw SQL access, or admin capabilities.
"""

from typing import Any, NamedTuple


class PolicyDecision(NamedTuple):
    allowed: bool
    reason: str


class PolicyEngine:
    """Independent policy validation gate."""

    # Explicit whitelist of approved tool actions
    PERMITTED_ACTIONS = {
        "get_system_status",
        "get_battery_status",
        "get_resource_metrics",
        "diagnostic_echo",
        "remember_fact",
        "recall_facts",
        "forget_fact",
        "save_note",
    }

    FORBIDDEN_ACTIONS = {
        "execute_shell",
        "execute_powershell",
        "execute_cmd",
        "run_terminal_command",
        "delete_file",
        "write_system_file",
        "modify_registry",
        "access_internet",
        "execute_sql",
        "raw_sql",
        "drop_table",
        "delete_database",
    }

    def evaluate(self, action_name: str, parameters: dict[str, Any] | None = None) -> PolicyDecision:
        """Evaluates whether an action proposed by the LLM is permitted."""
        if not action_name:
            return PolicyDecision(allowed=True, reason="Conversational response only (no tool requested).")

        lower_name = action_name.lower()

        # Explicit denial of destructive / unrestricted shell or raw SQL actions
        if (
            action_name in self.FORBIDDEN_ACTIONS
            or "shell" in lower_name
            or "exec" in lower_name
            or "sql" in lower_name
            or "drop_" in lower_name
        ):
            return PolicyDecision(
                allowed=False,
                reason=f"Security Violation: '{action_name}' is forbidden by the local security policy.",
            )

        # Allow only explicitly registered and permitted tool names
        if action_name in self.PERMITTED_ACTIONS:
            return PolicyDecision(
                allowed=True,
                reason=f"Action '{action_name}' is authorized under safe tool registry.",
            )

        return PolicyDecision(
            allowed=False,
            reason=f"Action '{action_name}' is not in the approved tool whitelist.",
        )
