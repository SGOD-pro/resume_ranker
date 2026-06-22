"""
output_cleaning.py — Tag stripping, text cleaning, and output normalization
=============================================================================
Functions for cleaning extracted text: removing layout tags, cleaning text
for ranking, and recursively stripping tags from nested data structures.
"""

import re
from typing import Any, Dict


def strip_tags(text: str) -> str:
    """Remove all [TAG]...[/TAG] markup and internal parser tokens from text."""
    if not text:
        return text
    # Remove closing tags: [/NAME], [/TITLE], [/BULLET], [/DATE], etc.
    text = re.sub(r'\[/[A-Z_]+\]', '', text)
    # Remove opening tags: [NAME], [TITLE], [BULLET], [DATE], [JOB_TITLE], [EDU_LINE], etc.
    text = re.sub(r'\[[A-Z][A-Z_]*\]', '', text)
    # Remove mixed-case section tags: [Employment History], [PROFILE], [PERSONAL INFO]
    text = re.sub(r'\[[A-Z][A-Za-z\s&]+\]', '', text)
    # Remove ||LOC: and bare LOC: tags (internal location markers from layout extractor)
    text = re.sub(r'\s*\|{0,2}LOC:[^\n]*', '', text)
    return text.strip()


def clean_text_for_ranking(text: str) -> str:
    """Clean text for ranking fallback: remove tags, emojis, special chars."""
    if not text:
        return ''
    # Remove tags like [SECTION], [/SECTION]
    text = re.sub(r'\[/?[A-Z_]+\]', '', text)
    # Remove (cid:XX) artifacts
    text = re.sub(r'\(cid:\d+\)', '', text)
    # Remove emojis and non-ASCII special chars (keep basic accented letters)
    text = re.sub(r'[^\x20-\x7E\n\t]', ' ', text)
    # Remove excessive special characters but keep basic punctuation
    text = re.sub(r'[^\w\s.,;:!?\-\'\"()/&@#+%]', ' ', text)
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def recursive_strip(obj: Any) -> Any:
    """Recursively strip tags from strings in dict/list structures."""
    if isinstance(obj, str):
        return strip_tags(obj)
    elif isinstance(obj, dict):
        return {k: recursive_strip(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursive_strip(item) for item in obj]
    return obj
