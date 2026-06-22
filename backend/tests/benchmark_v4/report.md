# Benchmark v5 — Trustworthy Production Report
Generated: 2026-06-23T03:42:07.228247
Version: 5.0.0

## Production Readiness Scorecard

| Category | Score | Weight | Formula |
|----------|-------|--------|---------|
| Extraction Quality | 69/100 █████████████░░░░░░░ | 25% | — |
| Ranking Quality | 92/100 ██████████████████░░ | 20% | — |
| Knockout Reliability | 100/100 ████████████████████ | 15% | — |
| Domain Accuracy | 85/100 █████████████████░░░ | 15% | — |
| False Positive Control | 88/100 █████████████████░░░ | 10% | — |
| False Negative Control | 75/100 ███████████████░░░░░ | 10% | — |
| Performance | 100/100 ████████████████████ | 5% | — |
| **OVERALL** | **85/100** | **100%** | |

### Verdict: 🟡 BETA READY

### Metric Formulas (Phase 4 Audit)
- Extraction composite: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email = 68.7
- Ranking: 74 domain-matched in top-5 across 16 JDs = 74/(16×5)
- Knockout: 3/3
- Domain: (5076 - 761) / 5076 = 85.0%
- FP: 4 / (16 × 10) = 2.5%
- FN: 150 cases

---
## Phase 1 — Knockout Validation
**Passed: 3/3**

- ✅ **Has must-have + valid experience**: knocked_out=False (expected=False)
  - KO reasons: []
  - Matched must-have: ['Python'], Missing: []
  - Total years: 6.5
- ✅ **Missing must-have skill**: knocked_out=True (expected=True)
  - KO reasons: ['Missing must-have skills: Python']
  - Matched must-have: [], Missing: ['Python']
  - Total years: 6.5
- ✅ **Must-have via inference (Django→Python)**: knocked_out=False (expected=False)
  - KO reasons: []
  - Matched must-have: ['Python'], Missing: []
  - Total years: 6.5

---
## Phase 2 — Extraction Accuracy
- **Total PDFs**: 5076
- **Success Rate**: 100.0% (5076/5076)
- **Composite Score**: 68.7/100
- **Formula**: `0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email`

### Field Extraction Rates
| Field | Present | Rate | Formula | Avg Count |
|-------|---------|------|---------|-----------|
| name | 2601 | 51.2% | 2601/5076 | - |
| email | 3809 | 75.0% | 3809/5076 | - |
| phone | 3734 | 73.6% | 3734/5076 | - |
| skills | 4653 | 91.7% | 4653/5076 | 13.9 |
| experience | 2546 | 50.2% | 2546/5076 | 3.9 |
| education | 3929 | 77.4% | 3929/5076 | 2.0 |
| projects | 610 | 12.0% | 610/5076 | - |
| certs | 793 | 15.6% | 793/5076 | - |

### Name Precision Audit
- **Valid names**: 2601
- **Blank names**: 2475
- **Blacklisted names**: 1248
- **Name Precision**: 67.6%
- **Formula**: `2601/(2601+1248)`
- **Confidence distribution**: {'high': 2263, 'medium': 242, 'low': 96, 'zero': 2475}

### Anomalies
- Tag leaks: 4
- Skill duplicates: 12
- Low quality: 361

---
## Phase 2.5 — Deduplication Audit
- **Total PDFs**: 5076
- **Unique PDFs (by SHA256)**: 3856
- **Exact duplicates**: 1220 (1051 groups)
- **Near duplicates**: 156 (123 groups)
- **Dedup rate**: 27.1%

### Exact Duplicate Samples
- `21a975187145...`: cv (1).pdf, cv (4837).pdf
- `b47c741903a1...`: cv (10).pdf, cv (4843).pdf
- `6c83556835bc...`: cv (1054).pdf, cv (1055).pdf
- `d89c849c0d18...`: cv (11).pdf, cv (4844).pdf
- `745cac622eea...`: cv (1170).pdf, cv (1171).pdf
### Near Duplicate Samples
- `81285e886e96...`: cv (1002).pdf, cv (1393).pdf
- `8eafc303168f...`: cv (101).pdf, cv (181).pdf, cv (1843).pdf
- `4d4a626d75b8...`: cv (102).pdf, cv (388).pdf
- `b6aef17c9967...`: cv (104).pdf, cv (222).pdf, cv (372).pdf
- `fdf04b4ed281...`: cv (1045).pdf, cv (1046).pdf

