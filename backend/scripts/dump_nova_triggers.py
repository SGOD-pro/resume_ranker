import os
import sys
import json
import uuid
import time
from pathlib import Path

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.extraction.structural_parsing_service import StructuralParsingService, BatchDoc
from src.extraction.markdown_extraction_service import MarkdownExtractionService
from src.extractors.contact.contact_parser import _is_name_line

from unittest.mock import patch, MagicMock
import boto3

mock_boto_patch = patch("boto3.client")
mock_boto = mock_boto_patch.start()

def side_effect(service_name, *args, **kwargs):
    if service_name == "bedrock-runtime":
        mock_bedrock = MagicMock()
        mock_response_body = {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "extract_resume_fields",
                                "input": {
                                    "phone": "555-123-4567",
                                    "email": "new_email@example.com"
                                }
                            }
                        }
                    ]
                }
            }
        }
        mock_stream = MagicMock()
        mock_stream.read.return_value = json.dumps(mock_response_body).encode('utf-8')
        mock_bedrock.invoke_model.return_value = {"body": mock_stream}
        return mock_bedrock
    elif service_name == "s3":
        mock_s3 = MagicMock()
        def fake_download(Bucket, Key, Filename):
            pass # won't need download for dumper since structural service batch mock bypasses it? Wait, run_v2_benchmark mocks it.
        mock_s3.download_file = fake_download
        return mock_s3
    elif service_name == "lambda":
        mock_lambda = MagicMock()
        def fake_invoke(**kwargs):
            return {
                "StatusCode": 200,
                "Payload": MagicMock(read=lambda: json.dumps({"elements": [], "text": "mocked odl text"}).encode('utf-8'))
            }
        mock_lambda.invoke = fake_invoke
        return mock_lambda
    else:
        mock_boto_patch.stop()
        client = boto3.client(service_name, *args, **kwargs)
        mock_boto_patch.start()
        return client

mock_boto.side_effect = side_effect

def run_dumper():
    resumes_dir = Path(project_root) / "data" / "resumes"
    if not resumes_dir.exists():
        print(f"Directory {resumes_dir} not found.")
        return
        
    import random
    all_pdfs = sorted(resumes_dir.glob("*.pdf"))
    valid_pdfs = list(all_pdfs)
    random.seed(42)
    random.shuffle(valid_pdfs)
    pdfs = valid_pdfs[:200]
    
    structural_service = StructuralParsingService()
    markdown_service = MarkdownExtractionService()
    
    docs = []
    for pdf_path in pdfs:
        doc_id = str(uuid.uuid4())
        docs.append(BatchDoc(
            document_id=doc_id,
            pdf_path=str(pdf_path),
            s3_bucket="dummy",
            s3_key=pdf_path.name
        ))
        
    print("Running structural parse batch...")
    parse_results = structural_service.parse_pdf_batch(docs)
    
    nova_triggers = []
    
    for doc, parse_result in zip(docs, parse_results):
        md_result = markdown_service.extract(
            parse_result.markdown, 
            parse_result.hyperlinks, 
            parse_result.elements
        )
        
        chunks = md_result.get("unresolved_chunks", [])
        if not chunks:
            continue
            
        fields = md_result.get("fields", {})
        
        missing_fields = []
        if not fields.get("name"): missing_fields.append("name")
        if not fields.get("email"): missing_fields.append("email")
        if not fields.get("phone"): missing_fields.append("phone")
        
        has_exp = fields.get("experience") and len(fields.get("experience")) > 0
        has_skills = fields.get("skills") and len(fields.get("skills")) > 0
        if not has_exp: missing_fields.append("experience")
        if not has_skills: missing_fields.append("skills")
        
        method_used = "pymupdf"
        for t in parse_result.stage_timings:
            if t.stage == "structural_parse":
                method_used = "odl" if t.method_used == "odl_fallback" else "pymupdf"
                
        # Check if structural signal produced a name candidate
        structural_signal_used = False
        elements = parse_result.elements
        if elements:
            for el in elements:
                if not isinstance(el, dict): continue
                if el.get('type') == 'heading' or str(el.get('pdfua_tag')).startswith('H'):
                    c = str(el.get('content', '')).strip()
                    if c:
                        import re
                        c = re.split(r'[,|]| - ', c)[0].strip()
                        if _is_name_line(c):
                            structural_signal_used = True
                            break
                            
        # Get ODL specific data
        odl_data = []
        if method_used == "odl" and elements:
            # First 15 elements from page 1
            for el in elements:
                if isinstance(el, dict) and el.get('page number', 1) == 1:
                    if len(odl_data) < 15:
                        odl_data.append(el)
        
        raw_text = parse_result.markdown[:1000] if parse_result.markdown else ""
        
        nova_triggers.append({
            "doc_id": doc.document_id,
            "filename": Path(doc.pdf_path).name,
            "source_path": method_used,
            "structural_signal_used": structural_signal_used,
            "missing_fields": missing_fields,
            "raw_text_first_1000_chars": raw_text,
            "odl_data": odl_data
        })
        
    output_path = Path(project_root) / "diagnostic_output.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(nova_triggers, f, indent=2, ensure_ascii=False)
        
    print(f"Dumped {len(nova_triggers)} triggers to {output_path}")

if __name__ == "__main__":
    run_dumper()
