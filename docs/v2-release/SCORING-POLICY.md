# SWYRA Sortlist v2 — Scoring Policy

This is the BINDING scoring policy for the v2 release. It replaces all previous scoring documentation.

## Principles
1. Scores are RELEVANCE scores, not hiring recommendations
2. Every score is transparent, deterministic, and explainable
3. No score is presented as a hiring decision
4. Human reviewer always owns shortlist/reject decisions

## Score Structure
- **Score version**: Incremented when formula changes
- **Policy version**: Incremented when allowed inputs change  
- **Job version**: Incremented when job criteria change
- All three are stored with every score snapshot

## Allowed Inputs (Exhaustive List)
| Input | Source | Notes |
|-------|--------|-------|
| Must-have skills | Job criteria | Explicit match, alias match, graph-inferred (weight 0.75), graph-related (weight 0.50) |
| Nice-to-have skills | Job criteria | Bonus only, never penalty |
| Min/max years of experience | Job criteria | Parsed from candidate dates |
| Required degree level | Job criteria | PhD(5), Masters(4), Bachelors(3), Associate(2), HighSchool(1), Any(-1) |
| Preferred field of study | Job criteria | Cosine similarity |
| Keywords | Job criteria | Presence/absence ratio |
| Role title similarity | Job criteria + candidate experience | TF-IDF cosine |
| Recency of experience | Candidate dates | Time since most recent role |
| Job-relevant project skills | Candidate projects | Matched against JD skills |
| Relevant certifications | Candidate certs | Must be job-relevant |

## PROHIBITED Inputs (Non-Negotiable)
The following MUST NEVER influence ranking:
- Age, date of birth, gender, race, caste, religion, nationality, disability, marital status
- Photo, address, or location-based proxies
- Name-based proxies (e.g., inferring ethnicity from name)
- University prestige (all accredited degrees are equal)
- Employer prestige / FAANG bonus (all employers are equal)
- Career gaps (gaps are not scored or penalized)
- Inferred "culture fit"
- Hackathon participation/wins (unless job explicitly requires it)

## Component Scores (0-100 each)
1. **Skill Score**: BM25 with inference weights. Domain penalty from proximity matrix.
2. **Experience Score**: 40% role title cosine + 40% years in range + 20% recency
3. **Keyword Score**: matched/total ratio × 100
4. **Education Score**: 60% degree level match + 40% field cosine similarity

## Composite Score
```
base_score = skill_w × skill_score + exp_w × experience_score + kw_w × keyword_score + edu_w × education_score
project_bonus = min(5.0, matched_project_skills / total_jd_skills × 6.0)
cert_bonus = sum(relevant_cert_scores), capped at 5.0
final_score = min(100.0, base_score + project_bonus + cert_bonus)
```

Default weights: Skills 40%, Experience 25%, Keywords 20%, Education 15%
Weights are configurable per job. Must sum to 100.

## Knockout Rules (Phase 1)
Candidates are marked as knocked out (NOT auto-rejected) when:
- Missing must-have skills with progressive penalty (1 missing: ×0.88, 2: ×0.765, 3: ×0.53, >3: ×0.0)
- Total parsed years below minimum (with lenient bypass for candidates with multiple experience entries)
- Total parsed years above maximum
- Required degree level not met
- Severe domain mismatch (confidence ≥ 0.35 and penalty ≤ -60)

Knocked-out candidates:
- Still have sub-scores calculated and stored for explainability
- Are moved to bottom of ranking
- Require human review to confirm rejection
- Are NEVER silently removed from the candidate list

## Removed Factors (v2)
The following factors from v1 are REMOVED:
- `_prestige_bonus()`: Hardcoded company prestige list — REMOVED
- `_cert_bonus()` prestigious issuer bonus: MIT/Stanford/Harvard/IIT bonus — REMOVED  
- Career gap anomaly flag as penalty — REMOVED (gap detection disabled)
- Hackathon bonus — REMOVED (not job-relevant unless explicitly required)
- Nice-to-have +10.0 per match — REDUCED to reasonable bonus

## Factor Ledger
Every score snapshot includes:
- `contribution`: Points contributed by each factor
- `source`: Where the evidence came from (field name, page number)
- `confidence`: Extraction confidence for this field
- `rule_version`: Which version of the scoring rule produced this

## Abstain / Review-Required
When extraction confidence is below 0.5, or insufficient evidence exists to score a component:
- Component score is marked as `ABSTAIN`
- Overall score shows `REVIEW_REQUIRED` state
- Human reviewer is prompted to verify extraction manually

## Reviewer Feedback
- Reviewers can override any score component with a mandatory reason
- Overrides are logged with timestamp, reviewer identity, original score, new score, and reason
- Overrides do not change the system score — they create a separate reviewer assessment
