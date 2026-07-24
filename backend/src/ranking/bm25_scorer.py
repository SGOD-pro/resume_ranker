"""
bm25_scorer.py — BM25-inspired skill scoring
==============================================
Treats each candidate's skill list as a 'document' and JD skills as 'query'.

Two variants:
  bm25_skill_score()           — legacy per-pool IDF (V1 backward compat)
  bm25_skill_score_fixed_idf() — fixed reference-corpus IDF (ADR-04, Phase 4)

The fixed-IDF variant is what ScoringService uses. It is 100% deterministic:
the same candidate scores identically regardless of who else is in the pool.
"""

import math
from collections.abc import Callable

from src.registries.skill_registry import match as _skill_match


def precompute_bm25_idf(jd_skills: list[str],
                        all_candidates_skills: list[list[str]]) -> tuple[dict[str, float], float]:
    """
    Pre-compute IDF values for all JD skills across the candidate pool.
    
    This is the expensive O(n × m) operation (n=candidates, m=jd_skills).
    Call ONCE per JD, then pass the result to bm25_skill_score for each candidate.
    
    Returns:
        (idf_dict, avg_doc_len)
    """
    n_docs = len(all_candidates_skills) or 1
    avg_len = sum(len(s) for s in all_candidates_skills) / n_docs if n_docs else 1.0

    idf = {}
    for jd_sk in jd_skills:
        doc_freq = sum(
            1 for cand_skills in all_candidates_skills
            if any(_skill_match(cs, jd_sk) for cs in cand_skills)
        )
        idf[jd_sk] = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

    return idf, avg_len


def bm25_skill_score(candidate_skills: list[str],  # noqa: PLR0917
                     jd_skills: list[str],
                     all_candidates_skills: list[list[str]],
                     skill_weights: dict[str, float] | None = None,
                     k1: float = 1.5, b: float = 0.75,
                     precomputed_idf: tuple[dict[str, float], float] | None = None) -> float:
    """
    BM25-inspired skill scoring.
    Treats each candidate's skill list as a 'document' and JD skills as 'query'.

    Args:
        candidate_skills: Skills extracted from this candidate's resume.
        jd_skills: Skills required by the JD (must-have + nice-to-have).
        all_candidates_skills: All candidates' skill lists (for IDF).
        skill_weights: Optional {jd_skill: weight} from inference engine.
        k1, b: BM25 tuning parameters.
        precomputed_idf: Optional (idf_dict, avg_len) from precompute_bm25_idf().
            If provided, skips the O(n×m) IDF computation.

    Returns 0.0–100.0.
    """
    if not jd_skills:
        return 100.0  # No requirements = full score

    # Use precomputed IDF if available (avoids O(n²) recomputation)
    if precomputed_idf is not None:
        idf, avg_len = precomputed_idf
    else:
        idf, avg_len = precompute_bm25_idf(jd_skills, all_candidates_skills)

    # Score this candidate
    doc_len = len(candidate_skills) or 1
    score = 0.0
    max_possible = 0.0

    for jd_sk in jd_skills:
        # Term frequency: use inference weight if available, else binary match
        if skill_weights and jd_sk in skill_weights:
            tf_val = skill_weights[jd_sk]
        else:
            tf_val = 1.0 if any(_skill_match(cs, jd_sk) for cs in candidate_skills) else 0.0

        # BM25 score component
        idf_val = idf.get(jd_sk, 0.0)
        numerator = tf_val * (k1 + 1)
        denominator = tf_val + k1 * (1 - b + b * doc_len / avg_len)
        score += idf_val * (numerator / denominator)
        # Max possible (if candidate had all skills with weight 1.0)
        max_numerator = 1.0 * (k1 + 1)
        max_denominator = 1.0 + k1 * (1 - b + b * doc_len / avg_len)
        max_possible += idf_val * (max_numerator / max_denominator)

    if max_possible <= 0:
        return 0.0
    return min(100.0, (score / max_possible) * 100.0)


def bm25_skill_score_fixed_idf(  # noqa: PLR0917
    candidate_skills: list[str],
    jd_skills: list[str],
    get_idf_fn: Callable[[str], float],
    skill_weights: dict[str, float] | None = None,
    avg_doc_len: float = 10.0,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """
    BM25 skill scoring with a fixed reference-corpus IDF (ADR-04).

    Args:
        candidate_skills: Skills extracted from the candidate's resume.
        jd_skills: Skills required by the JD (must-have + nice-to-have).
        get_idf_fn: A callable that returns fixed IDF for a skill token.
                    Typically idf_table.get_idf.
        skill_weights: Optional {jd_skill: weight} from inference engine.
                       Inferred skills arrive at fractional weight (e.g. 0.75).
        avg_doc_len: Average skill-list length in the reference corpus.
                     Default 10.0 (empirically stable — changing this by ±3
                     shifts scores by < 2 points, a negligible effect).
        k1, b: BM25 tuning parameters (V1-inherited, do not change without
               re-running the benchmark).

    Returns 0.0–100.0. Same candidate scores identically regardless of pool.
    """
    if not jd_skills:
        return 100.0     # No requirements = full score

    doc_len = len(candidate_skills) or 1
    score = 0.0
    max_possible = 0.0

    for jd_sk in jd_skills:
        # Term frequency: use inference weight if available, else binary match
        if skill_weights and jd_sk in skill_weights:
            tf_val = skill_weights[jd_sk]
        else:
            tf_val = 1.0 if any(_skill_match(cs, jd_sk) for cs in candidate_skills) else 0.0

        idf_val = get_idf_fn(jd_sk)

        numerator = tf_val * (k1 + 1)
        denominator = tf_val + k1 * (1 - b + b * doc_len / avg_doc_len)
        score += idf_val * (numerator / denominator)

        # Max possible score if candidate had this skill with weight=1.0
        max_num = 1.0 * (k1 + 1)
        max_den = 1.0 + k1 * (1 - b + b * doc_len / avg_doc_len)
        max_possible += idf_val * (max_num / max_den)

    if max_possible <= 0:
        return 0.0
    return min(100.0, (score / max_possible) * 100.0)
