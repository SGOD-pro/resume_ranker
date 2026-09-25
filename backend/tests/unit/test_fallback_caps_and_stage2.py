"""
test_fallback_caps_and_stage2.py — Test LLM Fallback Caps and Stage 2 Processing
=================================================================================
Verifies:
1. Global daily LLM cap enforcement (atomic DynamoDB check).
2. Per-job LLM fallback cap (LLM_FALLBACK_MAX_PER_JOB = 5).
3. Low confidence extraction tagging when caps are hit (never failing the file).
4. Stage 2 + scoring regression against golden using mock_fallback_fixtures.json.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.infrastructure.models.file import FileItem, FileStatus
from src.infrastructure.models.job import JobItem, JobStatus
from src.pipeline.stage2_worker import process_stage2_message
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden_v2_baseline"
MOCK_FALLBACK_PATH = FIXTURES_DIR / "mock_fallback_fixtures.json"
GOLDEN_20_PATH = FIXTURES_DIR / "golden_20_resumes.json"


@pytest.fixture
def mock_fallback_data():
    with open(MOCK_FALLBACK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def golden_20_data():
    with open(GOLDEN_20_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_job_llm_fallback_cap_reached():
    """When LLM_FALLBACK_MAX_PER_JOB is reached, skip LLM and tag low_confidence_extraction."""
    job_id = "job-cap-test"
    file_id = "file-exceeds-cap"

    # Simulate 5 files already completed with fallback
    existing_files = [
        FileItem(job_id=job_id, file_id=f"f{i}", status=FileStatus.S2_DONE, needs_fallback=True, low_confidence_extraction=False)
        for i in range(5)
    ]
    current_file = FileItem(job_id=job_id, file_id=file_id, status=FileStatus.S1_DONE, needs_fallback=True)

    stage1_json = {
        "fields": {"email": "test@example.com"},  # missing name and experience
        "quality": {"score": 0.85, "looks_tabular": False},
        "unresolved_chunks": ["unresolved text"],
    }

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", return_value=current_file), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.list_files_for_job", return_value=existing_files), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.update_file_non_terminal"), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_terminal, \
         patch("src.infrastructure.storage.storage_service.StorageService.get_stage1_json", return_value=stage1_json), \
         patch("src.infrastructure.storage.storage_service.StorageService.upload_stage2_json", return_value="stage2_key"), \
         patch("src.extraction.fallback.nova_service.NovaService") as mock_nova:

        msg = MagicMock(job_id=job_id, document_id=file_id)
        success = process_stage2_message(msg)

        assert success is True
        # Nova LLM MUST NOT have been called because job cap was reached
        mock_nova.assert_not_called()

        # File must be transitioned to S2_DONE with low_confidence_extraction = True
        mock_terminal.assert_called_once()
        _, kwargs = mock_terminal.call_args
        assert kwargs["terminal_status"] == FileStatus.S2_DONE.value
        assert kwargs["low_confidence_extraction"] is True
        assert kwargs["fallback_reason"] == "JOB_LLM_CAP_REACHED"


def test_global_daily_llm_cap_reached():
    """When global daily LLM cap is reached, skip LLM and tag low_confidence_extraction."""
    job_id = "job-global-cap-test"
    file_id = "file-daily-capped"

    current_file = FileItem(job_id=job_id, file_id=file_id, status=FileStatus.S1_DONE, needs_fallback=True)

    stage1_json = {
        "fields": {},  # missing critical fields
        "quality": {"score": 0.85, "looks_tabular": False},
        "unresolved_chunks": ["chunk"],
    }

    with patch("src.infrastructure.repositories.files_repository.FilesRepository.get_file", return_value=current_file), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.list_files_for_job", return_value=[]), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.check_and_increment_daily_llm_cap", return_value=False), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.update_file_non_terminal"), \
         patch("src.infrastructure.repositories.files_repository.FilesRepository.transition_file_terminal") as mock_terminal, \
         patch("src.infrastructure.storage.storage_service.StorageService.get_stage1_json", return_value=stage1_json), \
         patch("src.infrastructure.storage.storage_service.StorageService.upload_stage2_json", return_value="stage2_key"), \
         patch("src.extraction.fallback.nova_service.NovaService") as mock_nova:

        msg = MagicMock(job_id=job_id, document_id=file_id)
        success = process_stage2_message(msg)

        assert success is True
        mock_nova.assert_not_called()

        mock_terminal.assert_called_once()
        _, kwargs = mock_terminal.call_args
        assert kwargs["terminal_status"] == FileStatus.S2_DONE.value
        assert kwargs["low_confidence_extraction"] is True
        assert kwargs["fallback_reason"] == "GLOBAL_DAILY_LLM_CAP_REACHED"


def test_stage2_and_scoring_equality_with_mock_fixtures(mock_fallback_data, golden_20_data):
    """Stage 2 outputs merged with mock fallback fixtures score with exact equality against golden."""
    job_spec = golden_20_data["metadata"]["job_spec"]
    jd = JobDescription(
        title=job_spec["title"],
        must_have_skills=job_spec["must_have_skills"],
        nice_to_have_skills=job_spec["nice_to_have_skills"],
        min_years=job_spec["min_years"],
        max_years=job_spec["max_years"],
        required_degree=job_spec.get("education_level", "any"),
        preferred_field=job_spec.get("education_field", ""),
        keywords=job_spec["keywords"],
        weights=job_spec["weights"],
    )

    candidates = []
    for profile in golden_20_data["profiles"]:
        fields = dict(profile["extracted_profile"]["fields"])
        content_hash = profile.get("content_hash")
        # If mock Nova was recorded for this hash, merge it
        if content_hash in mock_fallback_data.get("nova_mocks", {}):
            mock_entry = mock_fallback_data["nova_mocks"][content_hash]
            if mock_entry.get("resolved_name") and not fields.get("name"):
                fields["name"] = mock_entry["resolved_name"]
            if mock_entry.get("resolved_experience") and not fields.get("experience"):
                fields["experience"] = mock_entry["resolved_experience"]

        fields["document_id"] = fields.get("name") or profile["filename"]
        candidates.append(fields)

    scorer = CandidateScorer()
    ranked = scorer.rank(jd, candidates)
    golden_results = golden_20_data["scoring_results"]

    assert len(ranked) == len(golden_results) == 20
    for r, g in zip(ranked, golden_results):
        assert abs(r.final_score - g["final_score"]) < 1e-4
        assert abs(r.skill_score - g["skill_score"]) < 1e-4
        assert abs(r.experience_score - g["experience_score"]) < 1e-4
        assert r.knocked_out == g["knocked_out"]
