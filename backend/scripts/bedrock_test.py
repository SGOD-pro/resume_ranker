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


def main():
    settings = get_settings()
    client = boto3.client(
        "bedrock-runtime",
        region_name=getattr(settings, "AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
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
        print(response)
    except ClientError as e:
        print(json.dumps(e.response, indent=2))


if __name__ == "__main__":
    main()