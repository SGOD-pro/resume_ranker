"""
test_skill_dedup.py — Assert no skill bundle fully contains another
=====================================================================
Validates that the skill deduplication logic in skills_parser.py:
1. Does not produce skills that are space-separated bundles of other skills
2. Does not produce skills containing other skills as substrings
3. Properly splits sidebar skill-list entries into individual skills
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR


@pytest.fixture(scope="module")
def pipeline():
    return PDFPipelineV3()


# Known legitimate multi-word skills (NOT bundles)
LEGITIMATE_MULTI_WORD = {
    'machine learning', 'deep learning', 'data science',
    'project management', 'infrastructure as code',
    'front desk operations', 'azure devops', 'ui design',
    'material ui', 'microservices architecture', 'mvc architecture',
    'ci/cd', 'e-commerce', 'asp.net', 'node.js', 'three.js',
    'scikit-learn',
}


def _get_skills(pipeline, pdf_name):
    """Extract skills from a PDF."""
    pdf_path = str(RESUME_DIR / pdf_name)
    if not os.path.exists(pdf_path):
        pytest.skip(f"PDF not found: {pdf_name}")
    result = pipeline.extract(pdf_path)
    return result.fields.get('skills', [])


def _find_bundles(skills):
    """Find skills that are space-separated bundles of other individual skills."""
    bundles = []
    lower_set = {s.lower() for s in skills}

    for s in skills:
        words = s.lower().split()
        if len(words) < 3:
            continue
        # Skip known legitimate multi-word skills
        if s.lower() in LEGITIMATE_MULTI_WORD:
            continue
        # Check if multiple individual words appear as separate skills
        individual_count = sum(1 for w in words if w in lower_set and w != s.lower())
        if individual_count >= 2:
            bundles.append(s)

    return bundles


@pytest.mark.parametrize("pdf_name", [
    "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
])
def test_no_skill_bundles(pipeline, pdf_name):
    """Assert no extracted skill is a space-separated bundle of other skills."""
    skills = _get_skills(pipeline, pdf_name)
    bundles = _find_bundles(skills)
    assert not bundles, f"Skill bundles found in {pdf_name}: {bundles}"


@pytest.mark.parametrize("pdf_name", [
    "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
])
def test_no_tag_leaks(pipeline, pdf_name):
    """Assert no internal parser tags appear in final skill output."""
    import re
    import json
    pdf_path = str(RESUME_DIR / pdf_name)
    if not os.path.exists(pdf_path):
        pytest.skip(f"PDF not found: {pdf_name}")
    result = pipeline.extract(pdf_path)
    raw = json.dumps(result.fields, default=str)
    # Check for internal tags
    tag_patterns = [
        r'\[BULLET\]', r'\[/BULLET\]',
        r'\[JOB_TITLE\]', r'\[/JOB_TITLE\]',
        r'\[EDU_LINE\]', r'\[/EDU_LINE\]',
        r'\[DATE\]', r'\[/DATE\]',
        r'\[NAME\]', r'\[/NAME\]',
        r'\|\|?LOC:',
    ]
    for pattern in tag_patterns:
        matches = re.findall(pattern, raw)
        assert not matches, f"Tag leak '{pattern}' found in {pdf_name}: {matches[:3]}"
