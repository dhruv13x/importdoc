# src/importdoc/modules/confidence.py

from typing import Dict, Tuple


class ConfidenceCalculator:
    WEIGHTS = {
        "ast_definition": 3.0,
        "ast_usage": 2.0,
        "regex_match": 1.0,
        "syspath_resolvable": 2.5,
        "multiple_sources": 1.5,
        "exact_match": 2.0,
        "fuzzy_match": 1.5,  # New: for similar modules
    }

    @staticmethod
    def calculate(evidence: Dict[str, int], total_suggestions: int) -> Tuple[int, str]:
        raw = 0.0
        parts = []
        for k, count in evidence.items():
            w = ConfidenceCalculator.WEIGHTS.get(k, 1.0)
            raw += w * count
            if count:
                parts.append(f"{count}x {k} ({w})")
        suggestion_bonus = min(total_suggestions * 0.5, 2.0)
        raw += suggestion_bonus
        score = int(round(max(0, min(10, raw))))
        explanation = f"Based on: {', '.join(parts)}"
        if suggestion_bonus:
            explanation += f" + {total_suggestions} actionable suggestions"
        return score, explanation
