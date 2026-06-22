"""
test_ranking_accuracy.py — Benchmark 2: Ranking Accuracy
==========================================================
Measures whether expected candidates rank in the top positions.

Scoring:
    Top 1 hit  = 100 points
    Top 3 hit  =  75 points
    Top 5 hit  =  50 points
    Miss       =   0 points

Returns RankingResult with overall accuracy percentage.
"""

from __future__ import annotations

import json
import glob
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription
from src.config.settings import RESUME_DIR
from tests.benchmark.benchmark_models import RankingCheck, RankingResult


def _extract_all_candidates(pipe: PDFPipelineV3) -> List[Dict[str, Any]]:
    """Extract all resumes and return as candidate dicts."""
    pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))
    candidates = []
    for pdf in pdfs:
        filename = os.path.basename(pdf)
        try:
            r = pipe.extract(pdf)
            fields = json.loads(json.dumps(
                r.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
            fields['_document_id'] = filename
            if 'extraction_quality' not in fields:
                fields['extraction_quality'] = 0.0
            candidates.append(fields)
        except Exception:
            pass
    return candidates


def _build_jd(jd_config: Dict[str, Any]) -> JobDescription:
    """Build a JobDescription from config dict."""
    return JobDescription(
        title=jd_config.get("title", ""),
        department=jd_config.get("department", ""),
        description=jd_config.get("description", ""),
        must_have_skills=jd_config.get("must_have_skills", []),
        nice_to_have_skills=jd_config.get("nice_to_have_skills", []),
        min_years=jd_config.get("min_years", 0),
        max_years=jd_config.get("max_years", 99),
        required_degree=jd_config.get("required_degree", "any"),
        preferred_field=jd_config.get("preferred_field", ""),
        keywords=jd_config.get("keywords", []),
        weights=jd_config.get("weights", {"skills": 0.40, "experience": 0.25, "keywords": 0.20, "education": 0.15}),
    )


def run(config: Dict[str, Any], verbose: bool = True) -> RankingResult:
    """Run ranking accuracy benchmark.

    For each JD, scores all candidates and checks if expected candidates
    appear in the top positions.
    """
    ranking_cfg = config.get("ranking_expectations", {})
    if not ranking_cfg:
        return RankingResult()

    pipe = PDFPipelineV3()
    scorer = CandidateScorer()
    candidates = _extract_all_candidates(pipe)

    result = RankingResult()

    if verbose:
        print("\n" + "=" * 78)
        print("  BENCHMARK 2: RANKING ACCURACY")
        print("=" * 78)

    total_score = 0.0
    max_score = 0.0

    for jd_name, expectation in ranking_cfg.items():
        jd = _build_jd(expectation["jd"])
        expected_files = expectation.get("expected_top_5", [])

        scored = scorer.rank(jd, candidates)

        # Build rank map: document_id → rank (1-based)
        rank_map: Dict[str, int] = {}
        score_map: Dict[str, float] = {}
        ko_map: Dict[str, bool] = {}
        for r in scored:
            rank_map[r.document_id] = r.rank
            score_map[r.document_id] = r.final_score
            ko_map[r.document_id] = r.knocked_out

        if verbose:
            print(f"\n  ── {jd_name} ──")
            # Show top 5 actual results
            for r in scored[:5]:
                ko = " [KO]" if r.knocked_out else ""
                print(f"    #{r.rank:2d} {r.name:25s} ({r.document_id:20s}) score={r.final_score:5.1f}{ko}")

        for exp_file in expected_files:
            rank = rank_map.get(exp_file, 0)
            knocked_out = ko_map.get(exp_file, False)
            final_score = score_map.get(exp_file, 0.0)

            in_top_1 = rank == 1 and not knocked_out
            in_top_3 = 1 <= rank <= 3 and not knocked_out
            in_top_5 = 1 <= rank <= 5 and not knocked_out

            if in_top_1:
                points = 100.0
                result.top_1_hits += 1
            elif in_top_3:
                points = 75.0
                result.top_3_hits += 1
            elif in_top_5:
                points = 50.0
                result.top_5_hits += 1
            else:
                points = 0.0
                result.misses += 1
                result.mistakes.append({
                    "jd": jd_name,
                    "expected_file": exp_file,
                    "actual_rank": rank,
                    "knocked_out": knocked_out,
                    "score": final_score,
                })

            check = RankingCheck(
                jd_title=jd_name,
                expected_file=exp_file,
                actual_rank=rank,
                in_top_1=in_top_1,
                in_top_3=in_top_3,
                in_top_5=in_top_5,
                knocked_out=knocked_out,
                score=points,
            )
            result.checks.append(check)
            result.total += 1
            total_score += points
            max_score += 100.0

            if verbose:
                if in_top_1:
                    icon = "🏆"
                elif in_top_3:
                    icon = "✅"
                elif in_top_5:
                    icon = "🟡"
                else:
                    icon = "❌"
                ko_label = " [KNOCKED OUT]" if knocked_out else ""
                print(f"    {icon} Expected: {exp_file:20s} → rank #{rank}{ko_label} ({points:.0f}pts)")

    result.accuracy = round(
        (total_score / max_score * 100.0) if max_score > 0 else 0.0, 1
    )

    if verbose:
        print(f"\n  Ranking Accuracy: {result.accuracy}%")
        print(f"    Top-1 hits: {result.top_1_hits}")
        print(f"    Top-3 hits: {result.top_3_hits}")
        print(f"    Top-5 hits: {result.top_5_hits}")
        print(f"    Misses:     {result.misses}")
        if result.mistakes:
            print(f"\n  ── Top Ranking Mistakes ──")
            for m in result.mistakes:
                print(f"    {m['jd']:30s} | {m['expected_file']:20s} → rank #{m['actual_rank']} (KO={m['knocked_out']})")

    return result
