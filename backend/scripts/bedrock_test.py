from botocore.exceptions import ClientError
import json
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path
import os
import sys

SCRIPT_DIR  = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

for p in [str(BACKEND_DIR), str(PROJECT_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import boto3

from src.config.aws import get_settings
settings = get_settings()
client = boto3.client(
    "bedrock-runtime",
    region_name=settings.aws_default_region,
    aws_access_key_id=settings.aws_access_key_id,
    aws_secret_access_key=settings.aws_secret_access_key,
)

try:
    response = client.converse(
        modelId="amazon.nova-micro-v1:0",
        messages=[
            {
                "role": "user",
                "content": [{"text": "Hello"}]
            }
        ]
    )
except ClientError as e:
    print(json.dumps(e.response, indent=2))