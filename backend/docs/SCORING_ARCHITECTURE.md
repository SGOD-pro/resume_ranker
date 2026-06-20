# Scoring Architecture

## Overview

The scoring engine evaluates candidates against a job description (JD) using a **3-phase pipeline**:

```
Phase 1: Hard Knockout → Phase 2: Multi-Signal Scoring → Phase 3: Rank & Explain
```

## Phase 1: Hard Knockout

Candidates are eliminated if they fail any of these checks:

| Check | Condition | Leniency |
|-------|-----------|----------|
| Must-have skills | Missing after structured + raw text search | Second-chance raw text scan |
| Minimum years | Below `min_years` threshold | Waived if ≥2 job entries or raw text mentions years |
| Required degree | Below degree level | Also checks raw text for degree mentions |

## Phase 2: Multi-Signal Scoring (0–100 per dimension)

Four weighted scoring dimensions:

| Dimension | Default Weight | Algorithm | Module |
|-----------|---------------|-----------|--------|
| Skills | 40% | BM25 (IDF-weighted) | `src/ranking/bm25_scorer.py` |
| Experience | 25% | Title similarity + Years + Recency | `src/ranking/similarity.py` |
| Keywords | 20% | JD keyword presence | `src/ranking/similarity.py` |
| Education | 15% | Degree level + Field match | `src/ranking/similarity.py` |

### BM25 Skill Scoring

Uses Inverse Document Frequency across all candidates to reward rare skill matches:

```
IDF(skill) = log((N - df + 0.5) / (df + 0.5) + 1.0)
```

Where `N` = total candidates, `df` = candidates who have this skill.

Skills are matched using the centralized **skill registry** (`src/registries/skill_registry.py`) which handles:
- 90+ aliases (k8s → Kubernetes, js → JavaScript, etc.)
- Normalization (React.js → reactjs)
- Substring matching for 3+ char skills
- Safe single-char handling (R, C)

### TF-IDF Text Similarity

Used by experience scoring (title similarity) and education scoring (field match):

```
cos(A, B) = (A · B) / (||A|| × ||B||)
```

Implementation: `src/ranking/tfidf_scorer.py` — zero external dependencies.

## Phase 3: Rank & Explain

### Bonus Scoring (capped at 100 total)

| Bonus | Range | Source |
|-------|-------|--------|
| Project-skill match | 0–5.0 | Projects using JD technologies |
| Prestigious company | 0–4.0 | 100+ recognized companies |
| Certifications | 0–5.0 | Domain-relevant certs + hackathons |

### Ranking

1. Sort by `final_score` descending (knocked-out → bottom)
2. Assign 1-based ranks
3. Compute percentiles among non-knocked-out candidates
4. Flag anomalies (fresher, overqualified, employment gap, low quality)

## Weight Configuration

Weights are **tunable per JD** via `JobDescription.weights`:

```python
# Fresher-friendly JD
weights = {"skills": 0.50, "experience": 0.10, "keywords": 0.25, "education": 0.15}

# Senior management role
weights = {"skills": 0.30, "experience": 0.35, "keywords": 0.20, "education": 0.15}
```

## Module Map

```
scorer.py                          → CandidateScorer class (orchestrator)
src/schemas/scoring.py             → JobDescription, ScoredCandidate dataclasses
src/registries/skill_registry.py   → Skill aliases, normalization, matching
src/ranking/bm25_scorer.py         → BM25 skill scoring algorithm
src/ranking/tfidf_scorer.py        → TF-IDF cosine similarity
src/ranking/similarity.py          → Experience, keyword, education scoring
```

## Adding a New Scoring Signal

1. **Create the scoring function** in `src/ranking/` (return 0–100 float)
2. **Add a weight key** to `JobDescription.weights` default factory
3. **Add a bonus/score field** to `ScoredCandidate`
4. **Call from `CandidateScorer._score_candidate()`** in `scorer.py`
5. **Include in weighted total** or as a bonus (capped at 100)
