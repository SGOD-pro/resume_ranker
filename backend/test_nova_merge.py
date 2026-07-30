import sys
import os
import json

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.extraction.fallback.nova_service import NovaService

def test_nova_merge():
    from unittest.mock import patch, MagicMock
    
    # We provide a chunk that has an email and phone
    chunks = [
        "Contact me at new_email@example.com or 555-123-4567. I am an engineer."
    ]
    
    existing_fields = {
        "name": "Jane Doe",
        "email": "old_deterministic@example.com",
        "phone": None
    }

    with patch("boto3.client") as mock_boto:
        mock_bedrock = MagicMock()
        mock_boto.return_value = mock_bedrock
        
        # Simulate Bedrock Nova response
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
        
        nova = NovaService()
        
        merged = nova.resolve_chunks(chunks, existing_fields)
    
    print("Merged output:")
    print(json.dumps(merged, indent=2))
    
    assert merged["email"] == "old_deterministic@example.com", "Failed: Email was overwritten!"
    assert merged["phone"] is not None and "555" in merged["phone"], "Failed: Phone was not filled!"
    print("Success: Deterministic field survived, Nova filled the missing field.")

if __name__ == "__main__":
    test_nova_merge()