---
## Phase 3 — Skill Intelligence
- **Accuracy**: 100.0%  **P**: 100.0%  **R**: 100.0%  **F1**: 100.0%
- TP=15  TN=4  FP=0  FN=0

---
## Phase 4 — Ranking Accuracy

### Backend Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 |  | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #2 |  | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #3 |  | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #4 |  | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #5 | ZOE THOMPSON | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #6 | MARCUS HALL | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #7 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #8 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #9 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #10 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #11 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #12 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #13 |  | 55.0 | engineering | software_engineering | 3/10 | 4 |
| #14 |  | 55.0 | engineering | software_engineering | 3/10 | 5 |
| #15 | Pavithra Shetty | 55.0 | engineering | software_engineering | 3/10 | 4 |
| #16 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #17 | John Smith | 50.0 | engineering | software_engineering | 4/10 | 2 |
| #18 |  | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #19 | Mashad Abbas | 50.0 | engineering | software_engineering | 2/10 | 23 |
| #20 |  | 50.0 | engineering | software_engineering | 2/10 | 7 |

### Frontend Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 65.0 | engineering | software_engineering | 6/10 | 3 |
| #2 | Harper Garcia | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #3 |  | 55.0 | engineering | software_engineering | 3/10 | 5 |
| #4 |  | 55.0 | engineering | software_engineering | 3/10 | 8 |
| #5 |  | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #6 | DANIEL GAN | 50.0 | engineering | civil_engineering | 6/10 | 2 |
| #7 | HARI KRISHNAN | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #8 |  | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #9 | Ramya. M | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #10 |  | 50.0 | engineering | software_engineering | 2/10 | 7 |
| #11 |  | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #12 |  | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #13 |  | 50.0 | engineering | software_engineering | 2/10 | 7 |
| #14 |  | 50.0 | engineering | software_engineering | 5/10 | 1 |
| #15 |  | 50.0 | engineering | software_engineering | 5/10 | 1 |
| #16 |  | 45.0 | engineering | software_engineering | 2/10 | 3 |
| #17 | Frederick Chen | 45.0 | engineering | software_engineering | 3/10 | 2 |
| #18 | Priya Elza | 45.0 | engineering | software_engineering | 3/10 | 2 |
| #19 |  | 45.0 | engineering | software_engineering | 3/10 | 2 |
| #20 |  | 45.0 | engineering | software_engineering | 2/10 | 3 |

### Fullstack Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #2 |  | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #3 | ZOE THOMPSON | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #4 |  | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #5 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #6 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #7 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #8 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #9 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #10 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #11 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #12 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #13 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #14 | VICTORIA BAKER | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #15 | Harper Garcia | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #16 |  | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #17 | Pavithra Shetty | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #18 |  | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #19 |  | 45.6 | engineering | software_engineering | 1/9 | 4 |
| #20 |  | 45.6 | engineering | software_engineering | 1/9 | 5 |

### DevOps Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | VICTORIA BAKER | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #2 |  | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #3 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #4 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #5 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #6 |  | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #7 |  | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #8 | Joseline | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #9 | Joseline | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #10 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #11 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #12 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #13 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #14 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #15 | ZOE THOMPSON | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #16 |  | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #17 | MARCUS HALL | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #18 |  | 45.6 | engineering | software_engineering | 1/9 | 4 |
| #19 | HARI KRISHNAN | 45.6 | engineering | software_engineering | 1/9 | 9 |
| #20 |  | 45.6 | engineering | software_engineering | 1/9 | 5 |

