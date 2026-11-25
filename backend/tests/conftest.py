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


@pytest.fixture(autouse=True)
def configure_test_queue():
    """Ensure tests run against deterministic in-memory LocalQueueAdapter."""
    import os
    from src.infrastructure.queue.local_adapter import LocalQueueAdapter
    from src.infrastructure.queue.queue_manager import set_queue_adapter
    from src.config.aws import get_settings
    os.environ["USE_REAL_SQS"] = "false"
    get_settings.cache_clear()
    adapter = LocalQueueAdapter()
    set_queue_adapter(adapter)
    yield adapter
    set_queue_adapter(None)


@pytest.fixture(scope="session")
def scorer():
    """Shared CandidateScorer instance."""
    return CandidateScorer()


@pytest.fixture(scope="session")
def candidates():
    """Load candidates from RESUME_DIR or cached json fixtures."""
    from tests.integration.test_scorer import load_all_candidates
    return load_all_candidates(verbose=False)
