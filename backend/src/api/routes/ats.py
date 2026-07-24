from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import hashlib
from src.extraction.structural_parsing_service import StructuralParsingService
from src.extraction.deterministic_extraction_service import DeterministicExtractionService
from src.ats.ats_scoring_service import AtsScoringService

router = APIRouter(prefix="/api/v2", tags=["ats"])

# Lazily initialized services (in a real app, these would be injected)
structural_service = None
extraction_service = None
ats_service = None

def get_services():
    global structural_service, extraction_service, ats_service
    if not structural_service:
        # Note: in a real app, we need to pass dependencies like ODL client, cache, etc.
        # This is a stub initialization for the standalone ATS endpoint.
        # We assume the services can be instantiated with defaults for now.
        structural_service = StructuralParsingService()
        extraction_service = DeterministicExtractionService()
        ats_service = AtsScoringService()
    return structural_service, extraction_service, ats_service


@router.post("/ats-check")
async def ats_check(file: UploadFile = File(...)):
    """
    Standalone ATS check endpoint. Does not persist to DB.
    Requires a PDF upload.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")
        
    try:
        pdf_bytes = await file.read()
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()
        
        struct_svc, extract_svc, ats_svc = get_services()
        
        # 1. Ingestion / Structural Parsing
        structural = struct_svc.parse(pdf_bytes, file.filename)
        
        # 2. Deterministic Extraction (computes LayoutMetadata)
        extraction = extract_svc.parse(structural, file.filename)
        
        # 3. ATS Evaluation
        ats_result = ats_svc.score(extraction)
        
        # In a real API we would serialize `ats_result` to a dict or pydantic model response
        # For this prototype we can return the dataclass wrapped in a dict
        
        # Convert dataclasses to dict using a quick comprehension/helper
        # Since AtsResult is a dataclass, we can return it directly if FastAPI handles it,
        # but to be safe, we'll return a dict representation
        import dataclasses
        return dataclasses.asdict(ats_result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
