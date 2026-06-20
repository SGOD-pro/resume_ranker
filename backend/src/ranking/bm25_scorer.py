"""
bm25_scorer.py — BM25-inspired skill scoring
==============================================
Treats each candidate's skill list as a 'document' and JD skills as 'query'.
IDF is computed across all candidates to reward rare skill matches.
"""

import math
from typing import List

from src.registries.skill_registry import match as _skill_match


def bm25_skill_score(candidate_skills: List[str],
                     jd_skills: List[str],
                     all_candidates_skills: List[List[str]],
                     k1: float = 1.5, b: float = 0.75) -> float:
    """
    BM25-inspired skill scoring.
    Treats each candidate's skill list as a 'document' and JD skills as 'query'.
    IDF is computed across all candidates to reward rare skill matches.
    Returns 0.0–100.0.
    """
    if not jd_skills:
        return 100.0  # No requirements = full score

    n_docs = len(all_candidates_skills) or 1
    avg_len = sum(len(s) for s in all_candidates_skills) / n_docs if n_docs else 1.0

    # IDF for each JD skill
    idf = {}
    for jd_sk in jd_skills:
        doc_freq = sum(
            1 for cand_skills in all_candidates_skills
            if any(_skill_match(cs, jd_sk) for cs in cand_skills)
        )
        # BM25 IDF formula
        idf[jd_sk] = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1.0)

    # Score this candidate
    doc_len = len(candidate_skills) or 1
    score = 0.0
    max_possible = 0.0

    for jd_sk in jd_skills:
        # Term frequency: does the candidate have this skill?
        tf_val = 1.0 if any(_skill_match(cs, jd_sk) for cs in candidate_skills) else 0.0
        # BM25 score component
        numerator = tf_val * (k1 + 1)
        denominator = tf_val + k1 * (1 - b + b * doc_len / avg_len)
        score += idf[jd_sk] * (numerator / denominator)
        # Max possible (if candidate had all skills)
        max_numerator = 1.0 * (k1 + 1)
        max_denominator = 1.0 + k1 * (1 - b + b * doc_len / avg_len)
        max_possible += idf[jd_sk] * (max_numerator / max_denominator)

    if max_possible <= 0:
        return 0.0
    return min(100.0, (score / max_possible) * 100.0)