### Data Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 |  | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #2 |  | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #3 |  | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #4 |  | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #5 |  | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #6 |  | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #7 |  | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #8 | John Smith | 63.3 | engineering | software_engineering | 6/9 | 2 |
| #9 |  | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #10 |  | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #11 |  | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #12 | MARCUS HALL | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #13 |  | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #14 | Mashad Abbas | 51.1 | engineering | software_engineering | 2/9 | 23 |
| #15 |  | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #16 | Pavithra Shetty | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #17 |  | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #18 |  | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #19 | HARI KRISHNAN | 45.6 | engineering | software_engineering | 1/9 | 9 |
| #20 |  | 45.6 | engineering | software_engineering | 1/9 | 5 |

### Data Scientist
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 |  | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #2 |  | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #3 |  | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #4 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #5 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #6 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #7 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #8 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #9 |  | 58.8 | engineering | software_engineering | 3/8 | 5 |
| #10 | Pavithra Shetty | 58.8 | engineering | software_engineering | 3/8 | 4 |
| #11 | Chechnik | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #12 | Gruvil Technologies | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #13 | Chechnik | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #14 |  | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #15 | Joseline | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #16 |  | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #17 | Joseline | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #18 | Edison | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #19 | BLAKE MESTLY | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #20 | Gruvil Technologies | 56.2 | engineering | software_engineering | 5/8 | 1 |

### ML Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 |  | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #2 |  | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #3 | Joseline | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #4 |  | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #5 | Joseline | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #6 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #7 |  | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #8 | VICTORIA BAKER | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #9 |  | 53.8 | engineering | software_engineering | 3/8 | 3 |
| #10 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #11 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #12 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #13 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #14 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #15 |  | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #16 | MARCUS HALL | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #17 |  | 46.2 | engineering | software_engineering | 1/8 | 4 |
| #18 |  | 46.2 | engineering | software_engineering | 1/8 | 5 |
| #19 |  | 46.2 | engineering | software_engineering | 1/8 | 5 |
| #20 | Pavithra Shetty | 46.2 | engineering | software_engineering | 1/8 | 4 |

### Marketing Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | LIAM | 65.7 | marketing | marketing | 5/7 | 2 |
| #2 | Christopher Fowler | 63.6 | marketing | marketing | 4/7 | 3 |
| #3 | ELIJAH BROWN | 63.6 | marketing | marketing | 4/7 | 3 |
| #4 |  | 54.3 | marketing | marketing | 2/7 | 13 |
| #5 | SAYYED SHAIFAL ABBAS | 54.3 | marketing | marketing | 2/7 | 8 |
| #6 | SAYYED SHAIFAL ABBAS | 54.3 | marketing | marketing | 2/7 | 8 |
| #7 |  | 54.3 | marketing | marketing | 2/7 | 13 |
| #8 |  | 54.3 | marketing | marketing | 2/7 | 9 |
| #9 |  | 54.3 | marketing | marketing | 2/7 | 7 |
| #10 |  | 54.3 | marketing | marketing | 2/7 | 4 |
| #11 | Daiana Rocha | 54.3 | marketing | marketing | 2/7 | 4 |
| #12 |  | 54.3 | marketing | marketing | 2/7 | 6 |
| #13 |  | 53.6 | marketing | marketing | 4/7 | 1 |
| #14 |  | 53.6 | marketing | marketing | 4/7 | 1 |
| #15 |  | 49.3 | marketing | marketing | 2/7 | 3 |
| #16 | Alfred (Yi) Zhang | 49.3 | marketing | marketing | 2/7 | 3 |
| #17 |  | 47.1 | marketing | marketing | 1/7 | 11 |
| #18 | Anju Sasi | 47.1 | marketing | marketing | 1/7 | 5 |
| #19 |  | 47.1 | marketing | marketing | 1/7 | 9 |
| #20 | Reetabrata Bhattacharya | 47.1 | marketing | marketing | 1/7 | 6 |

