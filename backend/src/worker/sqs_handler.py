"""
worker/sqs_handler.py — SQS Lambda Handler
==========================================
Replaces Celery per Architecture Rev 3.

This function acts as the AWS Lambda entry point for SQS events.
SQS native event-source mapping controls batch size and batching windows.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    AWS Lambda SQS Event Handler.
    
    Args:
        event: SQS event containing a batch of messages.
        context: Lambda context object.
    """
    from collections import defaultdict

    from src.extraction.domain_extraction import UnresolvedChunk
    from src.extraction.fallback.nova_service import NovaFallbackService
    from src.infrastructure.models.fallback_record import FallbackRecordItem
    from src.infrastructure.repositories.documents_repository import DocumentsRepository
    from src.infrastructure.repositories.fallback_record_repository import FallbackRecordRepository
    from src.infrastructure.storage.storage_service import StorageService

    records = event.get("Records", [])
    logger.info(f"Received {len(records)} messages from SQS")
    
    # Group chunks by document_id
    chunks_by_doc: dict[str, list[UnresolvedChunk]] = defaultdict(list)
    raw_payloads = []
    
    for record in records:
        try:
            body = json.loads(record.get("body", "{}"))
            if body.get("type") == "UNRESOLVED_CHUNK":
                chunk = UnresolvedChunk(**body["chunk"])
                chunks_by_doc[chunk.document_id].append(chunk)
            raw_payloads.append(body)
        except Exception as e:
            logger.error(f"Failed to parse SQS record body: {e}")

    if not chunks_by_doc:
        logger.info("No UnresolvedChunks in batch.")
        return {"statusCode": 200, "body": json.dumps("No chunks processed")}

    nova_service = NovaFallbackService()
    fallback_repo = FallbackRecordRepository()
    doc_repo = DocumentsRepository()
    storage = StorageService()

    for document_id, chunks in chunks_by_doc.items():
        logger.info(f"Processing fallback for doc {document_id} with {len(chunks)} chunks.")
        
        # We need the job_id. In a real scenario, it should be in the SQS payload or we look it up.
        # Assuming the payload included job_id (we'll fetch it from the first chunk's original payload).
        # Since UnresolvedChunk lacks job_id, we extract it from the raw payload if we sent it.
        # Alternatively, we could add job_id to UnresolvedChunk, but for now we look it up via the doc.
        # However, DynamoDB requires PK=JOB#... so we need job_id.
        
        # Wait, if we can't find job_id, we can't fetch the document easily without a GSI.
        # Let's assume the payload wrapper contains job_id.
        job_id = None
        for p in raw_payloads:
            if p.get("type") == "UNRESOLVED_CHUNK" and p.get("chunk", {}).get("document_id") == document_id:
                job_id = p.get("job_id")
                break
                
        if not job_id:
            logger.error(f"Cannot process doc {document_id}: job_id missing from payload.")
            continue

        try:
            # 1. Fetch current extraction JSON from S3
            base_json = storage.get_extracted_json(job_id, document_id)
            
            # Since ExtractionResult is a dataclass, we'll need to deserialize it carefully,
            # or just merge dicts. For now, let's assume we can merge Nova output directly into the dict
            # or use the domain objects. Let's merge dicts for simplicity if we can't easily reconstruct 
            # ExtractionResult (which contains ExtractedField objects).
            
            # 2. Invoke Nova
            nova_data, model_used, confidence = nova_service.process_chunks(document_id, chunks)
            
            if not nova_data:
                logger.info(f"Nova returned empty for doc {document_id}")
                continue

            # 3. Save FallbackRecords to DB
            fields_used = 0
            for field_name, value in nova_data.items():
                if value:  # if Nova returned something useful
                    # Determine which chunk this came from? Nova summarizes across all chunks.
                    # We'll just store the combined text as original context.
                    combined_text = "\\n\\n---\\n\\n".join(c.text for c in chunks)
                    record = FallbackRecordItem(
                        document_id=document_id,
                        field_name=field_name,
                        nova_model_used=model_used,
                        confidence=confidence,
                        resolved_value=value,
                        original_text=combined_text[:1000] # cap size
                    )
                    fallback_repo.create(record)
                    fields_used += 1

            # 4. Merge results into S3 JSON
            # Simple merge: only update fields if they are missing or empty in the base JSON.
            # (Adhering to the rule: Nova NEVER overwrites deterministic fields)
            for k, v in nova_data.items():
                if v:
                    # In our S3 JSON, fields are raw values (see to_fields_dict)
                    existing_val = base_json.get(k)
                    if not existing_val:  # Empty list, None, empty string
                        base_json[k] = v
                        logger.debug(f"Nova fallback populated field: {k}")

            # Upload updated JSON to S3
            storage.upload_extracted_json(job_id, document_id, base_json)

            # 5. Update DocumentItem metrics
            doc = doc_repo.get(job_id, document_id)
            if doc:
                doc_repo.update_nova_fields_used(
                    job_id=job_id,
                    document_id=document_id,
                    nova_fields_used=doc.nova_fields_used + fields_used,
                    expected_version=doc.version
                )

        except Exception as e:
            logger.error(f"Failed fallback pipeline for doc {document_id}: {e}")

    return {"statusCode": 200, "body": json.dumps("Fallback batch processed successfully")}
