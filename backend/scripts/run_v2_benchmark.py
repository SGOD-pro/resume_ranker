import os
import sys
import uuid
from pathlib import Path
import time
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import shutil
import json

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
            global current_pdf_path
            shutil.copy(current_pdf_path, Filename)
        mock_s3.download_file = fake_download
        return mock_s3
    else:
        mock_boto_patch.stop()
        client = boto3.client(service_name, *args, **kwargs)
        mock_boto_patch.start()
        return client

mock_boto.side_effect = side_effect

from src.extraction.extraction_pipeline import ExtractionPipeline
from src.infrastructure.storage.storage_service import StorageService
from src.config.aws import get_settings

def run_benchmark():
    settings = get_settings()
    pipeline = ExtractionPipeline()
    storage = StorageService()
    
    resumes_dir = Path(project_root) / "data" / "resumes"
    if not resumes_dir.exists():
        print(f"Directory {resumes_dir} not found.")
        return
        
    pdfs = list(resumes_dir.glob("*.pdf"))[:50]
    total_resumes = len(pdfs)
    
    print(f"Starting benchmark for {total_resumes} resumes...")
    
    # Metrics
    pymupdf_only_count = 0
    odl_fallback_count = 0
    nova_fallback_count = 0
    total_quality = 0.0
    email_found = 0
    phone_found = 0
    
    latencies = {
        "pymupdf_ms": [],
        "odl_ms": [],
        "total_ms": []
    }
    
    job_id = f"benchmark-{uuid.uuid4().hex[:8]}"
    
    for i, pdf_path in enumerate(pdfs, 1):
        try:
            global current_pdf_path
            current_pdf_path = str(pdf_path)
            
            doc_id = str(uuid.uuid4())
            with open(pdf_path, "rb") as f:
                content = f.read()
                
            # Upload to LocalStack S3 to mimic Phase 1 trigger
            s3_key = storage.upload_resume(job_id, doc_id, content, pdf_path.name)
            
            t_start = time.time()
            
            # Run pipeline
            result = pipeline.run_pipeline(str(pdf_path), doc_id, settings.s3_bucket_name, s3_key)
            
            t_end = time.time()
            
            # Calculate metrics
            fields = result.get("fields", {})
            stage_timings = fields.get("stage_timings", [])
            
            # Latency processing
            pymupdf_ms = 0
            odl_ms = 0
            nova_ms = 0
            
            used_odl = False
            used_nova = False
            
            for timing in stage_timings:
                if timing["stage"] == "structural_parse":
                    if timing["method_used"] == "pymupdf_fast":
                        pymupdf_ms = timing["duration_ms"]
                    elif timing["method_used"] == "odl_fallback":
                        odl_ms = timing["duration_ms"]
                        used_odl = True
                elif timing["stage"] == "nova_fallback":
                    nova_ms = timing["duration_ms"]
                    used_nova = True
                    
            total_ms = (t_end - t_start) * 1000
            
            if used_odl:
                odl_fallback_count += 1
                latencies["odl_ms"].append(odl_ms)
            else:
                pymupdf_only_count += 1
                latencies["pymupdf_ms"].append(pymupdf_ms)
                
            if used_nova:
                nova_fallback_count += 1
                
            latencies["total_ms"].append(total_ms)
            total_quality += result.get("extraction_quality", 0)
            
            if fields.get("email"):
                email_found += 1
            if fields.get("phone"):
                phone_found += 1
                
            if i % 10 == 0:
                print(f"Processed {i}/{total_resumes} resumes...")
                
        except Exception as e:
            print(f"Error processing {pdf_path.name}: {e}")
            
    def p50_p95(data):
        if not data:
            return 0.0, 0.0
        s = sorted(data)
        p50_idx = int(len(s) * 0.5)
        p95_idx = int(len(s) * 0.95)
        if p95_idx >= len(s):
            p95_idx = len(s) - 1
        if p50_idx >= len(s):
            p50_idx = len(s) - 1
        return s[p50_idx], s[p95_idx]
        
    py_p50, py_p95 = p50_p95(latencies["pymupdf_ms"])
    odl_p50, odl_p95 = p50_p95(latencies["odl_ms"])
    tot_p50, tot_p95 = p50_p95(latencies["total_ms"])
    
    avg_quality = (total_quality / total_resumes) if total_resumes > 0 else 0
    
    print("\n" + "="*50)
    print("=== Phase 3 Extraction Benchmark Report ===")
    print("="*50)
    print(f"Total Resumes Processed: {total_resumes}")
    if total_resumes > 0:
        print(f"Extraction Routing Breakdown: {pymupdf_only_count/total_resumes*100:.1f}% PyMuPDF-only vs {odl_fallback_count/total_resumes*100:.1f}% ODL-Fallback")
        print(f"Average Quality Score: {avg_quality:.2f}")
        print(f"LLM Fallback Rate (Nova): {nova_fallback_count/total_resumes*100:.1f}%")
        print(f"Field Presence: Email ({email_found/total_resumes*100:.1f}%), Phone ({phone_found/total_resumes*100:.1f}%)")
    
    print("\nLatency Metrics (ms) [p50 / p95]:")
    print(f"  PyMuPDF Parsing: {py_p50:.1f} / {py_p95:.1f}")
    print(f"  ODL Parsing:     {odl_p50:.1f} / {odl_p95:.1f}")
    print(f"  Total End-to-End: {tot_p50:.1f} / {tot_p95:.1f}")
    print("="*50)

if __name__ == "__main__":
    run_benchmark()
