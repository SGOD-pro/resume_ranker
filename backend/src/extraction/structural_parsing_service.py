"""
extraction/structural_parsing_service.py — ACL for opendataloader-pdf
=======================================================================
THE ONLY FILE in this codebase that imports opendataloader_pdf.

Responsibilities:
  1. Write PDF bytes to a temp file
  2. Call ODL convert() — which spawns/reuses the warm JVM process
  3. Read the output JSON from disk
  4. Cache result JSON in S3 by content_hash (never re-run ODL on same bytes)
  5. Map raw ODL JSON → StructuralParse via domain.py helpers
  6. Clean up temp files

What this class does NOT do:
  - Field-level text extraction (that's DeterministicExtractionService)
  - Scoring (that's ScoringService)
  - ATS scoring (that's AtsScoringService)
  - Any LLM calls (never)

Per boundaries.md §2: if opendataloader-pdf changes its API or JSON schema,
exactly this file changes — nothing else.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from src.extraction.domain import (
    StructuralParse,
    StructuralParseError,
    structural_parse_from_odl_json,
)

logger = logging.getLogger(__name__)

# opendataloader-pdf version — update when the dependency is bumped.
# Used to invalidate S3 cached parse results on parser upgrades.
_ODL_VERSION = "2.0"


# ---------------------------------------------------------------------------
# Protocol: DocumentCache (injected, never a concrete import here)
# ---------------------------------------------------------------------------

@runtime_checkable
class DocumentCache(Protocol):
    """
    Minimal cache interface for ODL parse results.
    Implementations: S3DocumentCache (production), InMemoryDocumentCache (tests).
    """

    def get(self, content_hash: str) -> dict[str, Any] | None:
        """Return the cached ODL JSON dict or None if not cached."""
        ...

    def put(self, content_hash: str, odl_json: dict[str, Any], markdown: str) -> str:
        """
        Persist the ODL JSON dict and return the storage key.
        markdown is stored alongside for convenience.
        """
        ...

    def get_markdown(self, content_hash: str) -> str:
        """Return the cached markdown string or empty string."""
        ...


# ---------------------------------------------------------------------------
# StructuralParsingService
# ---------------------------------------------------------------------------

class StructuralParsingService:
    """
    Single responsibility: PDF bytes → StructuralParse.

    This is the Anti-Corruption Layer (ACL) for opendataloader-pdf.
    Inject a DocumentCache to enable S3-backed caching.
    Inject cache=None to disable caching (useful in tests).

    Usage:
        svc = StructuralParsingService(cache=s3_cache)
        parse = await svc.parse(pdf_bytes, content_hash)
    """

    def __init__(self, cache: DocumentCache | None = None) -> None:
        self._cache = cache

    def parse(self, pdf_bytes: bytes, content_hash: str = "") -> StructuralParse:
        """
        PDF bytes → StructuralParse.

        Steps:
          1. Compute SHA-256 hash if not provided.
          2. Check cache — return immediately if hit.
          3. Write bytes to a temp PDF file.
          4. Call opendataloader_pdf.convert() for JSON + markdown.
          5. Read output files from temp dir.
          6. Store in cache.
          7. Clean up temp files.
          8. Map raw JSON → StructuralParse.

        Raises:
            StructuralParseError: JVM not found, malformed PDF, ODL timeout,
                                  or any other conversion failure.
        """
        if not content_hash:
            content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # 1. Cache hit — skip ODL entirely
        if self._cache is not None:
            cached = self._cache.get(content_hash)
            if cached is not None:
                markdown = self._cache.get_markdown(content_hash)
                logger.info(
                    "ODL cache hit for hash=%s, skipping conversion", content_hash[:12]
                )
                return structural_parse_from_odl_json(
                    cached, content_hash, _ODL_VERSION, markdown
                )

        # 2. Run ODL
        odl_json, markdown = self._run_odl(pdf_bytes, content_hash)

        # 3. Store result in cache (fire-and-forget; cache failures don't fail the parse)
        if self._cache is not None:
            try:
                self._cache.put(content_hash, odl_json, markdown)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to cache ODL result for %s: %s", content_hash[:12], exc)

        # 4. Build domain object
        return structural_parse_from_odl_json(odl_json, content_hash, _ODL_VERSION, markdown)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_odl(self, pdf_bytes: bytes, content_hash: str) -> tuple[dict[str, Any], str]:
        """
        Write PDF to disk, run ODL, read outputs, clean up.
        Returns (odl_json_dict, markdown_string).

        NOTE: This is where 'import opendataloader_pdf' lives.
        If Java is not installed, ODL raises FileNotFoundError — we
        convert it to StructuralParseError(retriable=False) since
        the JVM is a hard infrastructure dependency.
        """
        # Late import — keeps the import strictly inside this class
        # so the CI import-restriction check (rules.md §8) passes.
        try:
            from opendataloader_pdf import convert as odl_convert  # type: ignore  # noqa: PLC0415
        except ImportError as exc:
            raise StructuralParseError(
                document_id=content_hash[:12],
                reason=f"opendataloader_pdf not installed: {exc}",
                retriable=False,
            ) from exc

        with tempfile.TemporaryDirectory(prefix="odl_") as tmp_dir:
            pdf_path = Path(tmp_dir) / f"{content_hash}.pdf"
            out_dir = Path(tmp_dir) / "out"
            out_dir.mkdir()

            pdf_path.write_bytes(pdf_bytes)

            try:
                odl_convert(
                    input_path=str(pdf_path),
                    output_dir=str(out_dir),
                    format=["json", "markdown"],
                    quiet=True,
                )
            except FileNotFoundError as exc:
                raise StructuralParseError(
                    document_id=content_hash[:12],
                    reason="Java not found — JVM is required for opendataloader-pdf",
                    retriable=False,
                ) from exc
            except Exception as exc:  # noqa: BLE001
                raise StructuralParseError(
                    document_id=content_hash[:12],
                    reason=f"ODL conversion failed: {exc}",
                    retriable=True,
                ) from exc

            odl_json = self._read_json(out_dir, content_hash)
            markdown = self._read_markdown(out_dir, content_hash)

        return odl_json, markdown

    @staticmethod
    def _read_json(out_dir: Path, stem: str) -> dict[str, Any]:
        """
        ODL writes {input_stem}.json to output_dir.
        """
        json_path = out_dir / f"{stem}.json"
        if not json_path.exists():
            # ODL may use a different stem — find any .json file
            candidates = list(out_dir.glob("*.json"))
            if not candidates:
                raise StructuralParseError(
                    document_id=stem[:12],
                    reason=f"ODL produced no JSON output in {out_dir}",
                    retriable=False,
                )
            json_path = candidates[0]

        try:
            data: dict[str, Any] = json.loads(json_path.read_text(encoding="utf-8"))
            return data
        except json.JSONDecodeError as exc:
            raise StructuralParseError(
                document_id=stem[:12],
                reason=f"ODL JSON output is malformed: {exc}",
                retriable=False,
            ) from exc

    @staticmethod
    def _read_markdown(out_dir: Path, stem: str) -> str:
        """Return the markdown output or empty string if not present."""
        md_path = out_dir / f"{stem}.md"
        if not md_path.exists():
            candidates = list(out_dir.glob("*.md"))
            if not candidates:
                return ""
            md_path = candidates[0]
        return md_path.read_text(encoding="utf-8")
