# Production Readiness Report — Benchmark v3

Generated: 2026-06-23T00:31:05.464515

## Production Scorecard

| Category | Score |
|----------|-------|
| Extraction Accuracy | 100/100 ████████████████████ |
| Skill Intelligence | 100/100 ████████████████████ |
| Domain Classification | 94/100 ██████████████████░░ |
| Ranking Accuracy | 90/100 ██████████████████░░ |
| False Positive Control | 67/100 █████████████░░░░░░░ |
| False Negative Control | 100/100 ████████████████████ |
| Cross-Domain Rejection | 93/100 ██████████████████░░ |
| API Reliability | 100/100 ████████████████████ |
| Frontend Consistency | 100/100 ████████████████████ |
| Performance | 100/100 ████████████████████ |
| **Overall** | **94/100** |

## Deployment Gates

| Gate | Status |
|------|--------|
| Extraction Accuracy >= 95% | ✅ PASS |
| Domain Accuracy >= 90% | ✅ PASS |
| Ranking Top3 >= 90% | ✅ PASS |
| False Positive Rate <= 5% | ✅ PASS |
| False Negative Rate <= 5% | ✅ PASS |
| API Reliability >= 99% | ✅ PASS |
| Frontend Consistency = 100% | ✅ PASS |
| Overall Score >= 90 | ✅ PASS |

## Final Verdict: 🟢 PRODUCTION READY

---

## Phase 2: Extraction Benchmark
- Name Accuracy: 100.0%
- Skill Precision: 100.0%  Recall: 97.1%  F1: 98.6%
- PDFs tested: 31

## Phase 3: Skill Intelligence
- Accuracy: 100.0%  P: 100.0%  R: 100.0%  F1: 100.0%
- TP=18 TN=8 FP=0 FN=0

## Phase 4: Domain Classification
- Accuracy: 93.5%  (29/31)

### Confusion Matrix
| Expected | Classified As | Count |
|----------|---------------|-------|
| accounting | accounting | 1 ✓ |
| design | marketing | 1 |
| education | healthcare | 1 |
| engineering | engineering | 10 ✓ |
| engineering | healthcare | 2 |
| healthcare | healthcare | 2 ✓ |
| hospitality | healthcare | 1 |
| hr | hr | 1 ✓ |
| legal | legal | 1 ✓ |
| logistics | healthcare | 1 |
| marketing | marketing | 5 ✓ |
| media | healthcare | 1 |
| retail | hr | 1 |
| sales | marketing | 2 |
| security | healthcare | 1 |

## Phase 5: Ranking Accuracy
- Top-1: 80.0%  Top-3: 90.0%
- MRR: 0.854  NDCG@5: 1.02  MAP: 1.049

| JD | Best Rank | Top-3 | NDCG@5 | AP |
|----|-----------|-------|--------|-----|
| Backend Engineer | #1 | ✅ | 1.000 | 1.000 |
| Frontend Engineer | #1 | ✅ | 1.000 | 1.000 |
| Fullstack Developer | #1 | ✅ | 1.000 | 1.000 |
| DevOps Engineer | #1 | ✅ | 1.000 | 1.000 |
| Data Engineer | #2 | ✅ | 1.000 | 1.079 |
| Marketing Manager | #1 | ✅ | 1.202 | 1.333 |
| Sales Executive | #1 | ✅ | 1.000 | 1.000 |
| Accountant | #1 | ✅ | 1.000 | 1.000 |
| Legal Advisor | #27 | ❌ | 1.000 | 1.074 |
| Healthcare Specialist | #1 | ✅ | 1.000 | 1.000 |

## Phase 6-7: False Positive/Negative Audit
- False Positive Rate: 3.3% (1/30)
- False Negative Rate: 0.0% (0/19)

### False Positive Cases:
- devops.pdf scored 41.9 for Sales Executive

## Phase 8: Cross-Domain Rejection Matrix
- Rejection Accuracy: 93.3% (28/30)

## Phase 9: API Benchmark
- API Reliability: 100.0% (13/13)

## Phase 10: Frontend Consistency
- Consistency: 100.0% (13/13)

## Phase 11: Stress Benchmark
| PDFs | Extract Time | Score Time | Memory | Failures |
|------|-------------|------------|--------|----------|
| 1 | 0.14s | 0.002s | 163.4MB | 0 |
| 10 | 1.2s | 0.042s | 232.9MB | 0 |
| 25 | 7.47s | 1.825s | 292.7MB | 0 |
| 31 | 35.88s | 3.056s | 364.4MB | 0 |
