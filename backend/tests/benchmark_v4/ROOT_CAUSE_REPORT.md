# Phase 0 — Root Cause Report

Generated: 2026-06-23
Version: v7-phase0

---

## Step 0.1: JD Keyword Audit

| JD | Must-Have | Nice | KW Count | Weights (s/e/k/d) |
|----|-----------|------|----------|-------------------|
| Backend Engineer | 0 | 10 | 7 | 0.40/0.25/0.20/0.15 |
| Frontend Engineer | 0 | 10 | 6 | 0.45/0.20/0.20/0.15 |
| Fullstack Engineer | 0 | 9 | 6 | 0.40/0.25/0.20/0.15 |
| DevOps Engineer | 0 | 9 | 6 | 0.40/0.25/0.20/0.15 |
| Data Engineer | 0 | 9 | 6 | 0.40/0.25/0.20/0.15 |
| Data Scientist | 0 | 8 | 6 | 0.40/0.20/0.25/0.15 |
| ML Engineer | 0 | 8 | 6 | 0.40/0.20/0.25/0.15 |
| Marketing Manager | 0 | 7 | 7 | 0.35/0.30/0.20/0.15 |
| Sales Executive | 0 | 5 | 6 | 0.30/0.35/0.20/0.15 |
| HR Manager | 0 | 6 | 6 | 0.30/0.30/0.25/0.15 |
| Accountant | 0 | 7 | 6 | 0.35/0.30/0.20/0.15 |
| Civil Engineer | 0 | 7 | 7 | 0.35/0.30/0.20/0.15 |
| Electrical Engineer | 0 | 7 | 7 | 0.35/0.30/0.20/0.15 |
| Mechanical Engineer | 0 | 7 | 7 | 0.35/0.30/0.20/0.15 |
| Legal Advisor | 0 | 5 | 6 | 0.30/0.30/0.25/0.15 |
| Healthcare Specialist | 0 | 6 | 6 | 0.30/0.30/0.25/0.15 |
| Teacher | 0 | 4 | 6 | 0.30/0.30/0.25/0.15 |
| Hotel Manager | 0 | 4 | 6 | 0.30/0.30/0.25/0.15 |
| Construction Manager | 0 | 4 | 6 | 0.30/0.30/0.25/0.15 |
| Office Admin | 0 | 4 | 5 | 0.30/0.30/0.25/0.15 |

**Result**: 0 JDs with empty keywords. All 20 JDs have 5-7 keywords.

---

## Step 0.2: Full Score Decomposition — Accountant JD (200 PDF sample)

Real CandidateScorer output (top 10):

| Rank | Name | Skill | Exp | KW | Edu | DomPen | Final | Nice-Matched |
|------|------|-------|-----|------|------|--------|-------|-------------|
| 1 | V.P.O. Nangal Bhur | 69.2 | 44.0 | 50.0 | 96.4 | 0.0 | 61.9 | GAAP,Tax,Audit,Excel,SAP,QB |
| 2 | FAIZAN ALI | 37.1 | 44.0 | 66.7 | 96.4 | 0.0 | 54.0 | GAAP,Excel,SAP,QuickBooks |
| 3 | Mail Id | 44.9 | 44.0 | 50.0 | 96.4 | 0.0 | 53.4 | GAAP,Audit,SAP,QuickBooks |
| 4 | IT CONSULTANT | 43.1 | 46.0 | 50.0 | 96.4 | 0.0 | 53.4 | GAAP,IFRS,Audit,SAP,QB |
| 5 | Unknown Candidate | 30.0 | 50.0 | 66.7 | 96.4 | -50.0 | 53.3 | GAAP,IFRS,Audit,SAP,QB |

**Key observation**: Education score = 96.4 for almost everyone, creating near-constant noise floor.

---

## Step 0.3: Hypothesis — "Empty keywords produce keyword_score=100"

### Evidence

File: `src/ranking/similarity.py`, lines 171-172:
```python
if not jd.keywords:
    return 100.0, [], []
```

### Verdict: **CONFIRMED — Latent Bug**

If `jd.keywords` is empty, `keyword_score = 100.0` (perfect).

**However**: No current benchmark JD has empty keywords (Step 0.1). So this bug does NOT affect v6 results. It IS a production risk for user-created JDs.

---

## Step 0.4: Score Saturation Investigation

### Benchmark Formula (NOT production scorer)

```python
# Phase 4 ranking formula (tests/benchmark_v4/main.py, line 675)
approx = skill_score * 0.5 + domain_bonus + exp_bonus
```