### Sales Executive
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ISAAC HALL | 55.0 | marketing | marketing | 4/5 | 3 |
| #2 |  | 50.0 | healthcare | healthcare | 3/5 | 11 |
| #3 | SALIK SHAIKH | 50.0 | marketing | marketing | 3/5 | 5 |
| #4 | SALIK SHAIKH | 50.0 | marketing | marketing | 3/5 | 5 |
| #5 |  | 50.0 | healthcare | healthcare | 3/5 | 11 |
| #6 |  | 45.0 | engineering | software_engineering | 3/5 | 3 |
| #7 | Gaurav Kumar | 45.0 | healthcare | healthcare | 3/5 | 3 |
| #8 |  | 45.0 | hr | hr | 4/5 | 1 |
| #9 | M S | 40.0 | finance | finance | 2/5 | 6 |
| #10 | Oman Career Software | 40.0 | accounting | accounting | 2/5 | 4 |
| #11 | Hussein Masoud | 40.0 | accounting | accounting | 2/5 | 7 |
| #12 |  | 40.0 | healthcare | healthcare | 2/5 | 34 |
| #13 | Unmesh Ramesh Thorat | 40.0 | healthcare | healthcare | 2/5 | 17 |
| #14 | Shahriar Saaed Niazi | 40.0 | healthcare | healthcare | 2/5 | 5 |
| #15 | SHOIAB KHAN | 40.0 | engineering | software_engineering | 2/5 | 12 |
| #16 | MOHAMED ISMAIL | 40.0 | healthcare | healthcare | 2/5 | 41 |
| #17 | MOHAMED ISMAIL | 40.0 | healthcare | healthcare | 2/5 | 41 |
| #18 |  | 40.0 | healthcare | healthcare | 2/5 | 5 |
| #19 |  | 35.0 | hr | hr | 2/5 | 3 |
| #20 | Dheeraj S. Sharma | 35.0 | marketing | marketing | 3/5 | 1 |

### HR Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | UPADHYAY | 56.7 | hr | hr | 2/6 | 6 |
| #2 |  | 56.7 | hr | hr | 2/6 | 13 |
| #3 |  | 50.0 | hr | hr | 3/6 | 1 |
| #4 |  | 50.0 | hr | hr | 3/6 | 1 |
| #5 | Mahendra Kumar Yogi | 48.3 | hr | hr | 1/6 | 13 |
| #6 | M Priyadharsini | 48.3 | hr | hr | 1/6 | 4 |
| #7 |  | 48.3 | hr | hr | 1/6 | 8 |
| #8 |  | 48.3 | hr | hr | 1/6 | 8 |
| #9 | ARIF AHAMED M | 48.3 | hr | hr | 1/6 | 5 |
| #10 | Radha HG | 48.3 | hr | hr | 1/6 | 6 |
| #11 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 9 |
| #12 |  | 48.3 | hr | hr | 1/6 | 8 |
| #13 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 9 |
| #14 | Radha HG | 48.3 | hr | hr | 1/6 | 6 |
| #15 | ARIF AHAMED M | 48.3 | hr | hr | 1/6 | 5 |
| #16 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 13 |
| #17 | Hitesh Sagar | 48.3 | hr | hr | 1/6 | 11 |
| #18 | Mohammed Hidayath | 45.0 | hr | hr | 3/6 | 0 |
| #19 | Mohammed Hidayath | 45.0 | hr | hr | 3/6 | 0 |
| #20 |  | 43.3 | hr | hr | 1/6 | 3 |

