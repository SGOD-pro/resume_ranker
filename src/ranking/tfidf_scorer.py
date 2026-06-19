"""
tfidf_scorer.py — Lightweight TF-IDF cosine similarity (zero deps)
===================================================================
Tokenization, term frequency, and cosine similarity for text comparison.
Used by experience scoring (title similarity) and keyword scoring.
"""

import math
import re
from typing import Dict, List


def tokenize(text: str) -> List[str]:
    """Simple word tokenizer."""
    return re.findall(r'[a-z0-9]+', text.lower())


def tf(tokens: List[str]) -> Dict[str, float]:
    """Term frequency (normalized by document length)."""
    counts: Dict[str, int] = {}
    for t in tokens:
        counts[t] = counts.get(t, 0) + 1
    total = len(tokens) or 1
    return {t: c / total for t, c in counts.items()}


def cosine_sim(tf1: Dict[str, float], tf2: Dict[str, float]) -> float:
    """Cosine similarity between two TF vectors."""
    if not tf1 or not tf2:
        return 0.0
    common = set(tf1.keys()) & set(tf2.keys())
    if not common:
        return 0.0
    dot = sum(tf1[k] * tf2[k] for k in common)
    mag1 = math.sqrt(sum(v ** 2 for v in tf1.values()))
    mag2 = math.sqrt(sum(v ** 2 for v in tf2.values()))
    if mag1 == 0 or mag2 == 0:
        return 0.0
    return dot / (mag1 * mag2)


def text_cosine_sim(text1: str, text2: str) -> float:
    """Cosine similarity between two text strings."""
    return cosine_sim(tf(tokenize(text1)), tf(tokenize(text2)))
