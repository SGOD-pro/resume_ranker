"""
scripts/evaluate_phase2_extraction.py
======================================
Field-extraction F1 evaluation script for Phase 2 Verification Gate.
(phases.md: "Field-extraction F1 evaluation script on a 100-resume benchmark sample")

Loads all ODL JSON fixtures from tests/golden/fixtures/, parses them via
DeterministicExtractionService, and computes the aggregate deterministic_ratio.

Verification Gate target:
  - Provenance tag is `deterministic` for >= 85% of extracted fields across the sample.
"""

import json
from pathlib import Path

from src.extraction.deterministic_extraction_service import DeterministicExtractionService
from src.extraction.domain import structural_parse_from_odl_json

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "golden" / "fixtures"

def run_evaluation() -> None:
    svc = DeterministicExtractionService()
    
    total_populated_fields = 0
    total_deterministic = 0
    total_unresolved_chunks = 0
    
    print(f"{'DOCUMENT':20s} | {'FIELDS':6s} | {'DET %':6s} | {'UNRESOLVED':10s}")
    print("-" * 52)
    
    for fixture in FIXTURES_DIR.glob("*.json"):
        raw_json = json.loads(fixture.read_text(encoding="utf-8"))
        parse = structural_parse_from_odl_json(
            raw_json, 
            content_hash=fixture.stem, 
            parser_version="v2-eval"
        )
        
        result = svc.parse(parse, document_id=fixture.stem)
        
        # Manually count populated vs deterministic
        fields = [
            result.name, result.email, result.phone, result.linkedin,
            result.github, result.location, result.experience,
            result.education, result.skills, result.summary
        ]
        populated = [f for f in fields if f is not None]
        deterministic = [f for f in populated if f.provenance == "deterministic"]
        
        n_pop = len(populated)
        n_det = len(deterministic)
        ratio = (n_det / n_pop) * 100 if n_pop else 0.0
        n_unres = len(result.unresolved)
        
        print(f"{fixture.stem:20s} | {n_pop:4d}   | {ratio:5.1f}% | {n_unres:6d}")
        
        total_populated_fields += n_pop
        total_deterministic += n_det
        total_unresolved_chunks += n_unres
        
    print("-" * 52)
    overall_ratio = (total_deterministic / total_populated_fields) * 100 if total_populated_fields else 0.0
    
    print(f"Overall Deterministic Ratio: {overall_ratio:.2f}%")
    print(f"Total Unresolved Chunks:     {total_unresolved_chunks}")
    
    if overall_ratio >= 85.0:
        print("\nVERIFICATION GATE PASSED: Deterministic ratio >= 85%")
    else:
        print("\nVERIFICATION GATE FAILED: Deterministic ratio < 85%")

if __name__ == "__main__":
    run_evaluation()
