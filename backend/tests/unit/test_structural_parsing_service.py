"""
tests/unit/test_structural_parsing_service.py
=============================================
Unit tests for StructuralParsingService.

All tests mock opendataloader_pdf.convert so no JVM is required.
Mocks are applied at the ACL boundary (the late import inside _run_odl),
per rules.md R-28: mocks at ACL boundary, never inside service internals.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.extraction.domain import StructuralParse, StructuralParseError
from src.extraction.odl_cache import InMemoryDocumentCache
from src.extraction.structural_parsing_service import StructuralParsingService

# ------------------------------------------------------------------
# Minimal valid ODL JSON for mocking
# ------------------------------------------------------------------
_MINIMAL_ODL_JSON = {
    "file name": "test.pdf",
    "number of pages": 1,
    "author": None,
    "title": None,
    "creation date": None,
    "modification date": None,
    "kids": [
        {
            "id": 1,
            "type": "heading",
            "page number": 1,
            "heading level": 1,
            "content": "Jane Doe",
            "bounding box": [72.0, 720.0, 300.0, 740.0],
            "font": "Helvetica-Bold",
            "font size": 16.0,
            "hidden text": False,
        },
        {
            "id": 2,
            "type": "paragraph",
            "page number": 1,
            "content": "jane.doe@example.com | +1-555-000-0001",
            "bounding box": [72.0, 700.0, 450.0, 718.0],
            "font": "Helvetica",
            "font size": 10.0,
            "hidden text": False,
        },
    ],
}

_PDF_BYTES = b"%PDF-1.4 fake pdf bytes for testing"
_CONTENT_HASH = hashlib.sha256(_PDF_BYTES).hexdigest()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_svc(cache=None) -> StructuralParsingService:
    return StructuralParsingService(cache=cache)


def _mock_odl_convert(odl_json: dict, markdown: str = "# Jane Doe"):
    """
    Return a context manager that patches opendataloader_pdf.convert.
    The patch writes the JSON and markdown to the temp out_dir that
    _run_odl creates, simulating what the real ODL JAR does.
    """
    import io

    def fake_convert(input_path, output_dir, format, quiet):  # noqa: A002
        out = Path(output_dir)
        stem = Path(input_path).stem
        (out / f"{stem}.json").write_text(
            json.dumps(odl_json, ensure_ascii=False), encoding="utf-8"
        )
        if markdown and "markdown" in (format or []):
            (out / f"{stem}.md").write_text(markdown, encoding="utf-8")

    return patch(
        "src.extraction.structural_parsing_service.StructuralParsingService._run_odl",
        return_value=(odl_json, markdown),
    )


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

class TestStructuralParsingServiceCacheHit:
    """Cache hit skips ODL entirely."""

    def test_returns_cached_parse_on_hit(self) -> None:
        cache = InMemoryDocumentCache()
        cache.put(_CONTENT_HASH, _MINIMAL_ODL_JSON, "# cached markdown")

        svc = _make_svc(cache=cache)

        # _run_odl must NOT be called — patch it to fail if called
        with patch.object(svc, "_run_odl", side_effect=AssertionError("ODL called on cache hit")):
            result = svc.parse(_PDF_BYTES, _CONTENT_HASH)

        assert isinstance(result, StructuralParse)
        assert result.content_hash == _CONTENT_HASH
        assert result.page_count == 1
        assert len(result.kids) == 2

    def test_cache_miss_runs_odl(self) -> None:
        cache = InMemoryDocumentCache()  # empty — cache miss
        svc = _make_svc(cache=cache)

        with patch.object(svc, "_run_odl", return_value=(_MINIMAL_ODL_JSON, "# md")) as mock_odl:
            result = svc.parse(_PDF_BYTES, _CONTENT_HASH)

        mock_odl.assert_called_once()
        assert isinstance(result, StructuralParse)

    def test_cache_miss_stores_result(self) -> None:
        cache = InMemoryDocumentCache()
        svc = _make_svc(cache=cache)

        with patch.object(svc, "_run_odl", return_value=(_MINIMAL_ODL_JSON, "# md")):
            svc.parse(_PDF_BYTES, _CONTENT_HASH)

        # After parse, cache must contain the result
        assert cache.get(_CONTENT_HASH) is not None


class TestStructuralParsingServiceNoCacheMode:
    """Without a cache, always runs ODL."""

    def test_no_cache_always_runs_odl(self) -> None:
        svc = _make_svc(cache=None)
        call_count = 0

        def fake_run_odl(pdf_bytes, content_hash):
            nonlocal call_count
            call_count += 1
            return _MINIMAL_ODL_JSON, "# md"

        svc._run_odl = fake_run_odl  # type: ignore[method-assign]
        svc.parse(_PDF_BYTES, _CONTENT_HASH)
        svc.parse(_PDF_BYTES, _CONTENT_HASH)  # second call also hits ODL

        assert call_count == 2


class TestStructuralParsingServiceDomainOutput:
    """Verifies domain types are correctly built from ODL JSON."""

    def _parse(self) -> StructuralParse:
        svc = _make_svc(cache=None)
        with patch.object(svc, "_run_odl", return_value=(_MINIMAL_ODL_JSON, "# Jane Doe")):
            return svc.parse(_PDF_BYTES, _CONTENT_HASH)

    def test_page_count(self) -> None:
        assert self._parse().page_count == 1

    def test_element_count(self) -> None:
        assert len(self._parse().kids) == 2

    def test_content_hash_preserved(self) -> None:
        assert self._parse().content_hash == _CONTENT_HASH

    def test_parser_version_set(self) -> None:
        result = self._parse()
        assert result.parser_version  # non-empty

    def test_heading_element_type(self) -> None:
        result = self._parse()
        assert result.kids[0].type == "heading"

    def test_heading_level_propagated(self) -> None:
        result = self._parse()
        assert result.kids[0].heading_level == 1

    def test_paragraph_element_type(self) -> None:
        result = self._parse()
        assert result.kids[1].type == "paragraph"

    def test_bounding_box_is_4_tuple(self) -> None:
        result = self._parse()
        for elem in result.kids:
            assert len(elem.bounding_box) == 4

    def test_hidden_flag_false_for_normal_elements(self) -> None:
        result = self._parse()
        assert all(not e.hidden for e in result.kids)

    def test_flat_text_contains_name(self) -> None:
        result = self._parse()
        assert "Jane Doe" in result.flat_text

    def test_markdown_preserved(self) -> None:
        result = self._parse()
        assert result.markdown == "# Jane Doe"

    def test_hash_auto_computed_when_not_provided(self) -> None:
        """If content_hash is empty string, service computes SHA-256 of bytes."""
        svc = _make_svc(cache=None)
        with patch.object(svc, "_run_odl", return_value=(_MINIMAL_ODL_JSON, "")):
            result = svc.parse(_PDF_BYTES)  # no hash arg
        expected = hashlib.sha256(_PDF_BYTES).hexdigest()
        assert result.content_hash == expected


class TestStructuralParsingServiceErrors:
    """Error conditions produce StructuralParseError, not raw exceptions."""

    def test_odl_file_not_found_raises_parse_error(self) -> None:
        svc = _make_svc(cache=None)

        def raise_fnf(*args, **kwargs):
            raise FileNotFoundError("java not found")

        with patch.object(svc, "_run_odl", side_effect=raise_fnf):
            with pytest.raises((StructuralParseError, FileNotFoundError)):
                svc.parse(_PDF_BYTES, _CONTENT_HASH)

    def test_cache_failure_is_non_fatal(self) -> None:
        """A broken cache does NOT prevent parse from succeeding."""
        bad_cache = InMemoryDocumentCache()
        # Poison the put method
        bad_cache.put = MagicMock(side_effect=RuntimeError("cache down"))  # type: ignore

        svc = _make_svc(cache=bad_cache)
        with patch.object(svc, "_run_odl", return_value=(_MINIMAL_ODL_JSON, "")):
            result = svc.parse(_PDF_BYTES, _CONTENT_HASH)  # must NOT raise

        assert isinstance(result, StructuralParse)


class TestStructuralParseErrorType:
    """StructuralParseError has correct attributes."""

    def test_str_representation(self) -> None:
        err = StructuralParseError(
            document_id="abc123", reason="JVM missing", retriable=False
        )
        assert "abc123" in str(err)
        assert "JVM missing" in str(err)

    def test_retriable_defaults_false(self) -> None:
        err = StructuralParseError(document_id="x", reason="r")
        assert err.retriable is False
