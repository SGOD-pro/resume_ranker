"""
similarity.py — Experience, Keyword, and Education scoring
============================================================
Multi-signal scoring functions for candidate evaluation.
Each returns a 0-100 score for its dimension.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from src.ranking.tfidf_scorer import tf, tokenize, cosine_sim, text_cosine_sim


# ─────────────────────────────────────────────────────────────────────────────
# Date / Experience Year Calculations
# ─────────────────────────────────────────────────────────────────────────────

_MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'june': 6, 'july': 7, 'august': 8, 'september': 9,
    'october': 10, 'november': 11, 'december': 12,
}


def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a date string like 'January 2021', 'Jan 2021', '2021', 'Present'."""
    if not date_str:
        return None
    d = date_str.strip().lower()
    if d in ('present', 'current', 'now', 'ongoing'):
        return datetime.now()

    # Try "Month Year" format
    m = re.match(r'(\w+)\s+(\d{4})', d)
    if m:
        month_str, year = m.group(1), int(m.group(2))
        month = _MONTH_MAP.get(month_str, 1)
        return datetime(year, month, 1)

    # Try just year
    m = re.match(r'^(\d{4})$', d)
    if m:
        return datetime(int(m.group(1)), 6, 1)  # Assume mid-year

    return None


def compute_total_experience_years(experience: List[Dict[str, Any]]) -> float:
    """Calculate total years of experience from date ranges. Handles overlapping."""
    if not experience:
        return 0.0

    # Parse all date ranges
    ranges = []
    for exp in experience:
        start = parse_date(exp.get('start'))
        end = parse_date(exp.get('end'))
        if start and end and end > start:
            ranges.append((start, end))

    if not ranges:
        return 0.0

    # Sort and merge overlapping ranges
    ranges.sort(key=lambda x: x[0])
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    # Sum total days
    total_days = sum((end - start).days for start, end in merged)
    return round(total_days / 365.25, 1)


def most_recent_end_date(experience: List[Dict[str, Any]]) -> Optional[datetime]:
    """Get the most recent job end date."""
    latest = None
    for exp in experience:
        end = parse_date(exp.get('end'))
        if end and (latest is None or end > latest):
            latest = end
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Experience Scoring
# ─────────────────────────────────────────────────────────────────────────────

def experience_score(candidate: Dict[str, Any],
                     jd) -> Tuple[float, str]:
    """
    Score experience based on:
      - Title similarity to JD title (40%)
      - Years in desired range (40%)
      - Recency of most recent role (20%)
    Returns (score 0-100, best_matching_title).
    """
    experience = candidate.get('experience', [])
    total_years = compute_total_experience_years(experience)

    # ── Title similarity ──────────────────────────────────────────────────
    jd_title_tokens = tf(tokenize(jd.title))
    best_sim = 0.0
    best_title = ""
    for exp in experience:
        role = exp.get('role') or ''
        sim = cosine_sim(tf(tokenize(role)), jd_title_tokens)
        if sim > best_sim:
            best_sim = sim
            best_title = role
    title_score = min(1.0, best_sim * 1.5) * 100.0  # Boost and cap at 100

    # ── Years in range ────────────────────────────────────────────────────
    if jd.min_years == 0 and jd.max_years >= 99:
        years_score = 100.0  # No requirement
    elif total_years >= jd.min_years and total_years <= jd.max_years:
        years_score = 100.0
    elif total_years < jd.min_years:
        # Partial credit: linear scale down
        if jd.min_years > 0:
            ratio = total_years / jd.min_years
        else:
            ratio = 1.0
        years_score = max(0.0, ratio * 80.0)
    else:
        # Over max: slight penalty but still good
        years_score = 80.0

    # ── Recency ───────────────────────────────────────────────────────────
    most_recent = most_recent_end_date(experience)
    if most_recent:
        years_ago = (datetime.now() - most_recent).days / 365.25
        if years_ago <= 0.5:
            recency_score = 100.0   # Currently employed or very recent
        elif years_ago <= 2:
            recency_score = 85.0
        elif years_ago <= 5:
            recency_score = 60.0
        else:
            recency_score = 30.0
    else:
        recency_score = 20.0 if not experience else 50.0

    # Combine: 40% title + 40% years + 20% recency
    final = title_score * 0.4 + years_score * 0.4 + recency_score * 0.2
    return final, best_title


# ─────────────────────────────────────────────────────────────────────────────
# Keyword Scoring
# ─────────────────────────────────────────────────────────────────────────────

