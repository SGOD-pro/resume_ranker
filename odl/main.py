import os
import json
import uuid
import shutil
import logging
from pathlib import Path

import boto3
import opendataloader_pdf

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client('s3')

def lambda_handler(event, context):
    documents = event.get('documents', [])
    save_images = event.get('save_images', False)
    
    if not documents:
        raise ValueError("Missing 'documents' array in event payload")
        
    logger.info(f"Processing batch of {len(documents)} documents")
    
    # Use a unique directory in /tmp to prevent cross-invocation pollution
    run_id = str(uuid.uuid4())
    tmp_dir = Path(f"/tmp/{run_id}")
    inputs_dir = tmp_dir / "inputs"
    out_dir = tmp_dir / "out"
    
    inputs_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    input_paths = []
    doc_map = {} # document_id -> doc info
    
    try:
        # 1. Download all PDFs
        for doc in documents:
            doc_id = doc.get('document_id')
            bucket = doc.get('s3_bucket')
            key = doc.get('s3_key')
            
            if not doc_id or not bucket or not key:
                logger.warning(f"Skipping invalid document entry: {doc}")
                continue
                
            input_pdf = inputs_dir / f"{doc_id}.pdf"
            logger.info(f"Downloading s3://{bucket}/{key} to {input_pdf}")
            s3_client.download_file(bucket, key, str(input_pdf))
            
            input_paths.append(str(input_pdf))
            doc_map[doc_id] = doc
            
        if not input_paths:
            raise ValueError("No valid documents to process after download")
            
        # 2. Run opendataloader_pdf on all files in one call
        logger.info(f"Running opendataloader_pdf.convert on {len(input_paths)} files")
        try:
            opendataloader_pdf.convert(
                input_path=input_paths, 
                output_dir=str(out_dir), 
                format="json,markdown"
            )
        except Exception as e:
            # The convert function throws if ANY file is corrupt. 
            # However, it still produces output for the valid files.
            # We catch the exception and rely on missing output files to identify failures.
            logger.warning(f"opendataloader_pdf.convert raised an exception (likely due to partial failure): {e}")
        
        # 3 & 4. Per-doc result assembly
        results = []
        failed = []
        
        for doc_id in doc_map.keys():
            md_file = out_dir / f"{doc_id}.md"
            json_file = out_dir / f"{doc_id}.json"
            
            if not md_file.exists() and not json_file.exists():
                logger.error(f"Output for {doc_id} not found, marking as failed.")
                failed.append(doc_id)
                continue
                
            markdown_content = ""
            elements = []
            
            if md_file.exists():
                markdown_content = md_file.read_text(encoding="utf-8")
                
            if json_file.exists():
                elements = json.loads(json_file.read_text(encoding="utf-8"))
                
            result_item = {
                "document_id": doc_id,
                "markdown": markdown_content,
                "elements": elements
            }
            results.append(result_item)
            
        # 5. Response
        return {
            "results": results,
            "failed": failed
        }
        
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        raise
        
    finally:
        # Clean up /tmp/ to avoid filling ephemeral storage on warm invocations
        logger.info(f"Cleaning up {tmp_dir}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
