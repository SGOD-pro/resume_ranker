"""
fallback/nova_service.py — Amazon Nova LLM Fallback Integration
================================================================
Invokes Bedrock Converse API with tool-use constrained decoding.
Escalates from Nova Micro to Nova Lite if confidence is low.
"""

import logging
from typing import Any

import boto3  # type: ignore

from src.config.aws import get_boto3_kwargs
from src.extraction.domain_extraction import ExtractedField, ExtractionResult, UnresolvedChunk
from src.extraction.fallback.schema import FallbackExtractionSchema

logger = logging.getLogger(__name__)

# System prompt instructs the model to act as a strict data extractor.
SYSTEM_PROMPT = (
    "You are an expert resume parsing AI. Extract structured data from the provided text. "
    "Use the `extract_resume_data` tool to output the data. "
    "If a field is not present or cannot be determined, omit it (leave it null/empty). "
    "Do not hallucinate information."
)

MODEL_MICRO = "us.amazon.nova-micro-v1:0"
MODEL_LITE = "us.amazon.nova-lite-v1:0"
CONFIDENCE_THRESHOLD = 0.5


class NovaFallbackError(Exception):
    pass


class NovaFallbackService:
    def __init__(self) -> None:
        self._client = boto3.client("bedrock-runtime", **get_boto3_kwargs())

    def process_chunks(
        self, document_id: str, chunks: list[UnresolvedChunk]
    ) -> tuple[dict[str, Any], str, float]:
        """
        Process unresolved chunks using Nova Micro. Escalate to Lite if needed.
        Returns (extracted_dict, model_used, confidence)
        """
        if not chunks:
            return {}, MODEL_MICRO, 1.0

        combined_text = "\n\n---\n\n".join(chunk.text for chunk in chunks)
        
        # 1. Try Micro
        result, confidence = self._invoke_nova(MODEL_MICRO, combined_text)
        
        # 2. Escalate to Lite if confidence is too low
        if confidence < CONFIDENCE_THRESHOLD:
            logger.info("Nova Micro confidence %s < %s. Escalating to Nova Lite for %s", 
                        confidence, CONFIDENCE_THRESHOLD, document_id)
            lite_result, lite_conf = self._invoke_nova(MODEL_LITE, combined_text)
            return lite_result, MODEL_LITE, lite_conf
            
        return result, MODEL_MICRO, confidence

    def _invoke_nova(self, model_id: str, text: str) -> tuple[dict[str, Any], float]:
        """Call Bedrock Converse API with tool use."""
        tool_config = {
            "tools": [
                {
                    "toolSpec": {
                        "name": "extract_resume_data",
                        "description": "Extract structured fields from resume text.",
                        "inputSchema": {
                            "json": FallbackExtractionSchema.model_json_schema()
                        },
                    }
                }
            ],
            "toolChoice": {
                "tool": {"name": "extract_resume_data"}
            },
        }

        messages = [
            {
                "role": "user",
                "content": [{"text": text}],
            }
        ]

        try:
            response = self._client.converse(
                modelId=model_id,
                messages=messages,
                system=[{"text": SYSTEM_PROMPT}],
                toolConfig=tool_config,
                inferenceConfig={"temperature": 0.0},  # Maximum determinism
            )
        except Exception as e:
            logger.error("Bedrock Converse API failed: %s", e)
            raise NovaFallbackError(f"Bedrock invocation failed: {e}") from e

        output = response["output"]
        message = output.get("message", {})
        content = message.get("content", [])

        # Parse tool use
        for block in content:
            if "toolUse" in block:
                tool_use = block["toolUse"]
                if tool_use["name"] == "extract_resume_data":
                    extracted = tool_use["input"]
                    # Bedrock guarantees it matches our schema
                    confidence = float(extracted.get("confidence", 0.0))
                    # Remove confidence from the actual data payload
                    extracted.pop("confidence", None)
                    return extracted, confidence

        logger.warning("Nova did not return the expected tool use block.")
        return {}, 0.0

    def merge_results(
        self, 
        base_result: ExtractionResult, 
        nova_data: dict[str, Any],
        model_used: str,
        confidence: float
    ) -> ExtractionResult:
        """
        Merge Nova data into the base ExtractionResult.
        Rule: Nova NEVER overwrites deterministic-resolved fields.
        """
        # Top-level fields
        scalar_fields = ["name", "email", "phone", "linkedin", "github", "location", "summary"]
        for field in scalar_fields:
            existing = getattr(base_result, field)
            nova_val = nova_data.get(field)
            if not existing and nova_val:
                setattr(base_result, field, ExtractedField(
                    value=nova_val,
                    confidence=confidence,
                    provenance=model_used  # type: ignore
                ))

        # List fields (Skills)
        # We append novel skills to the existing list
        if nova_data.get("skills"):
            if not base_result.skills:
                base_result.skills = ExtractedField(
                    value=nova_data["skills"],
                    confidence=confidence,
                    provenance=model_used  # type: ignore
                )
            else:
                existing_skills = {s.lower() for s in base_result.skills.value}
                new_skills = []
                for skill in nova_data["skills"]:
                    if skill.lower() not in existing_skills:
                        new_skills.append(skill)
                        existing_skills.add(skill.lower())
                
                if new_skills:
                    base_result.skills = ExtractedField(
                        value=base_result.skills.value + new_skills,
                        confidence=base_result.skills.confidence,
                        provenance=base_result.skills.provenance
                    )

        # Complex lists (Experience, Education)
        # For simplicity in this iteration, if deterministic engine completely failed (empty list),
        # we take Nova's list. If deterministic found SOME, we do not attempt complex deep-merges 
        # to avoid duplicating jobs.
        if not base_result.experience and nova_data.get("experience"):
            base_result.experience = ExtractedField(
                value=nova_data["experience"], 
                confidence=confidence, 
                provenance=model_used  # type: ignore
            )
            
        if not base_result.education and nova_data.get("education"):
            base_result.education = ExtractedField(
                value=nova_data["education"], 
                confidence=confidence, 
                provenance=model_used  # type: ignore
            )

        return base_result
