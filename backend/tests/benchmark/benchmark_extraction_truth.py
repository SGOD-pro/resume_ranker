"""
benchmark_extraction_truth.py — Ground Truth Extraction Benchmark
====================================================================
Validates extraction output against manually reviewed PDF ground truth.

Ground truth file: tests/ground_truth/ground_truth_extraction.json
Each entry contains:
  - name: exact expected name from PDF
  - min_skills: minimum number of skills expected
  - min_experience: minimum number of experience entries expected
  - min_education: minimum number of education entries expected

This benchmark compares ACTUAL extraction against PDF TRUTH,
not against previous extraction output.
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR


GROUND_TRUTH_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'ground_truth', 'ground_truth_extraction.json'
)


@pytest.fixture(scope="module")
def pipeline():
    return PDFPipelineV3()


@pytest.fixture(scope="module")
def ground_truth():
    with open(GROUND_TRUTH_PATH, 'r') as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_extractions(pipeline, ground_truth):
    """Extract all PDFs once and cache results."""
    results = {}
    for pdf_name in ground_truth:
        pdf_path = str(RESUME_DIR / pdf_name)
        if os.path.exists(pdf_path):
            results[pdf_name] = pipeline.extract(pdf_path)
    return results


class TestGroundTruthExtraction:
    """Test extraction output against manually verified ground truth."""

    def test_ground_truth_file_exists(self):
        assert os.path.exists(GROUND_TRUTH_PATH), \
            f"Ground truth file not found: {GROUND_TRUTH_PATH}"

    def test_ground_truth_has_entries(self, ground_truth):
        assert len(ground_truth) >= 5, \
            f"Ground truth should have at least 5 entries, got {len(ground_truth)}"

    @pytest.mark.parametrize("pdf_name", [
        "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
    ])
    def test_name_extraction(self, all_extractions, ground_truth, pdf_name):
        """Verify extracted name matches PDF ground truth."""
        if pdf_name not in all_extractions:
            pytest.skip(f"PDF not found: {pdf_name}")
        result = all_extractions[pdf_name]
        expected_name = ground_truth[pdf_name]["name"]
        actual_name = result.fields.get("personal_info", {}).get("name")
        assert actual_name is not None, f"No name extracted for {pdf_name}"
        assert actual_name.lower() == expected_name.lower(), \
            f"{pdf_name}: expected name '{expected_name}', got '{actual_name}'"

    @pytest.mark.parametrize("pdf_name", [
        "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
    ])
    def test_skills_count(self, all_extractions, ground_truth, pdf_name):
        """Verify minimum skill count from ground truth."""
        if pdf_name not in all_extractions:
            pytest.skip(f"PDF not found: {pdf_name}")
        result = all_extractions[pdf_name]
        min_skills = ground_truth[pdf_name]["min_skills"]
        actual_skills = len(result.fields.get("skills", []))
        assert actual_skills >= min_skills, \
            f"{pdf_name}: expected >= {min_skills} skills, got {actual_skills}"

    @pytest.mark.parametrize("pdf_name", [
        "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
    ])
    def test_experience_count(self, all_extractions, ground_truth, pdf_name):
        """Verify minimum experience entry count from ground truth."""
        if pdf_name not in all_extractions:
            pytest.skip(f"PDF not found: {pdf_name}")
        result = all_extractions[pdf_name]
        min_exp = ground_truth[pdf_name]["min_experience"]
        actual_exp = len(result.fields.get("experience", []))
        assert actual_exp >= min_exp, \
            f"{pdf_name}: expected >= {min_exp} experience entries, got {actual_exp}"

    @pytest.mark.parametrize("pdf_name", [
        "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
    ])
    def test_education_count(self, all_extractions, ground_truth, pdf_name):
        """Verify minimum education entry count from ground truth."""
        if pdf_name not in all_extractions:
            pytest.skip(f"PDF not found: {pdf_name}")
        result = all_extractions[pdf_name]
        min_edu = ground_truth[pdf_name]["min_education"]
        actual_edu = len(result.fields.get("education", []))
        assert actual_edu >= min_edu, \
            f"{pdf_name}: expected >= {min_edu} education entries, got {actual_edu}"

    @pytest.mark.parametrize("pdf_name", [
        "frontend.pdf", "backend.pdf", "fullstack.pdf", "devops.pdf", "front-end.pdf",
    ])
    def test_no_section_header_as_name(self, all_extractions, pdf_name):
        """Verify name is not a section header or skill phrase."""
        if pdf_name not in all_extractions:
            pytest.skip(f"PDF not found: {pdf_name}")
        result = all_extractions[pdf_name]
        name = result.fields.get("personal_info", {}).get("name", "")
        if not name:
            return  # No name is tested separately

        from src.registries.section_registry import resolve
        assert not resolve(name), \
            f"{pdf_name}: name '{name}' resolves to section header '{resolve(name)}'"

        # Common skill/header phrases that should never be names
        bad_names = {
            'javascript expertise', 'cross-functional teamwork',
            'self-starter', 'strengths', 'skills', 'summary',
            'experience', 'education', 'projects',
        }
        assert name.lower() not in bad_names, \
            f"{pdf_name}: name '{name}' is a section header/skill phrase"
