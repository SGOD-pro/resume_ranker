"""
test_extraction_accuracy.py — Benchmark 1: Extraction Accuracy
================================================================
Measures extraction quality against expected values for selected resumes.
Validates: name, skills count, experience count, education count.

Returns ExtractionResult with overall accuracy percentage.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR
from tests.benchmark.benchmark_models import ExtractionCheck, ExtractionResult


def run(config: Dict[str, Any], verbose: bool = True) -> ExtractionResult:
    """Run extraction accuracy benchmark.

    Args:
        config: benchmark_config.json parsed dict
        verbose: print progress to stdout

    Returns:
        ExtractionResult with per-file checks and overall accuracy.
    """
    expectations = config.get("extraction_expectations", {})
    if not expectations:
        return ExtractionResult(errors=["No extraction expectations defined"])

    pipe = PDFPipelineV3()
    result = ExtractionResult()

    if verbose:
        print("\n" + "=" * 78)
        print("  BENCHMARK 1: EXTRACTION ACCURACY")
        print("=" * 78)

    for filename, expected in expectations.items():
        pdf_path = str(RESUME_DIR / filename)
        if not os.path.exists(pdf_path):
            result.errors.append(f"File not found: {filename}")
            continue

        try:
            extraction = pipe.extract(pdf_path)
            fields = json.loads(json.dumps(
                extraction.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
        except Exception as e:
            result.errors.append(f"Extraction failed for {filename}: {e}")
            continue

        pi = fields.get('personal_info', {})
        extracted_name = (pi.get('name') or 'Unknown').strip()
        expected_name = expected.get('expected_name', '')

        skills = fields.get('skills', [])
        experience = fields.get('experience', [])
        education = fields.get('education', [])

        name_correct = _fuzzy_name_match(extracted_name, expected_name)
        skills_pass = len(skills) >= expected.get('min_skills', 0)
        exp_pass = len(experience) >= expected.get('min_experience_entries', 0)
        edu_pass = len(education) >= expected.get('min_education_entries', 0)

        all_pass = name_correct and skills_pass and exp_pass and edu_pass

        check = ExtractionCheck(
            file=filename,
            expected_name=expected_name,
            extracted_name=extracted_name,
            name_correct=name_correct,
            min_skills=expected.get('min_skills', 0),
            actual_skills=len(skills),
            skills_pass=skills_pass,
            min_experience=expected.get('min_experience_entries', 0),
            actual_experience=len(experience),
            experience_pass=exp_pass,
            min_education=expected.get('min_education_entries', 0),
            actual_education=len(education),
            education_pass=edu_pass,
            all_pass=all_pass,
        )
        result.checks.append(check)
        result.total += 1
        if all_pass:
            result.passed += 1

        if verbose:
            icon = "✅" if all_pass else "❌"
            fails = []
            if not name_correct:
                fails.append(f"name(got='{extracted_name}')")
            if not skills_pass:
                fails.append(f"skills({len(skills)}<{expected.get('min_skills',0)})")
            if not exp_pass:
                fails.append(f"exp({len(experience)}<{expected.get('min_experience_entries',0)})")
            if not edu_pass:
                fails.append(f"edu({len(education)}<{expected.get('min_education_entries',0)})")
            detail = " | " + ", ".join(fails) if fails else ""
            print(f"  {icon} {filename:20s} {extracted_name:25s}{detail}")

    result.accuracy = round(
        (result.passed / result.total * 100.0) if result.total > 0 else 0.0, 1
    )

    if verbose:
        print(f"\n  Extraction Accuracy: {result.accuracy}% ({result.passed}/{result.total})")
        if result.errors:
            print(f"  Errors: {len(result.errors)}")
            for e in result.errors:
                print(f"    ⚠ {e}")

    return result


def _fuzzy_name_match(extracted: str, expected: str) -> bool:
    """Case-insensitive name matching with normalization."""
    e1 = extracted.lower().strip()
    e2 = expected.lower().strip()
    if e1 == e2:
        return True
    # Check if all words in expected appear in extracted (handles ordering)
    expected_words = set(e2.split())
    extracted_words = set(e1.split())
    return expected_words.issubset(extracted_words)