### Accountant
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Godwin Opati Sitati | 54.3 | finance | finance | 2/7 | 8 |
| #2 | Abdullatif A. Shehadeh | 54.3 | finance | finance | 2/7 | 5 |
| #3 | ABU RAIS SIDDIQUI | 54.3 | finance | finance | 2/7 | 5 |
| #4 | Sammy Musungu | 48.6 | accounting | accounting | 4/7 | 6 |
| #5 | Finance Minister | 47.1 | finance | finance | 1/7 | 4 |
| #6 | Finance Minister | 47.1 | finance | finance | 1/7 | 4 |
| #7 | Khulood Rashed Al-Saad | 47.1 | finance | finance | 1/7 | 5 |
| #8 |  | 47.1 | finance | finance | 1/7 | 14 |
| #9 | VINEET MATHRADAS | 42.1 | finance | finance | 1/7 | 3 |
| #10 | Virak Internship Hdfc | 40.0 | finance | finance | 0/7 | 10 |
| #11 | M S | 40.0 | finance | finance | 0/7 | 6 |
| #12 | Dinesh Joghee Sockkan | 40.0 | finance | finance | 0/7 | 6 |
| #13 |  | 40.0 | finance | finance | 0/7 | 10 |
| #14 |  | 40.0 | finance | finance | 0/7 | 7 |
| #15 | CHAISE JAYAPRAKASH (CPSM) | 40.0 | finance | finance | 0/7 | 4 |
| #16 |  | 40.0 | finance | finance | 0/7 | 12 |
| #17 |  | 40.0 | finance | finance | 0/7 | 12 |
| #18 |  | 40.0 | finance | finance | 0/7 | 28 |
| #19 |  | 40.0 | finance | finance | 0/7 | 12 |
| #20 |  | 40.0 | finance | finance | 0/7 | 12 |

### Civil Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MOHD AAMIR | 59.3 | engineering | civil_engineering | 2/7 | 12 |
| #2 |  | 52.1 | engineering | civil_engineering | 1/7 | 11 |
| #3 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #4 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #5 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #6 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #7 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #8 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #9 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #10 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #11 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #12 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #13 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #14 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #15 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #16 | RAHIL | 52.1 | engineering | civil_engineering | 1/7 | 5 |
| #17 |  | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #18 |  | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #19 |  | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #20 | Emily Davies | 47.1 | engineering | civil_engineering | 1/7 | 3 |

### Electrical Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | IMRAN ALI | 45.0 | engineering | electrical_engineering | 0/7 | 9 |
| #2 | Shahbaz Khurram | 45.0 | engineering | electrical_engineering | 0/7 | 11 |
| #3 | IMRAN ALI | 45.0 | engineering | electrical_engineering | 0/7 | 9 |
| #4 | ___________________________ | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #5 | WORKING RF SYSTEMS ENGINEER | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #6 | Project Manager | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #7 | AVIATION ENGINEER | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #8 |  | 32.1 | engineering | software_engineering | 1/7 | 5 |
| #9 | Ramya. M | 32.1 | engineering | software_engineering | 1/7 | 5 |
| #10 |  | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #11 |  | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #12 |  | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #13 |  | 32.1 | engineering | software_engineering | 1/7 | 8 |
| #14 |  | 32.1 | engineering | civil_engineering | 1/7 | 5 |
| #15 | CVCV | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #16 | RAJA PAULRAJ | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #17 | Kumar N.Y. | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #18 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #19 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #20 | Motars Qatar Qatar | 30.0 | engineering | electrical_engineering | 0/7 | 1 |

### Mechanical Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | SA | 59.3 | engineering | mechanical_engineering | 2/7 | 4 |
| #2 |  | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #3 |  | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #4 |  | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #5 |  | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #6 | ANUJ UPPAL | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #7 |  | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #8 | M.YAKOOTH | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #9 |  | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #10 | JAGDISH CHAUDHARY | 52.1 | engineering | mechanical_engineering | 1/7 | 5 |
| #11 |  | 51.4 | engineering | mechanical_engineering | 3/7 | 1 |
| #12 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #13 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #14 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #15 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #16 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #17 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #18 |  | 49.3 | engineering | mechanical_engineering | 2/7 | 2 |
| #19 | GYANESH GULSHAN | 48.6 | hr | hr | 4/7 | 7 |
| #20 | Deepak Patel | 48.6 | hr | hr | 4/7 | 6 |