def keyword_score(candidate: Dict[str, Any],
                  jd) -> Tuple[float, List[str], List[str]]:
    """
    Score keyword overlap between JD keywords and candidate's full text.
    Uses alias expansion so 'backend'/'back-end'/'server-side' all match,
    and skill aliases so 'Node.js'/'nodejs'/'node' all match.
    Returns (score 0-100, matched_keywords, missing_keywords).
    """
    from src.registries.skill_registry import (
        get_search_variants, normalize as _normalize, SKILL_ALIASES, match as _skill_match
    )

    if not jd.keywords:
        return 100.0, [], []

    full_text = (candidate.get('raw_text_sections', {}).get('full_text', '') or '').lower()
    # Also include structured fields as text
    skills_list = candidate.get('skills', [])
    skills_text = ' '.join(skills_list).lower()
    summary_text = (candidate.get('summary') or '').lower()
    all_text = f"{full_text} {skills_text} {summary_text}"

    matched = []
    missing = []
    for kw in jd.keywords:
        found = False
        kw_lower = kw.lower().strip()

        # Strategy 1: Check all surface-form variants in raw text
        variants = get_search_variants(kw)
        for variant in variants:
            # Word-boundary check for single-word variants
            if ' ' not in variant and '-' not in variant:
                if re.search(r'\b' + re.escape(variant) + r'\b', all_text):
                    found = True
                    break
            else:
                # Multi-word/hyphenated: plain substring
                if variant in all_text:
                    found = True
                    break

        # Strategy 2: Check if any extracted skill matches via alias resolution
        if not found:
            for skill in skills_list:
                if _skill_match(skill, kw):
                    found = True
                    break

        if found:
            matched.append(kw)
        else:
            missing.append(kw)

    score = (len(matched) / len(jd.keywords)) * 100.0
    return score, matched, missing


# ─────────────────────────────────────────────────────────────────────────────
# Education Scoring
# ─────────────────────────────────────────────────────────────────────────────

# Import degree level parsing from scorer (stays in scorer for now since
# it's also used by knockout logic)
def _parse_degree_level_local(degree_str: str) -> int:
    """Convert a degree string to a numeric level."""
    if not degree_str:
        return 0
    d = degree_str.lower().strip()
    _DEGREE_LEVELS = {
        "phd": 5, "doctorate": 5, "ph.d": 5,
        "master": 4, "masters": 4, "mba": 4, "m.s": 4, "m.a": 4, "msc": 4,
        "m.sc": 4, "m.tech": 4, "mtech": 4,
        "bachelor": 3, "bachelors": 3, "b.s": 3, "b.a": 3, "bsc": 3,
        "b.sc": 3, "b.tech": 3, "btech": 3, "bca": 3, "b.e": 3, "be": 3,
        "associate": 2, "associates": 2, "diploma": 2,
        "class 12": 1, "12th": 1, "high school": 1,
        "class 10": 0, "10th": 0,
        "any": -1, "none": 0,
    }
    for key, val in _DEGREE_LEVELS.items():
        if key in d:
            return val
    return 0


def education_score(candidate: Dict[str, Any],
                    jd) -> Tuple[float, str, str]:
    """
    Score education based on:
      - Degree level match (60%)
      - Field of study similarity (40%)
    Returns (score 0-100, best_degree, best_field).
    """
    education = candidate.get('education', [])

    # Find highest degree
    best_level = 0
    best_degree = ""
    best_field = ""
    for edu in education:
        degree = edu.get('degree') or ''
        level = _parse_degree_level_local(degree)
        if level > best_level:
            best_level = level
            best_degree = degree
            best_field = degree  # Field is usually embedded in degree string

    required_level = _parse_degree_level_local(jd.required_degree)

    # ── Degree level match ────────────────────────────────────────────────
    if required_level <= 0:
        # "any" requirement = full score
        degree_match = 100.0
    elif best_level >= required_level:
        degree_match = 100.0
    elif best_level == required_level - 1:
        degree_match = 60.0  # One level below
    elif best_level > 0:
        degree_match = 30.0  # Has some education
    else:
        degree_match = 0.0   # No education at all

    # ── Field similarity ──────────────────────────────────────────────────
    if not jd.preferred_field or jd.preferred_field.lower() in ('any', '', 'related'):
        field_sim = 100.0
    else:
        # Check all education entries for field match
        best_field_score = 0.0
        for edu in education:
            degree_text = (edu.get('degree') or '') + ' ' + (edu.get('institution') or '')
            sim = text_cosine_sim(degree_text, jd.preferred_field)
            if sim > best_field_score:
                best_field_score = sim
                best_field = edu.get('degree') or ''
        # Also check raw text for field keywords
        raw_text = candidate.get('raw_text_sections', {}).get('full_text', '')
        if jd.preferred_field.lower() in raw_text.lower():
            best_field_score = max(best_field_score, 0.7)
        field_sim = min(100.0, best_field_score * 130.0)  # Boost cosine scores

    # Combine: 60% degree level + 40% field
    final = degree_match * 0.6 + field_sim * 0.4
    return final, best_degree, best_field
