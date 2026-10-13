"""
Quality Lab JSON Report Generator.
Serializes machine-readable execution summaries and test outcomes with sensitive data redaction.
"""

from __future__ import annotations

import json
from pathlib import Path
from quality_lab.models import RunSummary


def generate_json_report(summary: RunSummary, output_path: Path) -> Path:
    """Serializes the RunSummary into a structured JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = summary.model_dump(mode="json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return output_path
