"""
Output Formatter
Produces clean, consistent JSON from parsed data.
Handles nulls, deduplication, and schema normalization.
"""
import json
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class ExtractionResult:
    """Final output schema."""
    document_id: str
    domain: str
    domain_confidence: float
    extraction_strategy: str   # which PDF extractor won
    page_count: int
    fields: Dict[str, Any]    # domain-specific extracted fields
    raw_entities: List[Dict]  # all NER entities
    warnings: List[str]
    metadata: Dict[str, Any]


class OutputFormatter:

    def format(
        self,
        pdf_path: str,
        domain_result,
        pdf_metadata: Dict,
        entities: list,
        parsed_fields: Dict[str, Any],
    ) -> ExtractionResult:

        doc_id = self._make_doc_id(pdf_path)
        warnings = self._generate_warnings(parsed_fields, entities)

        return ExtractionResult(
            document_id=doc_id,
            domain=domain_result.domain,
            domain_confidence=domain_result.confidence,
            extraction_strategy=pdf_metadata.get("strategy", "unknown"),
            page_count=pdf_metadata.get("page_count", 0),
            fields=self._clean_fields(parsed_fields),
            raw_entities=[
                {
                    "text": e.text,
                    "label": e.label,
                    "source": e.source,
                }
                for e in entities
            ],
            warnings=warnings,
            metadata={
                "pdf_path": pdf_path,
                "domain_signals": domain_result.signals[:5],
            }
        )

    def to_json(self, result: ExtractionResult, indent: int = 2) -> str:
        return json.dumps(asdict(result), indent=indent, ensure_ascii=False, default=str)

    def to_dict(self, result: ExtractionResult) -> Dict:
        return asdict(result)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _make_doc_id(self, path: str) -> str:
        import os
        name = os.path.basename(path)
        name = re.sub(r'\W+', '_', name)
        return name.lower().rstrip('_')

    def _clean_fields(self, fields: Dict) -> Dict:
        """Remove None values, empty lists, and clean strings."""
        if not isinstance(fields, dict):
            return fields

        cleaned = {}
        for k, v in fields.items():
            if v is None:
                continue
            if isinstance(v, dict):
                v = self._clean_fields(v)
                if v:
                    cleaned[k] = v
            elif isinstance(v, list):
                v = [self._clean_item(i) for i in v if i is not None]
                v = [i for i in v if i]
                if v:
                    cleaned[k] = v
            elif isinstance(v, str):
                v = v.strip()
                if v:
                    cleaned[k] = v
            else:
                cleaned[k] = v
        return cleaned

    def _clean_item(self, item):
        if isinstance(item, dict):
            return self._clean_fields(item)
        if isinstance(item, str):
            return item.strip() or None
        return item

    def _generate_warnings(self, fields: Dict, entities: list) -> List[str]:
        warnings = []

        # Check for critical missing fields per domain
        persons = [e for e in entities if e.label == "PERSON"]
        emails = [e for e in entities if e.label == "EMAIL"]

        if not persons:
            warnings.append("No person names detected — may be non-person document or OCR issue")
        if not entities:
            warnings.append("No entities extracted — PDF may be image-based (needs OCR)")

        # Check for garbage text (spaced chars artifact)
        if fields.get("personal_info", {}).get("name"):
            name = fields["personal_info"]["name"]
            if re.search(r'(?:[A-Z] ){3,}', name):
                warnings.append(f"Possible OCR artifact in name: '{name}'")

        return warnings
