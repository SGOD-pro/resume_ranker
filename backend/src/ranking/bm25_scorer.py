"""
bm25_scorer.py — BM25-inspired skill scoring
==============================================
Treats each candidate's skill list as a 'document' and JD skills as 'query'.
IDF is computed across all candidates to reward rare skill matches.

Supports inference-weighted matching: inferred skills contribute at fractional
weights (e.g., 0.75) instead of binary 1.0.
"""

import math
from typing import Dict, List, Optional, Tuple


from src.registries.skill_registry import match as _skill_match


def precompute_bm25_idf(jd_skills: List[str],
                        all_candidates_skills: List[List[str]]) -> Tuple[Dict[str, float], float]:
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


def bm25_skill_score(candidate_skills: List[str],
                     jd_skills: List[str],
                     all_candidates_skills: List[List[str]],
                     skill_weights: Optional[Dict[str, float]] = None,
                     k1: float = 1.5, b: float = 0.75,
                     precomputed_idf: Optional[Tuple[Dict[str, float], float]] = None) -> float:
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