### Legal Advisor
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | John Smith | 60.0 | legal | legal | 3/5 | 2 |
| #2 | Adarsh Ramesh | 60.0 | legal | legal | 2/5 | 4 |
| #3 | Court Procedures Due Dilligenc | 55.0 | legal | legal | 3/5 | 1 |
| #4 |  | 55.0 | legal | legal | 3/5 | 1 |
| #5 | MOHAMMED JAVED KHAN | 50.0 | legal | legal | 1/5 | 6 |
| #6 |  | 50.0 | legal | legal | 1/5 | 7 |
| #7 | VIVEK RAJA | 50.0 | legal | legal | 1/5 | 4 |
| #8 | INSTRUMENT & CONTROL ENGINEER/ | 50.0 | legal | legal | 1/5 | 5 |
| #9 |  | 50.0 | legal | legal | 1/5 | 10 |
| #10 | Siddharth Aggarwal | 50.0 | legal | legal | 1/5 | 23 |
| #11 | INSTRUMENT & CONTROL ENGINEER/ | 50.0 | legal | legal | 1/5 | 5 |
| #12 | INSTRUMENT & CONTROL ENGINEER/ | 50.0 | legal | legal | 1/5 | 5 |
| #13 | Siddharth Aggarwal | 50.0 | legal | legal | 1/5 | 23 |
| #14 |  | 50.0 | legal | legal | 1/5 | 10 |
| #15 |  | 50.0 | legal | legal | 1/5 | 9 |
| #16 | Information Technology Special | 50.0 | legal | legal | 1/5 | 4 |
| #17 | SADATH BASHA.A.M | 50.0 | legal | legal | 1/5 | 5 |
| #18 |  | 45.0 | legal | legal | 1/5 | 3 |
| #19 |  | 45.0 | legal | legal | 1/5 | 3 |
| #20 | ZAFER HUSSAIN | 45.0 | legal | legal | 1/5 | 3 |

### Healthcare Specialist
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 |  | 68.3 | healthcare | healthcare | 4/6 | 3 |
| #2 |  | 58.3 | healthcare | healthcare | 4/6 | 1 |
| #3 | University Departmental Post | 56.7 | healthcare | healthcare | 2/6 | 5 |
| #4 | Charly Dolman | 51.7 | healthcare | healthcare | 2/6 | 3 |
| #5 | Microsoft Office | 51.7 | healthcare | healthcare | 2/6 | 3 |
| #6 | Core Accomplishments | 50.0 | healthcare | healthcare | 3/6 | 1 |
| #7 |  | 50.0 | healthcare | healthcare | 3/6 | 1 |
| #8 | WANGILA Abraham Masinde | 48.3 | healthcare | healthcare | 1/6 | 4 |
| #9 |  | 48.3 | healthcare | healthcare | 1/6 | 11 |
| #10 |  | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #11 |  | 48.3 | healthcare | healthcare | 1/6 | 4 |
| #12 |  | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #13 |  | 48.3 | healthcare | healthcare | 1/6 | 23 |
| #14 | S.Patterson Gnanasamy | 48.3 | healthcare | healthcare | 1/6 | 25 |
| #15 |  | 48.3 | healthcare | healthcare | 1/6 | 8 |
| #16 |  | 48.3 | healthcare | healthcare | 1/6 | 13 |
| #17 | EDUCATIONAL & PERSONAL DETAIL | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #18 |  | 48.3 | healthcare | healthcare | 1/6 | 15 |
| #19 | K. HENRY JOSEPH | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #20 | K. HENRY JOSEPH | 48.3 | healthcare | healthcare | 1/6 | 6 |

---
## Phase 5 — False Positive Audit
- **Count**: 4
- **FP Rate**: 2.5%
- **Formula**: 4 / (16 × 10)

| JD | Name | Score | Domain | Sub-Domain | Skills | Exp | Reason |
|----|------|-------|--------|------------|--------|-----|--------|
| Frontend Engineer | DANIEL GAN | 50.0 | engineering | civil_engineering | 6/10 | 2 | civil_engineering candidate in software JD 'Fronte |
| Sales Executive |  | 45.0 | engineering | software_engineering | 3/5 | 3 | engineering candidate in non-eng JD 'Sales Executi |
| Electrical Engineer |  | 32.1 | engineering | software_engineering | 1/7 | 5 | software_engineering candidate in Electrical Engin |
| Electrical Engineer | Ramya. M | 32.1 | engineering | software_engineering | 1/7 | 5 | software_engineering candidate in Electrical Engin |

