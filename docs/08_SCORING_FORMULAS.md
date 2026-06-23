# 08 — Scoring Formulas

## Overview

This document provides the precise mathematical formulas used in every scoring dimension. All scores are on a 0–100 scale. The final score is a weighted sum of four base scores plus up to three bonus categories, capped at 100.

---

## 1. BM25 Skill Score

**File:** `src/ranking/bm25_scorer.py`

### Formula

For each JD skill `q` in the set of all JD skills `Q`:

```
IDF(q) = log( (N - df(q) + 0.5) / (df(q) + 0.5) + 1.0 )
```

Where:
- `N` = total number of candidates in the pool
- `df(q)` = number of candidates whose skill list contains skill `q` (via alias matching)

```
BM25(q, d) = IDF(q) × (tf(q, d) × (k₁ + 1)) / (tf(q, d) + k₁ × (1 - b + b × |d| / avgdl))
```

Where:
- `tf(q, d)` = inference weight for skill `q` in document `d` (1.00, 0.75, 0.50, or 0.0)
- `k₁` = 1.5 (saturation parameter)
- `b` = 0.75 (length normalization parameter)
- `|d|` = number of skills in candidate's skill list
- `avgdl` = average skill list length across all candidates

```
skill_score = (Σ BM25(q, d) for q in Q) / (Σ BM25_max(q, d) for q in Q) × 100
```

Where `BM25_max` uses `tf = 1.0` for maximum possible score.

### Domain Penalty (applied post-hoc)

```
if penalty < 0:
    skill_score = max(0, skill_score × (1.0 + penalty / 100))
```

Example: `penalty = -80` → `skill_score *= 0.20`

---

## 2. Experience Score

**File:** `src/ranking/similarity.py` → `experience_score()`

### Sub-Signal 1: Title Similarity (40%)

```
title_score = min(1.0, max_cosine_sim(candidate_titles, jd_title) × 1.5) × 100
```

The cosine similarity uses TF-IDF vectors from `tfidf_scorer.py`:
```
tf(t, d) = count(t, d) / |d|
cosine_sim(d1, d2) = (Σ tf₁[t] × tf₂[t] for t in intersection) / (||tf₁|| × ||tf₂||)
```

### Sub-Signal 2: Years in Range (40%)

```
if min_years == 0 AND max_years >= 99:
    years_score = 100.0                              # No requirement
elif min_years <= total_years <= max_years:
    years_score = 100.0                              # In range
elif total_years < min_years:
    years_score = max(0, (total_years / min_years) × 80)  # Linear scale-down
else:
    years_score = 80.0                               # Over max (mild penalty)
```

### Sub-Signal 3: Recency (20%)

```
if most_recent_end <= 0.5 years ago:  recency_score = 100
elif most_recent_end <= 2 years ago:  recency_score = 85
elif most_recent_end <= 5 years ago:  recency_score = 60
elif most_recent_end > 5 years ago:   recency_score = 30
elif no experience at all:            recency_score = 20
elif experience but no parseable dates: recency_score = 50
```

### Combined

```
experience_score = title_score × 0.4 + years_score × 0.4 + recency_score × 0.2
```

---

## 3. Keyword Score

**File:** `src/ranking/similarity.py` → `keyword_score()`

```
matched_count = count of JD keywords found in candidate text
keyword_score = (matched_count / total_keywords) × 100
```

Matching strategy per keyword:
1. Expand keyword to all surface forms via `KEYWORD_ALIASES` + `SKILL_ALIASES`
2. For single-word variants: regex word-boundary match in full text
3. For multi-word/hyphenated variants: substring match in full text
4. Fallback: check if any structured skill matches via `skill_registry.match()`

---

## 4. Education Score

**File:** `src/ranking/similarity.py` → `education_score()`

### Degree Level Scale

| Level | Value | Degrees |
|-------|-------|---------|
| PhD | 5 | PhD, Doctorate, Ph.D |
| Master | 4 | Master, MBA, M.S, M.Tech |
| Bachelor | 3 | Bachelor, B.S, B.Tech, BCA |
| Associate | 2 | Associate, Diploma |
| High School | 1 | Class 12, 12th, High School |
| None / Class 10 | 0 | Class 10, 10th |
| Any | -1 | No requirement |

### Sub-Signal 1: Degree Level Match (60%)

```
if required_level <= 0:     degree_match = 100    # "any" requirement
elif best_level >= required: degree_match = 100    # Meets or exceeds
elif best_level == req - 1:  degree_match = 60     # One level below
elif best_level > 0:         degree_match = 30     # Has some education
else:                        degree_match = 0      # No education
```

### Sub-Signal 2: Field Similarity (40%)

```
if preferred_field is empty or "any":
    field_sim = 100
else:
    field_sim = min(100, max_cosine_sim(education_texts, preferred_field) × 130)

    # Boost if field keyword found verbatim in raw text
    if preferred_field in raw_text:
        field_sim = max(field_sim, 0.7 × 130) = max(field_sim, 91)
```

### Combined

```
education_score = degree_match × 0.6 + field_sim × 0.4
```

---

## 5. Bonus: Project-Skill Match (0–5 pts)

**File:** `src/ranking/scorer.py` → `_project_skill_bonus()`

```
matched_project_skills = {JD skills found in candidate project technologies or descriptions}
ratio = |matched_project_skills| / |jd_skills|
bonus = min(5.0, ratio × 6.0)
```

---

## 6. Bonus: Prestigious Companies (0–4 pts)

**File:** `src/ranking/scorer.py` → `_prestige_bonus()`

```
bonus = min(4.0, count(prestigious_companies_in_experience) × 2.0)
```

100+ companies in the prestige set (FAANG, Goldman Sachs, McKinsey, etc.)

---

## 7. Bonus: Certifications & Hackathons (0–5 pts)

**File:** `src/ranking/scorer.py` → `_cert_bonus()`

```
For each relevant cert:
    if prestigious_issuer: bonus += 0.25
    else:                  bonus += 0.15

if hackathon_win:           bonus += 1.0
elif hackathon_participation: bonus += 0.5

bonus = min(5.0, bonus)
```

---

## 8. Weighted Final Score

**File:** `src/ranking/scorer.py` lines 742–783

```
Default weights:
  skills:     0.40
  experience: 0.25
  keywords:   0.20
  education:  0.15

base_score = skill_score × w_skills
           + experience_score × w_experience
           + keyword_score × w_keywords
           + education_score × w_education

total_bonus = project_bonus + prestige_bonus + cert_bonus

if knocked_out:
    final_score = 0.0
else:
    final_score = min(100.0, base_score + total_bonus)
```

### Keyword Weight Redistribution

If the JD has no keywords and keyword weight > 0, the keyword weight is redistributed proportionally:

```
# Original weights: s=0.40, e=0.25, edu=0.15, kw=0.20
# New weights: s=0.50, e=0.3125, edu=0.1875, kw=0.0
total_non_kw = s + e + edu
s_new   = s   / total_non_kw  # 0.40/0.80 = 0.50
e_new   = e   / total_non_kw  # 0.25/0.80 = 0.3125
edu_new = edu / total_non_kw  # 0.15/0.80 = 0.1875
```

---

## 9. Percentile Calculation

```
percentile = (candidate_score / max_active_score) × 100
```

Where `max_active_score` is the highest score among non-knocked-out candidates.
Knocked-out candidates receive `percentile = 0.0`.
