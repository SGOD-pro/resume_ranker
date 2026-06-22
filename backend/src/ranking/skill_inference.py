"""
skill_inference.py — Inference Engine for skill matching
==========================================================
Uses skill_graph.json to infer skills from candidate skill lists.

Match hierarchy (strict weights):
    Explicit = 1.00  (direct match after normalization)
    Alias    = 1.00  (same canonical form in graph aliases)
    Inferred = 0.75  (follows 'implies' edges in the graph)
    Related  = 0.50  (follows 'related' edges in the graph)

Usage:
    engine = SkillInferenceEngine()
    result = engine.match_skills(candidate_skills, jd_skills)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.registries.skill_registry import (
    normalize as _normalize,
    normalize_for_graph as _normalize_for_graph,
    match as _alias_match,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────

WEIGHT_EXPLICIT = 1.00
WEIGHT_ALIAS    = 1.00
WEIGHT_INFERRED = 0.75
WEIGHT_RELATED  = 0.50
WEIGHT_DOMAIN   = 0.25


@dataclass
class SkillMatchResult:
    """A single skill match with provenance."""
    skill: str          # The JD skill being matched
    source: str         # What resume skill triggered it ("" for explicit)
    match_type: str     # "explicit" | "alias" | "inferred" | "related"
    weight: float       # 1.00 | 1.00 | 0.75 | 0.50
    explanation: str    # Human-readable: "React ← inferred from Next.js"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "source": self.source,
            "match_type": self.match_type,
            "weight": self.weight,
            "explanation": self.explanation,
        }


@dataclass
class InferenceResult:
    """Complete inference result for a candidate vs JD skill set."""
    explicit_skills: List[str] = field(default_factory=list)
    inferred_skills: List[SkillMatchResult] = field(default_factory=list)
    related_skills: List[SkillMatchResult] = field(default_factory=list)
    all_matches: List[SkillMatchResult] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)

    # Per-skill weight map: jd_skill → best weight found
    skill_weights: Dict[str, float] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Graph Loader
# ─────────────────────────────────────────────────────────────────────────────

_GRAPH_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'registries', 'skill_graph.json'
)

_cached_graph: Optional[Dict] = None


def _load_graph() -> Dict:
    """Load and cache the skill graph from JSON."""
    global _cached_graph
    if _cached_graph is not None:
        return _cached_graph

    with open(_GRAPH_PATH) as f:
        raw = json.load(f)

    skills = {}
    alias_to_key: Dict[str, str] = {}

    for key, entry in raw.get('skills', {}).items():
        if key.startswith('___'):
            continue  # Skip section comment keys
        skills[key] = entry
        # Build alias → graph_key reverse index
        for alias in entry.get('aliases', []):
            norm = _normalize(alias)
            alias_to_key[norm] = key
        # Also index by key itself
        alias_to_key[key] = key

    _cached_graph = {
        'skills': skills,
        'domains': raw.get('domains', {}),
        'alias_to_key': alias_to_key,
    }
    return _cached_graph


# ─────────────────────────────────────────────────────────────────────────────
# Inference Engine
# ─────────────────────────────────────────────────────────────────────────────

class SkillInferenceEngine:
    """Graph-based skill inference engine.

    Usage:
        engine = SkillInferenceEngine()
        result = engine.match_skills(["Next.js", "TypeScript"], ["React", "Node.js", "Python"])
    """

    def __init__(self):
        graph = _load_graph()
        self._skills: Dict[str, Dict] = graph['skills']
        self._alias_to_key: Dict[str, str] = graph['alias_to_key']
        self._domains: Dict[str, Dict] = graph['domains']

        # Pre-build reverse implies index:
        # If skill A implies skill B, then _reverse_implies[B] contains A.
        self._reverse_implies: Dict[str, Set[str]] = {}
        for key, entry in self._skills.items():
            for implied in entry.get('implies', []):
                self._reverse_implies.setdefault(implied, set()).add(key)

        # Pre-build reverse related index
        self._reverse_related: Dict[str, Set[str]] = {}
        for key, entry in self._skills.items():
            for related in entry.get('related', []):
                self._reverse_related.setdefault(related, set()).add(key)

    def _resolve_to_graph_key(self, skill: str) -> Optional[str]:
        """Resolve a skill string to its graph key, trying multiple strategies."""
        # Strategy 1: Direct alias lookup after normalization
        norm = _normalize(skill)
        key = self._alias_to_key.get(norm)
        if key:
            return key

        # Strategy 2: Graph-key normalization (underscore-based)
        graph_key = _normalize_for_graph(skill)
        if graph_key in self._skills:
            return graph_key

        # Strategy 3: Try alias lookup with graph-key form
        key = self._alias_to_key.get(graph_key)
        if key:
            return key

        return None

    def match_skills(
        self,
        candidate_skills: List[str],
        jd_skills: List[str],
    ) -> InferenceResult:
        """Match candidate skills against JD skills using the full inference chain.

        For each JD skill, tries matching in order:
            1. Explicit match (candidate has exactly that skill)
            2. Alias match (candidate has an alias variant)
            3. Inference match (candidate has a skill that implies the JD skill)
            4. Related match (candidate has a related skill)

        Returns the best match found per JD skill.
        """
        result = InferenceResult()

        # Pre-resolve all candidate skills to graph keys
        candidate_graph_keys: Dict[str, str] = {}  # original → graph_key
        for cs in candidate_skills:
            gk = self._resolve_to_graph_key(cs)
            if gk:
                candidate_graph_keys[cs] = gk

        candidate_key_set = set(candidate_graph_keys.values())

        for jd_skill in jd_skills:
            match = self._best_match(jd_skill, candidate_skills, candidate_graph_keys, candidate_key_set)
            if match:
                result.all_matches.append(match)
                result.skill_weights[jd_skill] = match.weight

                if match.match_type == 'explicit':
                    result.explicit_skills.append(jd_skill)
                elif match.match_type == 'alias':
                    result.explicit_skills.append(jd_skill)  # Alias = same as explicit
                elif match.match_type == 'inferred':
                    result.inferred_skills.append(match)
                elif match.match_type == 'related':
                    result.related_skills.append(match)
            else:
                result.missing.append(jd_skill)
                result.skill_weights[jd_skill] = 0.0

        return result

    def _best_match(
        self,
        jd_skill: str,
        candidate_skills: List[str],
        candidate_graph_keys: Dict[str, str],
        candidate_key_set: Set[str],
    ) -> Optional[SkillMatchResult]:
        """Find the best match for a single JD skill across all candidate skills."""

        jd_display = jd_skill  # Preserve original for display

        # ── 1. Explicit match ──
        for cs in candidate_skills:
            if _alias_match(cs, jd_skill):
                return SkillMatchResult(
                    skill=jd_display,
                    source=cs,
                    match_type='explicit',
                    weight=WEIGHT_EXPLICIT,
                    explanation=f"{jd_display} ✓ matched directly",
                )

        # ── 2. Graph-based alias match ──
        jd_key = self._resolve_to_graph_key(jd_skill)
        if jd_key:
            for cs, cs_key in candidate_graph_keys.items():
                if cs_key == jd_key:
                    return SkillMatchResult(
                        skill=jd_display,
                        source=cs,
                        match_type='alias',
                        weight=WEIGHT_ALIAS,
                        explanation=f"{jd_display} ✓ alias of {cs}",
                    )

        # ── 3. Inference match (candidate has skill that implies JD skill) ──
        if jd_key:
            # Who implies jd_key?
            impliers = self._reverse_implies.get(jd_key, set())
            for cs, cs_key in candidate_graph_keys.items():
                if cs_key in impliers:
                    cs_display = self._skills.get(cs_key, {}).get('display', cs)
                    return SkillMatchResult(
                        skill=jd_display,
                        source=cs,
                        match_type='inferred',
                        weight=WEIGHT_INFERRED,
                        explanation=f"{jd_display} ← inferred from {cs_display}",
                    )

            # Also check: does the candidate have a skill whose implies list
            # contains the JD skill? (forward direction)
            for cs, cs_key in candidate_graph_keys.items():
                cs_entry = self._skills.get(cs_key, {})
                if jd_key in cs_entry.get('implies', []):
                    cs_display = cs_entry.get('display', cs)
                    return SkillMatchResult(
                        skill=jd_display,
                        source=cs,
                        match_type='inferred',
                        weight=WEIGHT_INFERRED,
                        explanation=f"{jd_display} ← inferred from {cs_display}",
                    )

        # ── 4. Related match ──
        if jd_key:
            # Who is related to jd_key?
            related = self._reverse_related.get(jd_key, set())
            jd_entry = self._skills.get(jd_key, {})
            jd_related = set(jd_entry.get('related', []))
            all_related = related | jd_related

            for cs, cs_key in candidate_graph_keys.items():
                if cs_key in all_related:
                    cs_display = self._skills.get(cs_key, {}).get('display', cs)
                    return SkillMatchResult(
                        skill=jd_display,
                        source=cs,
                        match_type='related',
                        weight=WEIGHT_RELATED,
                        explanation=f"{jd_display} ~ related to {cs_display}",
                    )

        return None

    def get_skill_domain(self, skill: str) -> Optional[str]:
        """Get the domain for a skill."""
        key = self._resolve_to_graph_key(skill)
        if key and key in self._skills:
            return self._skills[key].get('domain')
        return None

    def get_skill_display(self, skill: str) -> str:
        """Get the display name for a skill."""
        key = self._resolve_to_graph_key(skill)
        if key and key in self._skills:
            return self._skills[key].get('display', skill)
        return skill
