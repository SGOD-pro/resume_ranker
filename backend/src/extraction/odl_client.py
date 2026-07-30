import json
import logging
import sys
from typing import Any, Dict
from dataclasses import dataclass
import boto3
from botocore.exceptions import ClientError

from src.config.aws import get_settings

logger = logging.getLogger(__name__)

class ODLParseError(Exception):
    """Unified exception for any failure in the ODL parsing pipeline."""
    pass

@dataclass
class ODLParseResult:
    markdown: str
    elements: list[Dict[str, Any]]

def parse(s3_bucket: str, s3_key: str) -> ODLParseResult:
    """
    Parse a document using ODL.
    In local dev, bypasses Lambda and invokes the handler directly via sys.path.
    In prod, invokes the odl-parser-lambda via boto3.
    """
    settings = get_settings()
    event = {
        "s3_bucket": s3_bucket,
        "s3_key": s3_key
    }
    
    try:
        if settings.environment == "local":
            # Local bypass
            # Need to import odl/main.py. We'll add the project root to sys.path if needed,
            # assuming odl is a top-level module or at least accessible from where this runs.
            # Wait, the instruction says "imports odl/main.py directly".
            # The odl lambda is likely in a directory like `odl-parser-lambda` or `odl`.
            # Let's import it safely.
            try:
                # Based on the prompt: "imports odl/main.py directly"
                # which implies `from odl.main import lambda_handler`
                from odl.main import lambda_handler
            except ImportError:
                # If odl is not in path, we might need to add it dynamically, but we'll try straight import first
                # or we can do it more flexibly:
                import os
                project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
                odl_path = os.path.join(project_root, "odl")
                if odl_path not in sys.path:
                    sys.path.append(project_root)
                from odl.main import lambda_handler

            # Invoke locally
            response = lambda_handler(event, None)
            
            # response should be the payload dict directly or a dict with statusCode
            # ODL lambda usually returns a dict with statusCode and body.
            if isinstance(response, dict) and "statusCode" in response:
                if response["statusCode"] != 200:
                    raise ValueError(f"ODL returned {response['statusCode']}: {response.get('body')}")
                payload_str = response.get("body", "{}")
                if isinstance(payload_str, str):
                    payload = json.loads(payload_str)
                else:
                    payload = payload_str
            else:
                payload = response

        else:
            # Production boto3 invoke
            lambda_client = boto3.client("lambda")
            response = lambda_client.invoke(
                FunctionName="odl-parser-lambda",
                InvocationType="RequestResponse",
                Payload=json.dumps(event).encode("utf-8")
            )
            
            payload_bytes = response["Payload"].read()
            response_dict = json.loads(payload_bytes)
            
            if "FunctionError" in response:
                raise ValueError(f"ODL Lambda FunctionError: {response_dict}")
                
            if "statusCode" in response_dict:
                 if response_dict["statusCode"] != 200:
                     raise ValueError(f"ODL returned {response_dict['statusCode']}: {response_dict.get('body')}")
                 body = response_dict.get("body", "{}")
                 if isinstance(body, str):
                     payload = json.loads(body)
                 else:
                     payload = body
            else:
                payload = response_dict

        # Both paths now resolved to `payload` dict
        if "markdown" not in payload:
            raise ValueError("ODL response missing 'markdown' field")

        return ODLParseResult(
            markdown=payload.get("markdown", ""),
            elements=payload.get("elements", [])
        )

    except Exception as e:
        logger.error(f"ODL Parse failed: {str(e)}", exc_info=True)
        raise ODLParseError(f"ODL parsing failed: {str(e)}") from e