Where:
- `domain_bonus` ∈ {0, 5, 10, 20, 25} — 5 discrete values
- `exp_bonus = min(exp_count * 5, 20)` — caps at 20 for 4+ entries → 5 values
- `skill_score * 0.5 = (matched/total) * 50` — discrete steps

### Saturation Evidence (all 20 JDs)

| JD | Score Range | Unique Scores | Max Tie | Stdev | Flags |
|----|------------|---------------|---------|-------|-------|
| Backend Engineer | 60.0-50.0 | 3 | 10 | 3.6 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |
| Data Scientist | 66.2-56.2 | 4 | 10 | 3.5 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |
| Hotel Manager | 45.0-35.0 | 4 | 16 | 2.1 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |
| Office Admin | 52.5-42.5 | 4 | 11 | 4.2 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |
| Electrical Engineer | 37.1-30.0 | 3 | 12 | 2.2 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |
| HR Manager | 50.0-41.7 | 5 | 10 | 3.0 | LOW_DIVERSITY, HEAVY_TIES, LOW_SPREAD |

**17/20 JDs have HEAVY_TIES (max_tie ≥ 5)**
**10/20 JDs have LOW_SPREAD (stdev < 5)**
**7/20 JDs have LOW_DIVERSITY (unique scores ≤ 5)**

### Root Cause: **Benchmark formula, NOT production scorer**

The benchmark Phase 4 uses `phase4_ranking()` which computes a lightweight `approx` score:
```
approx = skill_score * 0.5 + domain_bonus + exp_bonus
```

This has **3 coarse dimensions** with ~125 possible score combinations.

The **production CandidateScorer** uses **7+ dimensions**:
- skill_score × weight
- experience_score × weight
- keyword_score × weight
- education_score × weight
- domain_penalty
- project_bonus
- prestige_bonus
- cert_bonus

Real scorer results (Accountant JD sample) showed much better differentiation:
- Scores ranged 27.3–61.9 (vs 39.3–54.3 in benchmark)
- Stdev ~9 (vs 5.5 in benchmark)

### Verdict: **Score saturation is a BENCHMARK artifact, not a product bug.**

---

## Step 0.5: Zero-Skill Candidates

### Real Scorer (Accountant JD, 200 PDF sample)
- 18/200 candidates have `skill_score=0` AND `final_score > 25`
- These score via: `experience_score(~50) + keyword_score(~17) + education_score(~60)` = ~27

### Breakdown of a typical zero-skill candidate:
```
name=Unknown Candidate
skill=0.0  exp=50.0  kw=33.3  edu=60.0
weighted: s=0.0  e=15.0  k=6.7  d=9.0 → final=31.0
matched_kw=['financial', 'audit']  domain=sales  penalty=0.0
```

### Root Cause: **Experience + Education overweight when skill=0**

When `skill_score=0`:
- `exp_score` alone contributes up to 50 × 0.30 = 15 points
- `edu_score` contributes up to 96.4 × 0.15 = 14.5 points  
- `kw_score` contributes up to 100 × 0.20 = 20 points

Combined: up to 49.5 points with ZERO skill match.

### Verdict: **This is expected behavior** (experience/education have value even without exact skill matches), BUT it should be:
1. Flagged explicitly in rankings ("0 skill matches")
2. Capped — a candidate with 0/7 skill matches should NOT outrank one with 3/7

---

## Summary of Findings

| # | Finding | Status | Root Cause | Fix Required |
|---|---------|--------|-----------|:------------:|
| 1 | Empty keywords → 100.0 score | **Confirmed (latent)** | `similarity.py:171` | Yes (Phase 1) |
| 2 | Score saturation / heavy ties | **Confirmed** | Benchmark uses lightweight formula, not real scorer | Yes (Phase 10) |
| 3 | 0-skill candidates ranked high | **Confirmed** | exp+edu overweight when skill=0 | Evaluate |
| 4 | Benchmark ≠ production scorer | **Confirmed** | `phase4_ranking()` uses `approx` formula | Yes (Phase 10) |
| 5 | Empty keyword JDs in benchmark | **Disproven** | All 20 JDs have 5-7 keywords | No |

### Recommended Fix Priority

1. **Phase 10 (CRITICAL)**: Replace benchmark lightweight formula with real `CandidateScorer.rank()`
2. **Phase 1**: Fix empty keyword → 100.0 latent bug in production 
3. **Phase 2**: Deduplicate benchmark corpus before ranking
4. **Phase 5**: Name extraction hardening
5. **Evaluate**: Whether 0-skill floor should be implemented in scorer
