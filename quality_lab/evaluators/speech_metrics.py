"""
Speech Evaluation Metrics & Bi-directional Persian/English Text Normalizer.
Computes Word Error Rate (WER), Character Error Rate (CER), semantic command-intent accuracy,
and argument matching accuracy without altering the raw transcripts fed into the assistant.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Sequence

PERSIAN_TO_ENGLISH_DIGITS = {
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
}

ARABIC_TO_PERSIAN_CHARS = {
    "ي": "ی",
    "ى": "ی",
    "ك": "ک",
    "ة": "ه",
    "ۀ": "ه",
    "ؤ": "و",
    "إ": "ا",
    "أ": "ا",
    "آ": "ا",
}

DIACRITICS_REGEX = re.compile(r"[\u064B-\u065F\u0670]")
PUNCTUATION_REGEX = re.compile(r"[.,\/#!$%\^&\*;:{}=\-_`~()؟?،!«»\"'\[\]]")


def normalize_evaluation_text(text: str) -> str:
    """
    Normalizes Persian, English, and mixed-language transcripts for fair evaluation:
    - Normalizes Unicode (NFKC)
    - Replaces Arabic Yeh/Kaf with standard Persian glyphs
    - Translates Persian and Arabic digits to ASCII digits
    - Strips Arabic/Persian diacritics (harakat)
    - Strips punctuation and excessive whitespace
    - Lowercases English words
    """
    if not text or not isinstance(text, str):
        return ""

    normalized = unicodedata.normalize("NFKC", text)

    # Character replacements
    for ar, fa in ARABIC_TO_PERSIAN_CHARS.items():
        normalized = normalized.replace(ar, fa)

    # Persian digits translation
    for p_dig, e_dig in PERSIAN_TO_ENGLISH_DIGITS.items():
        normalized = normalized.replace(p_dig, e_dig)

    # Strip diacritics
    normalized = DIACRITICS_REGEX.sub("", normalized)

    # Replace zero-width non-joiner (\u200c) with space for token matching
    normalized = normalized.replace("\u200c", " ")

    # Strip punctuation
    normalized = PUNCTUATION_REGEX.sub(" ", normalized)

    # Lowercase Latin characters
    normalized = normalized.lower()

    # Collapse multiple whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _levenshtein_distance(seq1: Sequence[Any], seq2: Sequence[Any]) -> int:
    """Computes minimum edit distance between two sequences (words or characters)."""
    n, m = len(seq1), len(seq2)
    if n == 0:
        return m
    if m == 0:
        return n

    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if seq1[i - 1] == seq2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost # substitution
            )

    return dp[n][m]


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Computes Word Error Rate: WER = EditDistance(ref_words, hyp_words) / len(ref_words).
    Returns 0.0 for identical token sequences, and 0.0 if both strings are empty.
    """
    ref_norm = normalize_evaluation_text(reference)
    hyp_norm = normalize_evaluation_text(hypothesis)

    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    distance = _levenshtein_distance(ref_words, hyp_words)
    return round(distance / len(ref_words), 4)


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Computes Character Error Rate: CER = EditDistance(ref_chars, hyp_chars) / len(ref_chars).
    """
    ref_norm = normalize_evaluation_text(reference).replace(" ", "")
    hyp_norm = normalize_evaluation_text(hypothesis).replace(" ", "")

    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0

    distance = _levenshtein_distance(list(ref_norm), list(hyp_norm))
    return round(distance / len(ref_norm), 4)


def evaluate_voice_intent_and_args(
    expected_intent: str,
    expected_args: dict[str, Any],
    observed_intent: str,
    observed_args: dict[str, Any],
) -> tuple[bool, bool, str]:
    """
    Evaluates whether the downstream assistant chose the correct handler intent
    and extracted required arguments accurately.
    Returns: (intent_match, args_match, details)
    """
    intent_match = (expected_intent.lower() == observed_intent.lower())
    args_match = True
    mismatches = []

    for k, v in expected_args.items():
        obs_val = observed_args.get(k)
        if obs_val is None:
            args_match = False
            mismatches.append(f"Missing required parameter '{k}'")
            continue

        # Normalization for string values
        if isinstance(v, str) and isinstance(obs_val, str):
            if normalize_evaluation_text(v) != normalize_evaluation_text(obs_val):
                args_match = False
                mismatches.append(f"Arg '{k}' expected '{v}' but observed '{obs_val}'")
        else:
            if obs_val != v:
                args_match = False
                mismatches.append(f"Arg '{k}' expected {v} but observed {obs_val}")

    detail = "Intent and arguments match exactly."
    if not intent_match:
        detail = f"Intent mismatch: Expected '{expected_intent}' but got '{observed_intent}'."
    elif not args_match:
        detail = f"Argument mismatch: {'; '.join(mismatches)}."

    return intent_match, args_match, detail
