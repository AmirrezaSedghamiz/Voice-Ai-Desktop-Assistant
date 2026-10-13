"""
Quality Lab Version-Controlled Evaluation Datasets.
"""

import json
from pathlib import Path
from typing import Any

DATASETS_DIR = Path(__file__).resolve().parent


def load_ai_eval_dataset() -> list[dict[str, Any]]:
    path = DATASETS_DIR / "ai_eval_dataset.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def load_voice_eval_dataset() -> list[dict[str, Any]]:
    path = DATASETS_DIR / "voice_dataset.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])
