"""
test_skill_inference_accuracy.py — Benchmark 4: Skill Inference Accuracy
==========================================================================
Validates the skill graph produces correct inferences.

Tracks:
    True Positives  — correctly inferred skills
    True Negatives  — correctly NOT inferred (different frameworks)
    False Positives — incorrectly inferred
    False Negatives — should have inferred but didn't

Returns InferenceResult with overall accuracy percentage.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.ranking.skill_inference import (
    SkillInferenceEngine,
    WEIGHT_INFERRED,
)
from tests.benchmark.benchmark_models import InferenceCheck, InferenceResult


def run(config: Dict[str, Any], verbose: bool = True) -> InferenceResult:
    """Run skill inference accuracy benchmark."""
    inf_config = config.get("inference_test_cases", {})
    if not inf_config:
        return InferenceResult()

    engine = SkillInferenceEngine()
    result = InferenceResult()

    if verbose:
        print("\n" + "=" * 78)
        print("  BENCHMARK 4: SKILL INFERENCE ACCURACY")
        print("=" * 78)

    # ── True Positives ──
    tp_cases = inf_config.get("true_positives", [])
    if verbose:
        print("\n  ── True Positives (should match) ──")

    for case in tp_cases:
        c_skill = case["candidate_skill"]
        jd_skill = case["jd_skill"]
        expected_type = case["expected_type"]

        match_result = engine.match_skills([c_skill], [jd_skill])
        match = match_result.all_matches[0] if match_result.all_matches else None

        if match and match.weight >= 0.50:  # Any match counts as TP
            actual_type = match.match_type
            actual_weight = match.weight
            correct = True
            result.true_positives += 1
            explanation = match.explanation
        else:
            actual_type = "no_match"
            actual_weight = 0.0
            correct = False
            result.false_negatives += 1
            explanation = f"Expected {expected_type} but got no match"

        check = InferenceCheck(
            candidate_skill=c_skill,
            jd_skill=jd_skill,
            expected_type=expected_type,
            actual_type=actual_type,
            actual_weight=actual_weight,
            correct=correct,
            explanation=explanation,
        )
        result.checks.append(check)
        result.total += 1

        if verbose:
            icon = "✅" if correct else "❌"
            print(f"    {icon} {c_skill:20s} → {jd_skill:20s} | {actual_type:10s} w={actual_weight:.2f}")

    # ── True Negatives ──
    tn_cases = inf_config.get("true_negatives", [])
    if verbose:
        print("\n  ── True Negatives (should NOT match) ──")

    for case in tn_cases:
        c_skill = case["candidate_skill"]
        jd_skill = case["jd_skill"]

        match_result = engine.match_skills([c_skill], [jd_skill])
        match = match_result.all_matches[0] if match_result.all_matches else None

        # True negative: no match or only related (weight < WEIGHT_INFERRED)
        if match is None or match.weight < WEIGHT_INFERRED:
            correct = True
            result.true_negatives += 1
            actual_type = match.match_type if match else "no_match"
            actual_weight = match.weight if match else 0.0
            explanation = "Correctly not inferred"
        else:
            correct = False
            result.false_positives += 1
            actual_type = match.match_type
            actual_weight = match.weight
            explanation = f"FALSE POSITIVE: {match.explanation}"

        check = InferenceCheck(
            candidate_skill=c_skill,
            jd_skill=jd_skill,
            expected_type="no_match",
            actual_type=actual_type,
            actual_weight=actual_weight,
            correct=correct,
            explanation=explanation,
        )
        result.checks.append(check)
        result.total += 1

        if verbose:
            icon = "✅" if correct else "❌"
            match_info = f"{actual_type} w={actual_weight:.2f}" if actual_weight > 0 else "no match"
            print(f"    {icon} {c_skill:20s} ✗ {jd_skill:20s} | {match_info}")

    result.accuracy = round(
        ((result.true_positives + result.true_negatives) / result.total * 100.0)
        if result.total > 0 else 0.0,
        1
    )

    if verbose:
        print(f"\n  Inference Accuracy: {result.accuracy}%")
        print(f"    True Positives:  {result.true_positives}")
        print(f"    True Negatives:  {result.true_negatives}")
        print(f"    False Positives: {result.false_positives}")
        print(f"    False Negatives: {result.false_negatives}")

    return result
