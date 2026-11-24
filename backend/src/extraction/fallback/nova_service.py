import json
import logging
import os
import re
from typing import Dict, Any, List, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel, Field, field_validator

from src.config.aws import get_settings

logger = logging.getLogger(__name__)

# ── Pydantic structured output models ──────────────────────────────────────────

class NovaExperienceItem(BaseModel):
    role: Optional[str] = ""
    company: Optional[str] = ""
    description: Optional[str] = ""

    @field_validator("role", "company", "description", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return str(v).strip() if v is not None else ""

class NovaEducationItem(BaseModel):
    degree: Optional[str] = ""
    institution: Optional[str] = ""
    year: Optional[str] = None

    @field_validator("degree", "institution", "year", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("null", "none", "n/a") else None

class NovaResumeSchema(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[NovaExperienceItem] = Field(default_factory=list)
    education: List[NovaEducationItem] = Field(default_factory=list)

    @field_validator("name", "email", "phone", mode="before")
    @classmethod
    def _coerce_scalar(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s if s and s.lower() not in ("null", "none", "n/a") else None

    @field_validator("skills", mode="before")
    @classmethod
    def _coerce_skills(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        if isinstance(v, list):
            res = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    res.append(item.strip())
                elif isinstance(item, (int, float)):
                    res.append(str(item))
                elif isinstance(item, dict) and "name" in item:
                    res.append(str(item["name"]).strip())
            return res
        return []

    @field_validator("experience", mode="before")
    @classmethod
    def _coerce_experience(cls, v):
        if not v:
            return []
        if isinstance(v, str) and v.strip():
            return [{"role": v.strip(), "company": "", "description": ""}]
        if not isinstance(v, list):
            return []
        res = []
        for item in v:
            if isinstance(item, dict):
                res.append(item)
            elif isinstance(item, str) and item.strip():
                res.append({"role": item.strip(), "company": "", "description": ""})
        return res

    @field_validator("education", mode="before")
    @classmethod
    def _coerce_education(cls, v):
        if not v:
            return []
        if isinstance(v, str) and v.strip():
            return [{"degree": v.strip(), "institution": "", "year": None}]
        if not isinstance(v, list):
            return []
        res = []
        for item in v:
            if isinstance(item, dict):
                res.append(item)
            elif isinstance(item, str) and item.strip():
                res.append({"degree": item.strip(), "institution": "", "year": None})
        return res


def parse_and_validate_llm_json(raw_text: str) -> Dict[str, Any]:
    """Robust parser & validator for LLM structured output.

    Handles:
    1. Clean JSON objects
    2. Markdown code fences (```json ... ```)
    3. Preamble/postscript text
    4. Invalid JSON syntax (graceful fallback)
    5. Schema mismatch / unexpected keys (strict filtering)
    6. Invalid field types (coercion via Pydantic)
    7. Empty or whitespace responses
    8. Provider envelopes (e.g. {'output': {'message': ...}})
    9. Multiple JSON objects returned (takes first valid)
    10. Truncated JSON (attempts balanced closure or graceful recovery)
    """
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        return {}

    cleaned = raw_text.strip()

    # 1. Strip markdown fences if present
    if "```" in cleaned:
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            cleaned = re.sub(r"```[a-zA-Z]*", "", cleaned).replace("```", "").strip()

    parsed_dict: Optional[Dict[str, Any]] = None

    # First attempt: direct json.loads
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # Check for provider envelope: {'output': ...}
            if "output" in data and isinstance(data["output"], dict):
                msg = data["output"].get("message", {})
                content = msg.get("content", [])
                if content and isinstance(content[0], dict) and "text" in content[0]:
                    return parse_and_validate_llm_json(content[0]["text"])
            parsed_dict = data
    except (json.JSONDecodeError, ValueError):
        pass

    # Second attempt: find balanced braces { ... }
    if parsed_dict is None:
        start_idx = cleaned.find("{")
        if start_idx != -1:
            depth = 0
            end_idx = -1
            in_string = False
            escape = False
            for i in range(start_idx, len(cleaned)):
                c = cleaned[i]
                if escape:
                    escape = False
                    continue
                if c == "\\":
                    escape = True
                    continue
                if c == '"':
                    in_string = not in_string
                    continue
                if not in_string:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
            if end_idx != -1:
                candidate_str = cleaned[start_idx:end_idx]
                try:
                    candidate_data = json.loads(candidate_str)
                    if isinstance(candidate_data, dict):
                        parsed_dict = candidate_data
                except Exception:
                    pass

    # Third attempt: truncated JSON recovery (e.g. unclosed brackets/braces)
    if parsed_dict is None:
        start_idx = cleaned.find("{")
        if start_idx != -1:
            sub = cleaned[start_idx:]
            for suffix in ('"}', '"]}', '"]}}', '}'):
                try:
                    candidate_data = json.loads(sub + suffix)
                    if isinstance(candidate_data, dict):
                        parsed_dict = candidate_data
                        break
                except Exception:
                    pass

    if parsed_dict is None:
        return {}

    # 3. Validate against Pydantic schema
    try:
        model = NovaResumeSchema.model_validate(parsed_dict)
        return model.model_dump(exclude_unset=False)
    except Exception as val_err:
        logger.warning("Nova schema validation error: %s", val_err)
        res = {}
        if "name" in parsed_dict and isinstance(parsed_dict["name"], str):
            res["name"] = parsed_dict["name"]
        if "skills" in parsed_dict and isinstance(parsed_dict["skills"], list):
            res["skills"] = [str(s) for s in parsed_dict["skills"] if isinstance(s, (str, int, float))]
        if "experience" in parsed_dict and isinstance(parsed_dict["experience"], list):
            res["experience"] = [e for e in parsed_dict["experience"] if isinstance(e, dict)]
        if "education" in parsed_dict and isinstance(parsed_dict["education"], list):
            res["education"] = [e for e in parsed_dict["education"] if isinstance(e, dict)]
        return res

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


class NovaProviderError(Exception):
    """Base exception for Nova Bedrock provider failures."""
    pass


class NovaThrottlingError(NovaProviderError):
    """Raised when Bedrock throttles requests (HTTP 429, ThrottlingException, etc.)."""
    pass


class NovaQuotaExceededError(NovaProviderError):
    """Raised when AWS account or model quota is exhausted."""
    pass


class NovaService:
    """
    LLM fallback using Amazon Nova Micro via the Bedrock ``converse`` API.

    Per the AWS Nova structured-output docs we use a system prompt that contains
    the full JSON schema and prefill the assistant turn with ``{`` to guide the
    model directly into a JSON object — no ``toolConfig`` / ``invoke_model`` needed.
    """

    _last_call_time: float = 0.0
    _min_call_interval: float = 4.0  # 15 calls per minute (60s / 15 = 4.0s)

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

        has_skills = bool(existing_fields.get("skills"))
        has_exp = bool(existing_fields.get("experience"))
        is_name_missing = not existing_fields.get("name") or existing_fields.get("name") == "Name needs review"

        if is_name_missing and (has_skills or has_exp):
            user_text = (
                "Extract the candidate full name from the following resume header text.\n\n"
                f"<header>\n{text_to_process[:800]}\n</header>"
            )
        else:
            user_text = (
                "Extract all resume fields from the following text.\n\n"
                f"<resume>\n{text_to_process}\n</resume>"
            )

        extracted = self._call_nova(user_text) if not self._dead else {}

        # If Nova LLM did not resolve name or experience, apply heuristic fallback
        if not extracted or not (extracted.get("name") or extracted.get("experience")):
            heuristics = self._heuristic_infill(text_to_process, existing_fields)
            if not extracted:
                extracted = heuristics
            else:
                for k, v in heuristics.items():
                    if not extracted.get(k):
                        extracted[k] = v

        return self._merge(existing_fields, extracted)

    def _heuristic_infill(self, text: str, existing: Dict[str, Any]) -> Dict[str, Any]:
        """Heuristic extractor fallback when Nova Bedrock is unreachable or rate limited."""
        result: Dict[str, Any] = {}
        from src.extractors.contact.identity_resolver import CandidateIdentityResolver
        resolver = CandidateIdentityResolver()

        # 1. Candidate Name resolution
        name_cand = None
        # Check email prefix first (e.g., subhadip.mondal@example.com -> Subhadip Mondal)
        email = existing.get("email") or ""
        if not email:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            if email_match:
                email = email_match.group(0)
                result["email"] = email

        if email and "@" in email:
            handle = email.split("@")[0]
            parts = re.split(r'[._\-]+', handle)
            clean_parts = [re.sub(r'\d+', '', p).strip().title() for p in parts]
            clean_parts = [p for p in clean_parts if len(p) >= 2 and p.isalpha()]
            if 2 <= len(clean_parts) <= 3:
                potential_name = " ".join(clean_parts)
                cleaned, err = resolver._clean_and_validate(potential_name)
                if cleaned:
                    valid, _ = resolver._evaluate_negative_evidence(cleaned)
                    if valid:
                        name_cand = potential_name

        # If still no name, check top 10 lines of text
        if not name_cand:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for line in lines[:10]:
                if len(line) < 3 or len(line) > 40:
                    continue
                if any(c in line for c in "@|/\\;:•*+~=[]{}()<>"):
                    continue
                if re.search(r'\d', line):
                    continue
                cleaned, err = resolver._clean_and_validate(line)
                if cleaned:
                    valid, _ = resolver._evaluate_negative_evidence(cleaned)
                    if valid:
                        name_cand = cleaned
                        break

        if name_cand:
            result["name"] = name_cand

        # 2. Experience extraction fallback if missing
        if not existing.get("experience"):
            exp_entries = []
            role_keywords = (
                "engineer", "developer", "scientist", "manager", "architect",
                "analyst", "consultant", "intern", "specialist", "designer",
                "administrator", "lead", "officer", "executive", "associate"
            )
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if any(kw in line_lower for kw in role_keywords) and len(line) < 80:
                    context = " ".join(lines[max(0, i-1):min(len(lines), i+3)])
                    exp_entries.append({
                        "role": line,
                        "company": "",
                        "description": context[:200],
                    })
                    if len(exp_entries) >= 3:
                        break
            if exp_entries:
                result["experience"] = exp_entries

        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _call_nova(self, user_text: str) -> Dict[str, Any]:
        """
        Calls the Bedrock converse API and returns the parsed JSON dict.
        Returns {} on any error so the caller falls back to deterministic fields.
        """
        import time
        max_retries = 2

        # Enforce rate limit: configurable via NOVA_MIN_INTERVAL (default 1.0s, 0.0s in tests/mocks)
        min_interval = float(os.environ.get("NOVA_MIN_INTERVAL", "1.0"))
        is_mock = (
            hasattr(self.bedrock_client, "_mock_return_value")
            or type(self.bedrock_client).__name__ == "MagicMock"
            or (hasattr(self.bedrock_client, "converse") and type(self.bedrock_client.converse).__name__ == "MagicMock")
        )
        if min_interval > 0 and not is_mock:
            now = time.time()
            elapsed = now - NovaService._last_call_time
            if elapsed < min_interval:
                sleep_needed = min_interval - elapsed
                time.sleep(sleep_needed)
            NovaService._last_call_time = time.time()

        for attempt in range(max_retries):
            try:
                response = self.bedrock_client.converse(
                    modelId="apac.amazon.nova-lite-v1:0",
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

                # ── Robust Parse & Validate JSON via Pydantic ─────────────────
                parsed = parse_and_validate_llm_json(raw_text)
                if parsed:
                    parsed["_nova_tokens"] = usage
                    return parsed
                return {}


            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code", "Unknown")
                error_msg = exc.response.get("Error", {}).get("Message", str(exc))
                http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")

                if error_code in ("ThrottlingException", "TooManyRequestsException", "RequestLimitExceeded"):
                    logger.error(
                        "Nova LLM THROTTLED [%s] HTTP %s: %s — Attempt %d/%d. Sleeping...",
                        error_code, http_status, error_msg, attempt + 1, max_retries,
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # 1s, 2s
                        continue
                    else:
                        raise NovaThrottlingError(
                            f"Bedrock Nova throttled after {max_retries} attempts: [{error_code}] {error_msg}"
                        )
                elif error_code == "ServiceQuotaExceededException":
                    logger.error("Nova LLM QUOTA EXHAUSTED [%s] HTTP %s: %s", error_code, http_status, error_msg)
                    self._dead = True
                    raise NovaQuotaExceededError(f"Bedrock Nova quota exhausted: [{error_code}] {error_msg}")
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

        # ── Name resolution & validation (Rule 7) ─────────────────────────────
        det_name = existing.get("name")
        if det_name:
            # R-08: Deterministic verified identity is NEVER overwritten
            merged["name"] = det_name
        elif extracted.get("name"):
            # R-09: Validate LLM returned candidate before accepting
            from src.extractors.contact.identity_resolver import (
                CandidateIdentityResolver,
                IdentityStatus,
                IdentitySource,
            )
            resolver = CandidateIdentityResolver()
            raw_llm_name = str(extracted["name"]).strip()
            cleaned, clean_err = resolver._clean_and_validate(raw_llm_name)
            is_valid, neg_err = (False, clean_err) if not cleaned else resolver._evaluate_negative_evidence(cleaned)

            if is_valid and cleaned:
                norm_name = resolver._normalize_name(cleaned)
                merged["name"] = norm_name
                merged["identity"] = {
                    "display_name": norm_name,
                    "normalized_name": norm_name,
                    "confidence": 0.65,
                    "status": IdentityStatus.PLAUSIBLE.value,
                    "source": IdentitySource.LLM_INFILL.value,
                    "evidence_text": raw_llm_name,
                    "warnings": ["Resolved via Nova LLM fallback"],
                }
            else:
                logger.warning("Nova LLM proposed invalid name candidate (%s): rejected", neg_err or clean_err)
                merged["name"] = None
                existing_identity = existing.get("identity") or {}
                existing_identity["warnings"] = existing_identity.get("warnings", []) + [
                    f"Nova LLM proposed candidate {raw_llm_name!r} failed identity validation: {neg_err or clean_err}"
                ]
                merged["identity"] = existing_identity
        else:
            merged["name"] = None

        # Scalar contact fields
        for key in ("email", "phone"):
            det_val = existing.get(key)
            if det_val:
                merged[key] = det_val
            elif extracted.get(key):
                merged[key] = extracted[key]
            else:
                merged[key] = det_val


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
