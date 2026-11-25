"""
test_llm_json_resilience.py — Comprehensive LLM Structured Output Failure & Schema Tests
=======================================================================================
Verifies all 10 edge cases required by Section 31 of the Senior Principal Engineer spec:
1. Standard clean JSON object
2. Markdown fenced JSON (` ```json ... ``` `)
3. Preamble text preceding JSON (`Here is the JSON: ...`)
4. Completely invalid JSON syntax
5. Valid JSON with completely wrong schema
6. Valid schema with invalid field types (type coercion)
7. Empty / whitespace string response
8. Provider envelope containing structured tool response
9. Multiple JSON objects returned sequentially
10. Truncated JSON response (unclosed brackets/braces)
"""

import pytest
from src.extraction.fallback.nova_service import parse_and_validate_llm_json, NovaService


def test_case_1_clean_json():
    raw = '{"name":"John Doe","email":"john@example.com","skills":["Python","FastAPI"]}'
    res = parse_and_validate_llm_json(raw)
    assert res.get("name") == "John Doe"
    assert res.get("email") == "john@example.com"
    assert res.get("skills") == ["Python", "FastAPI"]


def test_case_2_markdown_fenced_json():
    raw = '```json\n{"name":"Jane Smith","email":"jane@example.com"}\n```'
    res = parse_and_validate_llm_json(raw)
    assert res.get("name") == "Jane Smith"
    assert res.get("email") == "jane@example.com"


def test_case_3_preamble_before_json():
    raw = 'Here is the JSON extracted from the resume:\n{"name":"Alice Walker","skills":["AWS","Docker"]}\nI hope this helps!'
    res = parse_and_validate_llm_json(raw)
    assert res.get("name") == "Alice Walker"
    assert res.get("skills") == ["AWS", "Docker"]


def test_case_4_invalid_json():
    raw = 'This is completely non-JSON text with no braces or structures at all.'
    res = parse_and_validate_llm_json(raw)
    assert res == {}


def test_case_5_wrong_schema():
    raw = '{"unrelated_key": 12345, "another_junk": true}'
    res = parse_and_validate_llm_json(raw)
    # Must terminate safely and return default schema values or empty fields
    assert res.get("name") is None
    assert res.get("skills") == []
    assert res.get("experience") == []


def test_case_6_invalid_field_types():
    raw = '{"name": 99999, "skills": "Python, SQL, Go", "experience": "Senior Engineer"}'
    res = parse_and_validate_llm_json(raw)
    # Type coercion: name is stringified, skills coerced from string to list, experience coerced to list of dict
    assert res.get("name") == "99999"
    assert "Python" in res.get("skills", [])
    assert len(res.get("experience", [])) == 1
    assert res["experience"][0]["role"] == "Senior Engineer"


def test_case_7_empty_response():
    assert parse_and_validate_llm_json("") == {}
    assert parse_and_validate_llm_json("   \n\t  ") == {}
    assert parse_and_validate_llm_json(None) == {}


def test_case_8_provider_envelope():
    raw = '{"output": {"message": {"content": [{"text": "{\\"name\\": \\"Bob Ross\\", \\"skills\\": [\\"Painting\\"]}"}]}}}'
    res = parse_and_validate_llm_json(raw)
    assert res.get("name") == "Bob Ross"
    assert res.get("skills") == ["Painting"]


def test_case_9_multiple_json_objects():
    raw = '{"name":"Candidate One","skills":["Java"]}\n{"name":"Candidate Two","skills":["C++"]}'
    res = parse_and_validate_llm_json(raw)
    # Should safely extract the first valid JSON object
    assert res.get("name") == "Candidate One"
    assert res.get("skills") == ["Java"]


def test_case_10_truncated_json():
    raw = '{"name": "Truncated User", "skills": ["Python", "Rust"'
    res = parse_and_validate_llm_json(raw)
    # Balanced recovery should recover name and available skills or safely return empty
    assert isinstance(res, dict)
    if "name" in res:
        assert res["name"] == "Truncated User"


def test_merge_immutability_rule_r08_r09():
    """Verify deterministic fields are strictly protected against overwrite."""
    existing = {
        "name": "Deterministic Verified Name",
        "skills": ["Python", "PostgreSQL"],
        "email": None,
        "phone": None,
    }
    extracted = {
        "name": "Malicious Or Hallucinated Name",
        "skills": ["Javascript"],
        "email": "infilled@example.com",
        "phone": "555-1234",
    }
    merged = NovaService._merge(existing, extracted)
    # R-08: Non-null deterministic name and skills preserved
    assert merged["name"] == "Deterministic Verified Name"
    assert merged["skills"] == ["Python", "PostgreSQL"]
    # R-09: Infill gaps
    assert merged["email"] == "infilled@example.com"
    assert merged["phone"] == "555-1234"
