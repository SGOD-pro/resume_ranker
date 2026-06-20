"""
settings.py — Centralized path configuration
===============================================
All paths are resolved relative to PROJECT_ROOT using Path.resolve().
No hardcoded paths anywhere else in the codebase.
"""

from pathlib import Path

# Project root: two levels up from src/config/settings.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data"
RESUME_DIR = DATA_DIR / "resumes"
BENCHMARK_RESUME_DIR = DATA_DIR / "benchmark_resumes"
DICTIONARY_DIR = DATA_DIR / "dictionaries"
SKILLS_DICTIONARY = DICTIONARY_DIR / "skills_dictionary.json"

# ── Benchmark paths ──────────────────────────────────────────────────────────
BENCHMARKS_DIR = PROJECT_ROOT / "benchmarks"
BASELINES_DIR = BENCHMARKS_DIR / "baselines"
REPORTS_DIR = BENCHMARKS_DIR / "reports"
OUTPUTS_DIR = BENCHMARKS_DIR / "outputs"

# ── Source paths ──────────────────────────────────────────────────────────────
SRC_DIR = PROJECT_ROOT / "src"

# ── Temporary files ──────────────────────────────────────────────────────────
TMP_DIR = PROJECT_ROOT / "tmp"

# ── Default resume for CLI ───────────────────────────────────────────────────
DEFAULT_RESUME = RESUME_DIR / "souvik.pdf"
