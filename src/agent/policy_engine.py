"""
Policy Engine: Independently enforces permissions and boundaries.
Treats model outputs as untrusted. Never allows prompt injection or untrusted text
to grant shell execution, arbitrary file writes, or admin capabilities.
"""

from typing import Any, NamedTuple


class PolicyDecision(NamedTuple):
    allowed: bool
    reason: str


class PolicyEngine:
    """Independent policy validation gate."""

    # Explicit whitelist of approved tool actions for the initial baseline
    PERMITTED_ACTIONS = {
        "get_system_status",
        "get_battery_status",
        "get_resource_metrics",
        "diagnostic_echo",
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
    }

    def evaluate(self, action_name: str, parameters: dict[str, Any] | None = None) -> PolicyDecision:
        """Evaluates whether an action proposed by the LLM is permitted."""
        if not action_name:
            return PolicyDecision(allowed=True, reason="Conversational response only (no tool requested).")

        # Explicit denial of destructive / unrestricted shell actions
        if action_name in self.FORBIDDEN_ACTIONS or "shell" in action_name.lower() or "exec" in action_name.lower():
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
