# 06 — Skill Inference Engine

## Overview

The Skill Inference Engine uses a graph-based approach to match candidate skills against JD requirements, going beyond exact string matching to handle cases where a candidate's skills *imply* or are *related to* a required skill.

**Entry point:** `SkillInferenceEngine.match_skills(candidate_skills, jd_skills)` in `src/ranking/skill_inference.py`

**Graph data:** `src/registries/skill_graph.json` (~80KB, 200+ skill nodes)

---

## Match Hierarchy

The engine assigns weights to skill matches based on their type. Higher weight = stronger match evidence.

| Match Type | Weight | Example | Meaning |
|-----------|--------|---------|---------|
| **Explicit** | 1.00 | Candidate has "React", JD requires "React" | Direct match |
| **Alias** | 1.00 | Candidate has "ReactJS", JD requires "React" | Same canonical skill |
| **Inferred** | 0.75 | Candidate has "Next.js", JD requires "React" | Next.js *implies* React |
| **Related** | 0.50 | Candidate has "Angular", JD requires "React" | Angular is *related to* React |
| **Domain** | 0.25 | (Reserved, not actively used in matching) | Same domain affinity |
| **Missing** | 0.00 | Candidate lacks any match for the JD skill | No match found |

---

## Skill Graph Structure

```json
{
  "skills": {
    "nextjs": {
      "display": "Next.js",
      "aliases": ["next.js", "next"],
      "domain": "engineering",
      "implies": ["reactjs", "nodejs", "javascript"],
      "related": ["gatsby", "nuxtjs", "vuejs"]
    },
    "reactjs": {
      "display": "React",
      "aliases": ["react", "react.js", "reactjs"],
      "domain": "engineering",
      "implies": ["javascript"],
      "related": ["angular", "vuejs", "svelte"]
    }
  },
  "domains": {
    "engineering": { ... },
    "healthcare": { ... }
  }
}
```

### Edge Types

| Edge | Direction | Meaning |
|------|-----------|---------|
| `implies` | Forward | "If you know A, you implicitly know B" |
| `related` | Bidirectional | "A and B are in the same technology family" |
| `aliases` | Canonical | "These are all names for the same skill" |

---

## Resolution Algorithm

For each JD skill, the engine tries matching in priority order:

```
1. EXPLICIT: Does any candidate skill match via alias-aware matching?
   → weight = 1.00

2. GRAPH ALIAS: Do the candidate and JD skill resolve to the same graph key?
   → weight = 1.00

3. INFERENCE (reverse): Does any candidate skill imply the JD skill?
   Example: Candidate has "Next.js", JD wants "React"
   → skill_graph["nextjs"]["implies"] contains "reactjs"
   → weight = 0.75

4. INFERENCE (forward): Does any candidate skill's implies list contain the JD skill?
   (Checks both directions of the implies relationship)
   → weight = 0.75

5. RELATED: Does any candidate skill appear in the JD skill's related list, or vice versa?
   → weight = 0.50

6. MISSING: No match found
   → weight = 0.00
```

### Key Implementation Detail: Pre-built Reverse Indices

The engine builds reverse lookup indices at initialization time for O(1) edge traversal:

```python
# _reverse_implies[B] = {A1, A2, ...} where A1 implies B, A2 implies B
# _reverse_related[B] = {A1, A2, ...} where A1 is related to B
```

---

## Integration Points

### Phase 1: Knockout (scorer.py)

Inferred skills with weight ≥ 0.75 can **satisfy must-have requirements**, preventing false knockouts. Related skills (0.50) do **not** satisfy must-have requirements.

```python
# Example: JD requires "React"
# Candidate has "Next.js" (implies React at 0.75)
# → Must-have check PASSES (0.75 ≥ 0.75)
```

### Phase 2: BM25 Scoring (bm25_scorer.py)

Inference weights are passed as `skill_weights` to BM25, replacing binary 1/0 term frequency with fractional values:

```python
tf_val = skill_weights.get(jd_skill, 0.0)  # 0.75 for inferred, 0.50 for related
```

This gives inferred skills partial credit in the BM25 formula rather than full-or-nothing.

### Skill Augmentation (scorer.py)

Before running inference, the scorer augments the candidate's skill list by searching skill-bearing text sections for JD skill variants:

```python
for jd_sk in all_jd_skills:
    if not found_in_structured_skills:
        variants = get_search_variants(jd_sk)
        if any_variant_found_in_skill_sections:
            augmented_skills.append(jd_sk)
```

This catches skills mentioned in experience descriptions or project descriptions but not in the structured skills list.

---

## Output

```python
@dataclass
class InferenceResult:
    explicit_skills: List[str]           # JD skills matched explicitly
    inferred_skills: List[SkillMatchResult]  # JD skills matched via inference
    related_skills: List[SkillMatchResult]   # JD skills matched via related
    all_matches: List[SkillMatchResult]      # All matches combined
    missing: List[str]                       # JD skills with no match
    skill_weights: Dict[str, float]          # jd_skill → best weight found
```

```python
@dataclass
class SkillMatchResult:
    skill: str          # "React" (the JD skill)
    source: str         # "Next.js" (what resume skill triggered it)
    match_type: str     # "explicit" | "alias" | "inferred" | "related"
    weight: float       # 1.00 | 0.75 | 0.50
    explanation: str    # "React ← inferred from Next.js"
```

The `explanation` field is human-readable and displayed in the frontend's skill breakdown panel.
