import logging
from typing import Dict, Any, List

from src.extraction.structural_parsing_service import StructuralParsingService, StageTiming, BatchDoc
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extraction.fallback.nova_service import NovaService
from src.config.aws import get_settings

logger = logging.getLogger(__name__)

class ExtractionPipeline:
    """
    V2 Extraction Pipeline — used by the /api/v2/jobs routes.

    NOTE on naming:
      This class is intentionally called "ExtractionPipeline" (no version suffix)
      to distinguish it from the older PDFPipelineV3 in src/core/pipeline.py.
      PDFPipelineV3 is the THIRD internal iteration of the V1 extraction core and
      is still used by ExtractionService (src/services/extraction_service.py).
      This pipeline is the NEW path introduced alongside the v2 API — it replaces
      that older path for all /api/v2/jobs traffic.

    Orchestration:
      1. StructuralParsingService  — PyMuPDF quality gate + ODL fallback
      2. MarkdownExtractionService — regex parsers (ported from V1 extractors)
      3. NovaService               — LLM fallback for unresolved chunks

    Output format (flat dict, top-level keys):
      name, email, phone, location, skills, experience, education, projects
      _document_id, extraction_quality, elements, stage_timings
    """
    def __init__(self):
        self.structural_service = StructuralParsingService()
        self.markdown_service = MarkdownExtractionService()
        self.nova_service = NovaService()

    def run_pipeline(self, pdf_path: str, doc_id: str, s3_bucket: str, s3_key: str) -> Dict[str, Any]:
        """
        Extract structured data from a single PDF resume.

        Steps:
          1. Structural Parse  — PyMuPDF quality gate; falls back to ODL if score < 0.90
          2. Regex Extraction  — MarkdownExtractionService parses name/email/skills/etc.
          3. LLM Fallback      — NovaService resolves unresolved chunks (name missing, etc.)

        Returns a flat dict. The scorer reads directly from top-level keys (name, email…),
        NOT from a nested personal_info dict (that was the old PDFPipelineV3 format).
        """
        # Step 1 & 2: Structural Parse (PyMuPDF or ODL)
        parse_result = self.structural_service.parse_pdf(pdf_path, doc_id, s3_bucket, s3_key)
        
        # Log StageTimings (Normally this would go to DynamoDB, but we return it to caller)
        timings = parse_result.stage_timings

        # Step 3: Regex Parse on Clean Markdown
        import time
        t0 = time.time()
        md_result = self.markdown_service.extract(
            parse_result.markdown, parse_result.hyperlinks, parse_result.elements,
            pymupdf_markdown=parse_result.pymupdf_text
        )
        t1 = time.time()
        timings.append(StageTiming(
            document_id=doc_id,
            stage="regex_parse",
            method_used="markdown_regex",
            duration_ms=(t1 - t0) * 1000,
            triggered_fallback=False
        ))

        fields = md_result["fields"]
        unresolved_chunks = md_result["unresolved_chunks"]

        # Step 4: Nova Fallback
        if unresolved_chunks:
            t2 = time.time()
            fields = self.nova_service.resolve_chunks(unresolved_chunks, fields)
            t3 = time.time()
            timings.append(StageTiming(
                document_id=doc_id,
                stage="nova_fallback",
                method_used="nova_micro",
                duration_ms=(t3 - t2) * 1000,
                triggered_fallback=True
            ))

        # Add metadata for scoring
        fields["_document_id"] = doc_id
        fields["extraction_quality"] = parse_result.quality_score
        fields["elements"] = parse_result.elements
        fields["stage_timings"] = [t.__dict__ for t in timings]
        
        return {
            "fields": fields,
            "document_id": doc_id,
            "extraction_quality": parse_result.quality_score,
            "page_count": 0, # Could be added to ParseResult if needed
            "domain": "resume",
            "stage_timings": [t.__dict__ for t in timings],
            "error_reason": parse_result.error_reason
        }

    def run_pipeline_batch(
        self,
        docs: List[BatchDoc],
    ) -> List[Dict[str, Any]]:
        """
        Batch version of run_pipeline.

        Structural parsing (PyMuPDF quality gate + ONE batched ODL call) is done
        for the whole group first, then each document individually proceeds through
        the regex → Nova → scoring pipeline.  Nova stays per-document (ADR-10).
        """
        import time

        # Step 1+2: Batch structural parse (ONE JVM boot for all ODL-destined docs)
        parse_results = self.structural_service.parse_pdf_batch(docs)

        output: List[Dict[str, Any]] = []
        for doc, parse_result in zip(docs, parse_results):
            doc_id = doc.document_id
            timings = list(parse_result.stage_timings)

            # Step 3: Regex extract
            t0 = time.time()
            md_result = self.markdown_service.extract(
                parse_result.markdown, parse_result.hyperlinks, parse_result.elements,
                pymupdf_markdown=parse_result.pymupdf_text
            )
            t1 = time.time()
            timings.append(StageTiming(
                document_id=doc_id,
                stage="regex_parse",
                method_used="markdown_regex",
                duration_ms=(t1 - t0) * 1000,
                triggered_fallback=False,
            ))

            fields = md_result["fields"]
            unresolved_chunks = md_result["unresolved_chunks"]

            # Step 4: Nova fallback (per-document, unchanged)
            if unresolved_chunks:
                t2 = time.time()
                fields = self.nova_service.resolve_chunks(unresolved_chunks, fields)
                t3 = time.time()
                timings.append(StageTiming(
                    document_id=doc_id,
                    stage="nova_fallback",
                    method_used="nova_micro",
                    duration_ms=(t3 - t2) * 1000,
                    triggered_fallback=True,
                ))

            fields["_document_id"] = doc_id
            fields["extraction_quality"] = parse_result.quality_score
            fields["elements"] = parse_result.elements
            fields["stage_timings"] = [t.__dict__ for t in timings]

            output.append({
                "fields": fields,
                "document_id": doc_id,
                "filename": __import__('os').path.basename(doc.pdf_path),
                "extraction_quality": parse_result.quality_score,
                "page_count": 0,
                "domain": "resume",
                "stage_timings": [t.__dict__ for t in timings],
                "error_reason": parse_result.error_reason,
            })

        return output
