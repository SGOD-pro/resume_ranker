"""
quality_scoring.py — Extraction quality assessment functions
==============================================================
Evaluates the quality of PDF text extraction and structured data.
Used by the pipeline to flag garbled documents and compute
extraction confidence scores.
"""

import re
from typing import Any, Dict, List


def compute_quality(personal_info: dict, skills: list,
                    experience: list, education: list) -> float:
    """Compute extraction quality score (0.0 to 1.0).
    Higher = more structured data was successfully extracted.
    Used by ranker to decide how much to weight structured vs raw text."""
    score = 0.0
    total = 6.0

    # Name (most basic field)
    if personal_info.get('name'):
        score += 1.0

    # Email
    if personal_info.get('email'):
        score += 1.0

    # Skills (critical for ranking)
    if skills and len(skills) >= 3:
        score += 1.0
    elif skills:
        score += 0.5

    # Experience
    if experience and len(experience) >= 1:
        # Check quality: at least one entry has both role and company
        good = any(e.get('role') and e.get('company') for e in experience)
        score += 1.0 if good else 0.5

    # Education
    if education and len(education) >= 1:
        good = any(e.get('degree') and e.get('institution') for e in education)
        score += 1.0 if good else 0.5

    # Location or phone (supporting info)
    if personal_info.get('location') or personal_info.get('phone'):
        score += 1.0

    return round(score / total, 2)


def compute_text_quality(text: str) -> float:
    """Compute text extraction quality score (0.0 to 1.0).

    Detects corrupted PDF text extraction by checking:
    - Alphabetic character ratio (< 0.4 = likely corrupt)
    - Average word length (< 2.0 = likely garbled)
    - Excessive non-printable characters
    - Known corruption patterns (cid: references)

    Returns:
        0.0-1.0 where < 0.5 indicates likely corruption
    """
    if not text or len(text) < 10:
        return 0.0

    # Strip tags for analysis
    clean = re.sub(r'\[/?[A-Z_]+\]', '', text)
    if not clean.strip():
        return 0.0

    total_chars = len(clean)
    alpha_chars = sum(1 for c in clean if c.isalpha())
    alpha_ratio = alpha_chars / total_chars

    # Average word length
    words = clean.split()
    valid_words = [w for w in words if len(w) > 0]
    avg_word_len = sum(len(w) for w in valid_words) / len(valid_words) if valid_words else 0

    # Non-printable characters (excluding newlines, tabs)
    non_print = sum(1 for c in clean if not c.isprintable() and c not in '\n\r\t')
    non_print_ratio = non_print / total_chars

    # (cid:XX) pattern count
    cid_count = len(re.findall(r'\(cid:\d+\)', clean))
    cid_penalty = min(cid_count * 0.1, 0.5)

    # Garbled pattern: consecutive non-alpha characters (3+)
    garbled_runs = len(re.findall(r'[^a-zA-Z\s,.\-:;()]{3,}', clean))
    garbled_penalty = min(garbled_runs * 0.02, 0.3)

    # Compose score
    score = 1.0
    if alpha_ratio < 0.4:
        score -= 0.5
    elif alpha_ratio < 0.6:
        score -= 0.2

    if avg_word_len < 2.0:
        score -= 0.3
    elif avg_word_len < 3.0:
        score -= 0.1

    score -= non_print_ratio * 2
    score -= cid_penalty
    score -= garbled_penalty

    return round(max(0.0, min(1.0, score)), 2)


def compute_semantic_quality(text: str) -> float:
    """Detect semantically garbled text using linguistic heuristics.

    Checks if words have patterns consistent with natural English:
    - Contain vowels (garbled text often has runs of consonants)
    - Reasonable consonant-to-vowel ratio
    - Not excessive unusual character patterns

    Words like 'PreneCt', 'mCntagra@', 'oiCkeIiC' fail these checks.

    Returns:
        0.0-1.0 where < 0.5 indicates semantic corruption
    """
    if not text or len(text) < 20:
        return 0.0

    # Strip tags and get words
    clean = re.sub(r'\[/?[A-Z_]+\]', '', text)
    words = re.findall(r'[a-zA-Z]{3,}', clean)

    if len(words) < 5:
        return 0.5  # too few words to judge

    vowels = set('aeiouAEIOU')

    def looks_english(word: str) -> bool:
        """Check if a word has plausible English-like structure."""
        w = word.lower()
        # Must contain at least one vowel
        if not any(c in vowels for c in w):
            return False
        # No more than 4 consecutive consonants (unusual in English)
        consonant_run = 0
        max_consonant_run = 0
        for c in w:
            if c not in vowels:
                consonant_run += 1
                max_consonant_run = max(max_consonant_run, consonant_run)
            else:
                consonant_run = 0
        if max_consonant_run > 5:
            return False
        # Check mid-word capitalization (garbled: 'PreneCt', 'oiCkeIiC')
        if len(word) > 2:
            mid = word[1:-1]
            mid_upper = sum(1 for c in mid if c.isupper())
            if mid_upper > len(mid) * 0.3 and len(mid) > 2:
                return False
        return True

    plausible = sum(1 for w in words if looks_english(w))
    ratio = plausible / len(words)

    # Score: >80% plausible = good text, <50% = garbled
    if ratio >= 0.8:
        return 1.0
    elif ratio >= 0.6:
        return 0.7
    elif ratio >= 0.5:
        return 0.5
    else:
        return 0.2


def remove_duplicate_blocks(text: str) -> str:
    """Remove duplicate content blocks from text.

    Some PDFs produce repeated sections (e.g., sidebar + main overlap).
    This deduplicates by comparing normalized line blocks.

    Returns text with duplicate blocks removed.
    """
    lines = text.split('\n')
    if len(lines) < 10:
        return text  # too short to have meaningful duplicates

    # Normalize and hash blocks of 3+ consecutive non-empty lines
    seen_blocks: set = set()
    result_lines: list = []
    block: list = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if block:
                block_key = ' '.join(
                    re.sub(r'\s+', ' ', l.strip().lower()) for l in block
                )
                if len(block_key) > 50 and block_key in seen_blocks:
                    # Duplicate — skip this block
                    block = []
                    result_lines.append('')  # keep blank line
                    continue
                seen_blocks.add(block_key)
                result_lines.extend(block)
                block = []
            result_lines.append(line)
        else:
            block.append(line)

    # Flush final block
    if block:
        block_key = ' '.join(
            re.sub(r'\s+', ' ', l.strip().lower()) for l in block
        )
        if not (len(block_key) > 50 and block_key in seen_blocks):
            result_lines.extend(block)

    return '\n'.join(result_lines)
