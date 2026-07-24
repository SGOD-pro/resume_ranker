"""
check_imports.py — CI-enforced import restriction verification
================================================================
Per rules.md §8: vendor SDK imports are restricted to their ACL classes.
Exit code 1 on any violation.

Usage:
    python scripts/check_imports.py
"""

import ast
import sys
from pathlib import Path

# Map of restricted import → list of files allowed to import it.
# Paths are relative to backend/src/.
RESTRICTED_IMPORTS: dict[str, list[str]] = {
    "opendataloader_pdf": ["extraction/structural_parsing_service.py"],
    "boto3": [
        "extraction/nova_fallback_service.py",
        "infrastructure/storage/s3_client.py",
        # V1 legacy files — allowed during migration, removed in later phases
        "infrastructure/health.py",
        "config/aws.py",
        # V1 DynamoDB repositories — replaced by Postgres in Phase 4+
        "infrastructure/repositories/base.py",
        "infrastructure/repositories/documents_repository.py",
        "infrastructure/repositories/jobs_repository.py",
        "infrastructure/repositories/scoring_repository.py",
        "infrastructure/scripts/create_tables.py",
        "infrastructure/storage/storage_service.py",
    ],
    "anthropic": ["extraction/nova_fallback_service.py"],
    "sentence_transformers": ["ranking/embedding_tiebreaker.py"],
    # PyMuPDF — completely banned in V2. No files are allowed.
    "fitz": [],
    "pymupdf": [],
}

SRC_ROOT = Path(__file__).resolve().parent.parent / "src"


def _get_imports(filepath: Path) -> set[str]:
    """Extract top-level module names from import statements in a Python file."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return set()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def check() -> int:
    """Scan all .py files under src/ for restricted imports.

    Returns 0 if clean, 1 if violations found.
    """
    violations: list[str] = []

    for py_file in SRC_ROOT.rglob("*.py"):
        relative = str(py_file.relative_to(SRC_ROOT)).replace("\\", "/")
        imports = _get_imports(py_file)

        for restricted_module, allowed_files in RESTRICTED_IMPORTS.items():
            if restricted_module in imports and relative not in allowed_files:
                violations.append(
                    f"  VIOLATION: {relative} imports '{restricted_module}' "
                    f"(allowed only in: {allowed_files or 'NOWHERE'})"
                )

    if violations:
        print("Import restriction check FAILED:")
        for v in violations:
            print(v)
        return 1

    print("Import restriction check passed ✅")
    return 0


if __name__ == "__main__":
    sys.exit(check())
