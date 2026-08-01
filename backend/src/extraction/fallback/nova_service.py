import json
import logging
import re
from typing import Dict, Any, List

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.config.aws import get_settings

logger = logging.getLogger(__name__)

# ── System prompt — embeds the full JSON schema per AWS Nova docs ──────────────
# Pattern: https://docs.aws.amazon.com/nova/latest/userguide/prompting-structured-output.html
# Strategy: system prompt declares the schema + rules; assistant prefill of "{"
# forces Nova directly into the JSON body with no preamble.
_SYSTEM_PROMPT = (
    "You are a resume parser. Extract fields from the resume text and output ONLY a valid "
    "JSON object matching this exact schema. Do NOT include markdown fencing, preamble, or "
    "any explanation — output the JSON object only.\n\n"
    "Schema:\n"
    '{\n'
    '  "name": "<full name as string, or null>",\n'
    '  "email": "<email address as string, or null>",\n'
    '  "phone": "<phone number as string, or null>",\n'
    '  "skills": ["<skill string>"],\n'
    '  "experience": [\n'
    '    {"role": "<job title>", "company": "<company name>", "description": "<summary>"}\n'
    '  ],\n'
    '  "education": [\n'
    '    {"degree": "<degree name>", "institution": "<school name>", "year": "<graduation year or null>"}\n'
    '  ]\n'
    '}\n\n'
    "Rules:\n"
    "- Use null for scalar fields not found in the text.\n"
    "- Use [] for array fields with no items found.\n"
    "- Output ONLY the JSON object. No markdown. No explanation."
)


class NovaService:
    """
    LLM fallback using Amazon Nova Micro via the Bedrock ``converse`` API.

    Per the AWS Nova structured-output docs we use a system prompt that contains
    the full JSON schema and prefill the assistant turn with ``{`` to guide the
    model directly into a JSON object — no ``toolConfig`` / ``invoke_model`` needed.
    """

    def __init__(self):
        from src.config.aws import get_client
        # Strict 10-second timeout — fail loudly, don't hang
        _config = Config(
            connect_timeout=10,
            read_timeout=10,
            retries={"max_attempts": 2},
        )
        self.bedrock_client = get_client("bedrock-runtime", config=_config)
        self._dead = False  # Set True if quota exhausted — skip further calls

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def resolve_chunks(self, chunks: List[str], existing_fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes unresolved text chunks and uses Amazon Nova Micro to extract
        missing resume fields.

        Merge rule (R-08 / R-09):
          R-08 — NEVER overwrite a field already resolved by the deterministic engine.
          R-09 — MUST fill a null/empty field left by the deterministic engine.
        """
        if not chunks:
            return {}

        # If quota exhausted in this session, skip all further calls
        if self._dead:
            logger.debug("Nova LLM skipped — quota exhausted for this session")
            return self._merge(existing_fields, {})

        # Cap at 10 chunks / ~4 000 chars to stay within Nova Micro context limit
        text_to_process = "\n\n".join(chunks[:10])[:4000]

        user_text = (
            "Extract all resume fields from the following text.\n\n"
            f"<resume>\n{text_to_process}\n</resume>"
        )

        extracted = self._call_nova(user_text)
        return self._merge(existing_fields, extracted)

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _call_nova(self, user_text: str) -> Dict[str, Any]:
        """
        Calls the Bedrock converse API and returns the parsed JSON dict.
        Returns {} on any error so the caller falls back to deterministic fields.
        """
        import time
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.bedrock_client.converse(
                    modelId="amazon.nova-lite-v1:0",
                    system=[{"text": _SYSTEM_PROMPT}],
                    messages=[
                        {
                            "role": "user",
                            "content": [{"text": user_text}],
                        },
                        # Prefill the assistant turn with "{" — nudges Nova directly
                        # into the JSON body, skipping any preamble text.
                        {
                            "role": "assistant",
                            "content": [{"text": "{"}],
                        },
                    ],
                    inferenceConfig={
                        "temperature": 0.0,
                        "maxTokens": 512,
                        # Stop on closing fence in case the model emits one anyway
                        "stopSequences": ["```"],
                    },
                )

                # ── Extract text block from converse response ──────────────────
                content_blocks = (
                    response.get("output", {})
                            .get("message", {})
                            .get("content", [])
                )
                raw_text = ""
                for block in content_blocks:
                    if isinstance(block, dict) and "text" in block:
                        raw_text = block["text"].strip()
                        break

                # The model continues from the prefilled "{", so re-prepend it
                if raw_text and not raw_text.startswith("{"):
                    raw_text = "{" + raw_text

                usage = response.get("usage", {})

                # ── Parse JSON ─────────────────────────────────────────────────
                try:
                    parsed = json.loads(raw_text)
                    parsed["_nova_tokens"] = usage
                    return parsed
                except (json.JSONDecodeError, ValueError) as parse_err:
                    logger.warning(
                        "Nova JSON parse error (%s). Raw response: %.300s",
                        parse_err, raw_text,
                    )
                    # Best-effort: grab the first balanced { … } block
                    m = re.search(r"\{.*?\}", raw_text, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                            parsed["_nova_tokens"] = usage
                            return parsed
                        except Exception:
                            pass
                    return {}

            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                error_msg = exc.response.get("Error", {}).get("Message", str(exc))
                http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

                if error_code in ("ThrottlingException", "TooManyRequestsException",
                                  "ServiceQuotaExceededException"):
                    logger.error(
                        "Nova LLM QUOTA EXHAUSTED [%s] HTTP %s: %s — "
                        "Attempt %d/%d. Sleeping...",
                        error_code, http_status, error_msg, attempt + 1, max_retries
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # 1s, 2s
                        continue
                    else:
                        return {}
                elif error_code in ("AccessDeniedException", "UnrecognizedClientException",
                                    "InvalidSignatureException"):
                    logger.error(
                        "Nova LLM AUTH FAILURE [%s] HTTP %s: %s",
                        error_code, http_status, error_msg,
                    )
                    self._dead = True
                    return {}
                else:
                    logger.error(
                        "Nova LLM ClientError [%s] HTTP %s: %s",
                        error_code, http_status, error_msg,
                    )
                    return {}

            except Exception as exc:
                logger.error(
                    "Nova LLM unexpected error [%s]: %s",
                    type(exc).__name__, exc,
                )
                return {}

        return {}

    @staticmethod
    def _merge(existing: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applies R-08 and R-09.

        R-08: If the deterministic engine already resolved a field (truthy value),
              keep it — do NOT let the LLM overwrite it.
        R-09: If the deterministic engine left a field null/empty,
              accept the LLM's value.
        """
        merged: Dict[str, Any] = {}

        # Scalar fields
        for key in ("name", "email", "phone"):
            det_val = existing.get(key)
            if det_val:                                  # R-08: deterministic wins
                merged[key] = det_val
            elif extracted.get(key):                     # R-09: LLM fills the gap
                merged[key] = extracted[key]
            else:
                merged[key] = det_val                   # stays None

        # Array fields
        for key in ("skills", "experience", "education"):
            det_val = existing.get(key)
            if det_val:                                  # R-08: non-empty → preserve
                merged[key] = det_val
            else:
                merged[key] = extracted.get(key) or []  # R-09: LLM fills the gap

        # Preserve any additional fields from deterministic (e.g. projects, certs)
        for k, v in existing.items():
            if k not in merged:
                merged[k] = v

        if "_nova_tokens" in extracted:
            merged["_nova_tokens"] = extracted["_nova_tokens"]

        return merged
