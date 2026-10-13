"""
Reference-Based Rubric Evaluator for AI Natural Language Outputs.
Evaluates semantic correctness, factual alignment, style boundaries (zero emojis),
and language consistency without requiring third-party cloud APIs.
"""

from __future__ import annotations

import re
from typing import Sequence
from pydantic import BaseModel, Field
from quality_lab.evaluators.speech_metrics import normalize_evaluation_text


class RubricEvaluation(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    criteria_passed: list[str] = Field(default_factory=list)
    criteria_failed: list[str] = Field(default_factory=list)
    explanation: str = ""


class SemanticRubricEvaluator:
    """Evaluates conversational outputs against explicit, reference-based rubrics."""

    @staticmethod
    def evaluate(
        response_text: str,
        required_concepts: Sequence[str] = (),
        forbidden_concepts: Sequence[str] = (),
        expected_language: str = "en",
        min_length: int = 1,
        max_length: int = 2000,
        disallow_emojis: bool = True,
    ) -> RubricEvaluation:
        norm_resp = normalize_evaluation_text(response_text)
        passed_crit = []
        failed_crit = []

        # 1. Non-empty & Length Bounds
        if len(response_text.strip()) >= min_length and len(response_text.strip()) <= max_length:
            passed_crit.append("length_boundary")
        else:
            failed_crit.append(f"length_boundary (len={len(response_text)}, expected [{min_length}, {max_length}])")

        # 2. Emoji prohibition check
        if disallow_emojis:
            emoji_chars = re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", response_text)
            if not emoji_chars:
                passed_crit.append("zero_emoji_rule")
            else:
                failed_crit.append(f"zero_emoji_rule (found emojis: {''.join(emoji_chars)})")

        # 3. Required concepts/keywords presence
        for req in required_concepts:
            norm_req = normalize_evaluation_text(req)
            if not norm_req:
                if req in response_text:
                    passed_crit.append(f"required_concept:{req}")
                else:
                    failed_crit.append(f"missing_concept:{req}")
                continue
            if norm_req in norm_resp:
                passed_crit.append(f"required_concept:{req}")
            else:
                failed_crit.append(f"missing_concept:{req}")

        # 4. Forbidden concepts/keywords absence
        for forb in forbidden_concepts:
            norm_forb = normalize_evaluation_text(forb)
            if not norm_forb:
                if forb in response_text:
                    failed_crit.append(f"forbidden_concept_detected:{forb}")
                else:
                    passed_crit.append(f"forbidden_concept_absent:{forb}")
                continue
            if norm_forb in norm_resp:
                failed_crit.append(f"forbidden_concept_detected:{forb}")
            else:
                passed_crit.append(f"forbidden_concept_absent:{forb}")

        # 5. Language consistency check
        if expected_language == "fa":
            fa_chars = len(re.findall(r"[\u0600-\u06FF]", response_text))
            if fa_chars > 3:
                passed_crit.append("persian_script_present")
            else:
                failed_crit.append("persian_script_missing")
        elif expected_language == "en":
            en_chars = len(re.findall(r"[a-zA-Z]", response_text))
            if en_chars > 3:
                passed_crit.append("english_script_present")
            else:
                failed_crit.append("english_script_missing")

        total = len(passed_crit) + len(failed_crit)
        score = round(len(passed_crit) / total, 3) if total > 0 else 1.0
        passed = (len(failed_crit) == 0)

        explanation = (
            "Passed all semantic criteria."
            if passed
            else f"Failed criteria: {', '.join(failed_crit)}"
        )

        return RubricEvaluation(
            passed=passed,
            score=score,
            criteria_passed=passed_crit,
            criteria_failed=failed_crit,
            explanation=explanation,
        )
