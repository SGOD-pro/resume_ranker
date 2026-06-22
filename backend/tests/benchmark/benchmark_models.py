"""
benchmark_models.py — Data models for benchmark results
=========================================================
Provides typed result classes and the overall BenchmarkReport that
aggregates all 5 benchmark categories into a production readiness score.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExtractionCheck:
    """Result of a single extraction accuracy check."""
    file: str
    expected_name: str
    extracted_name: str
    name_correct: bool
    min_skills: int
    actual_skills: int
    skills_pass: bool
    min_experience: int
    actual_experience: int
    experience_pass: bool
    min_education: int
    actual_education: int
    education_pass: bool
    all_pass: bool


@dataclass
class ExtractionResult:
    """Aggregate extraction benchmark result."""
    checks: List[ExtractionCheck] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    accuracy: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class RankingCheck:
    """Result of a single ranking expectation check."""
    jd_title: str
    expected_file: str
    actual_rank: int  # 0 = not found in results
    in_top_1: bool = False
    in_top_3: bool = False
    in_top_5: bool = False
    knocked_out: bool = False
    score: float = 0.0  # 100/75/50/0 based on position


@dataclass
class RankingResult:
    """Aggregate ranking benchmark result."""
    checks: List[RankingCheck] = field(default_factory=list)
    total: int = 0
    top_1_hits: int = 0
    top_3_hits: int = 0
    top_5_hits: int = 0
    misses: int = 0
    accuracy: float = 0.0  # weighted score
    mistakes: List[Dict[str, Any]] = field(default_factory=list)  # top ranking mistakes


@dataclass
class RejectionCheck:
    """Result of a single cross-domain rejection check."""
    name: str
    candidate_file: str
    jd_title: str
    expected_rejected: bool
    actually_rejected: bool
    final_score: float
    correct: bool
    detail: str = ""


@dataclass
class RejectionResult:
    """Aggregate cross-domain rejection benchmark result."""
    checks: List[RejectionCheck] = field(default_factory=list)
    total: int = 0
    correct_rejections: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    accuracy: float = 0.0


@dataclass
class InferenceCheck:
    """Result of a single inference test case."""
    candidate_skill: str
    jd_skill: str
    expected_type: str  # "inferred", "alias", "explicit", or "no_match"
    actual_type: str
    actual_weight: float
    correct: bool
    explanation: str = ""


@dataclass
class InferenceResult:
    """Aggregate inference benchmark result."""
    checks: List[InferenceCheck] = field(default_factory=list)
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    total: int = 0
    accuracy: float = 0.0


@dataclass
class APICheck:
    """Result of a single API endpoint check."""
    endpoint: str
    method: str
    status_code: int
    passed: bool
    detail: str = ""
    response_time_ms: float = 0.0


@dataclass
class APIResult:
    """Aggregate API E2E benchmark result."""
    checks: List[APICheck] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    accuracy: float = 0.0
    debug_jd_match: bool = False


@dataclass
class BenchmarkReport:
    """Complete benchmark report with all 5 categories."""
    timestamp: str = ""
    version: str = "1.0.0"

    extraction: ExtractionResult = field(default_factory=ExtractionResult)
    ranking: RankingResult = field(default_factory=RankingResult)
    rejection: RejectionResult = field(default_factory=RejectionResult)
    inference: InferenceResult = field(default_factory=InferenceResult)
    api: APIResult = field(default_factory=APIResult)

    overall_score: float = 0.0
    production_ready: bool = False
    failing_gates: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def compute_overall(self, weights: Dict[str, float], gates: Dict[str, float]):
        """Compute weighted overall score and production readiness."""
        self.overall_score = round(
            self.extraction.accuracy * weights.get("extraction_accuracy", 0.30) +
            self.ranking.accuracy * weights.get("ranking_accuracy", 0.40) +
            self.rejection.accuracy * weights.get("rejection_accuracy", 0.15) +
            self.inference.accuracy * weights.get("inference_accuracy", 0.10) +
            self.api.accuracy * weights.get("api_reliability", 0.05),
            1
        )

        self.failing_gates = []
        gate_map = {
            "extraction_accuracy": self.extraction.accuracy,
            "ranking_accuracy": self.ranking.accuracy,
            "rejection_accuracy": self.rejection.accuracy,
            "inference_accuracy": self.inference.accuracy,
            "api_reliability": self.api.accuracy,
        }
        for gate, threshold in gates.items():
            actual = gate_map.get(gate, 0.0)
            if actual < threshold:
                self.failing_gates.append(f"{gate}: {actual:.1f}% < {threshold:.1f}%")

        self.production_ready = len(self.failing_gates) == 0

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def save(self, path: str):
        with open(path, 'w') as f:
            f.write(self.to_json())
