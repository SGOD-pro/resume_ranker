import json
import logging
from typing import Dict, Any, List
import boto3
from src.config.aws import get_settings

logger = logging.getLogger(__name__)

class NovaService:
    def __init__(self):
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=get_settings().aws_default_region,
        aws_access_key_id=get_settings().aws_access_key_id,
        aws_secret_access_key=get_settings().aws_secret_access_key,
        )
        
    def resolve_chunks(self, chunks: List[str], existing_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes unresolved chunks of text and uses Nova Micro to extract missing fields.
        Crucially, it MUST NEVER overwrite a field that the deterministic engine already resolved.
        """
        if not chunks:
            return {}
            
        # Batch up to 10 chunks
        batched_chunks = chunks[:10]
        text_to_process = "\n\n".join(batched_chunks)
        
        # We define a tool schema for the fields we care about.
        tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": "extract_resume_fields",
                        "description": "Extract structured fields from a resume.",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "email": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "skills": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    },
                                    "experience": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "role": {"type": "string"},
                                                "company": {"type": "string"},
                                                "description": {"type": "string"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            ],
            "toolChoice": {
                "tool": {
                    "name": "extract_resume_fields"
                }
            }
        }
        
        prompt = (
            "Extract structured data from the following resume text. "
            "Only extract information that is present in the text.\n\n"
            f"<text>\n{text_to_process}\n</text>"
        )
        
        body = {
            "schemaVersion": "messages-v1",
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": prompt}]
                }
            ],
            "inferenceConfig": {
                "temperature": 0.0
            },
            "toolConfig": tool_config
        }
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId="amazon.nova-micro-v1:0",
                contentType="application/json",
                accept="application/json",
                body=json.dumps(body)
            )
            
            response_body = json.loads(response.get("body").read())
            output_message = response_body.get("output", {}).get("message", {})
            content = output_message.get("content", [])
            
            extracted = {}
            for item in content:
                if "toolUse" in item:
                    if item["toolUse"]["name"] == "extract_resume_fields":
                        extracted = item["toolUse"]["input"]
                        break
                        
            # Merge rule: NEVER overwrite deterministic fields.
            merged = {}
            # For scalars (name, email, phone)
            for key in ["name", "email", "phone"]:
                if existing_fields.get(key):
                    # Deterministic already resolved this, skip
                    merged[key] = existing_fields[key]
                elif extracted.get(key):
                    merged[key] = extracted[key]
                else:
                    merged[key] = existing_fields.get(key)
                    
            # For arrays (skills, experience), we can append, but for simplicity here we just
            # preserve existing if they exist, else use LLM, or combine.
            # R-08 implies "never overwrite a field". If deterministic found skills, we might keep them or append.
            # Let's say we don't overwrite if existing is not empty.
            if existing_fields.get("skills"):
                merged["skills"] = existing_fields["skills"]
            else:
                merged["skills"] = extracted.get("skills", [])
                
            if existing_fields.get("experience"):
                merged["experience"] = existing_fields["experience"]
            else:
                merged["experience"] = extracted.get("experience", [])
                
            # Keep anything else from existing fields
            for k, v in existing_fields.items():
                if k not in merged:
                    merged[k] = v
                    
            return merged

        except Exception as e:
            logger.error(f"Nova LLM fallback failed: {e}")
            return existing_fields
