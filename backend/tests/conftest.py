"""
conftest.py — Shared pytest fixtures for Resume Ranker test suite.
"""

import sys
from pathlib import Path
import pytest

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.ranking.scorer import CandidateScorer


@pytest.fixture(scope="session")
def scorer():
    """Shared CandidateScorer instance."""
    return CandidateScorer()


@pytest.fixture(scope="session")
def candidates():
    """Load candidates from RESUME_DIR or cached json fixtures."""
    from tests.integration.test_scorer import load_all_candidates
    return load_all_candidates(verbose=False)