---
## Phase 6 — False Negative Audit
- **Count**: 150

| JD | Name | Domain | Sub-Domain | Skills | Overlap | Reason |
|----|------|--------|------------|--------|---------|--------|
| Backend Engineer |  | engineering | software_engineering | 18 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer |  | engineering | software_engineering | 11 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Shanbagam Thanikachalam | engineering | software_engineering | 39 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | NOLAN | engineering | software_engineering | 15 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | WORKING RF SYSTEMS ENGINE | engineering | electrical_engineering | 46 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer |  | engineering | software_engineering | 55 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer |  | engineering | software_engineering | 49 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | People Centered Leadershi | engineering | civil_engineering | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer |  | engineering | software_engineering | 63 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | JACOB | engineering | software_engineering | 16 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Jose Curricular | engineering | software_engineering | 10 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | FRESHER | engineering | software_engineering | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | TAYLOR | engineering | software_engineering | 11 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Geakminds Inc | engineering | software_engineering | 10 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | LISA JENNINGS | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Drew Hall | engineering | software_engineering | 10 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | JACOB | engineering | software_engineering | 16 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | RODNEY | engineering | software_engineering | 17 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | E Express | engineering | software_engineering | 11 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Thiruvallam P.O | engineering | software_engineering | 33 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer |  | engineering | software_engineering | 31 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Akila Palanimuthu | engineering | software_engineering | 33 | 4 | Domain match + 4/10 skill overlap but not in  |
| Frontend Engineer | MOHD RASHID | engineering | software_engineering | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer |  | engineering | software_engineering | 8 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer |  | engineering | software_engineering | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer |  | engineering | software_engineering | 17 | 3 | Domain match + 3/10 skill overlap but not in  |

---
## Phase 6b — Domain Classification
- **Classified**: 85.0%
- **Formula**: `(5076 - 761) / 5076`
- **Unknown**: 761 (15.0%)

| Domain | Count | % | Avg Confidence |
|--------|-------|---|----------------|
| engineering | 1532 | 30.2% | 0.725 |
| healthcare | 1269 | 25.0% | 0.669 |
| unknown | 761 | 15.0% | 0.0 |
| hr | 600 | 11.8% | 0.643 |
| marketing | 290 | 5.7% | 0.557 |
| accounting | 286 | 5.6% | 0.543 |
| legal | 242 | 4.8% | 0.53 |
| finance | 96 | 1.9% | 0.539 |

---
## Phase 7 — Performance
| PDFs | Extract | Rank | Per-PDF | Memory | Failures |
|------|---------|------|---------|--------|----------|
| 1 | 0.16s | 0.005s | 162.6ms | 225.4MB | 0 |
| 10 | 1.4s | 0.058s | 139.8ms | 225.4MB | 0 |
| 100 | 13.72s | 2.32s | 137.2ms | 257.0MB | 0 |
| 1000 | 180.69s | 222.991s | 180.7ms | 257.0MB | 0 |
| 5076 | 886.93s | N/A | 174.7ms | 257.0MB | 0 | (Phase 1 batch extraction data)

---
## Phase 8 — Frontend Consistency
- **Accuracy**: 94.1% (16/17)
- ✅ POST /jobs: 
- ✅ POST /resumes: 
- ✅ SSE extraction: 
- ✅ POST /score: 
- ✅ Has candidates: 
- ✅ Field: name: 
- ✅ Field: document_id: 
- ✅ Field: final_score: 
- ✅ Field: rank: 
- ✅ Field: knocked_out: 
- ✅ Field: skill_score: 
- ✅ Field: experience_score: 
- ✅ Field: keyword_score: 
- ❌ Field: education_scre: 
- ✅ Field: matched_must_have: 
- ✅ Field: missing_must_have: 
- ✅ GET /results: 
