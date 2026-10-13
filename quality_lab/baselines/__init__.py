"""
Quality Lab Baseline Specifications & Thresholds.
"""

import json
from pathlib import Path
from typing import Any

BASELINES_DIR = Path(__file__).resolve().parent


def load_default_baseline() -> dict[str, Any]:
    path = BASELINES_DIR / "default_baseline.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
