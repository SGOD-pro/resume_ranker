# Benchmark v6 — Production Report with Quality Remediation
Generated: 2026-06-23T14:12:01.456305
Version: 6.0.0

## Production Readiness Scorecard

| Category | Score | Weight | Formula |
|----------|-------|--------|---------|
| Extraction Quality | 69/100 █████████████░░░░░░░ | 25% | — |
| Ranking Quality | 95/100 ███████████████████░ | 20% | — |
| Knockout Reliability | 100/100 ████████████████████ | 15% | — |
| Domain Accuracy | 93/100 ██████████████████░░ | 15% | — |
| False Positive Control | 88/100 █████████████████░░░ | 10% | — |
| False Negative Control | 75/100 ███████████████░░░░░ | 10% | — |
| Performance | 100/100 ████████████████████ | 5% | — |
| **OVERALL** | **86/100** | **100%** | |

### Verdict: 🔵 PRODUCTION READY

### Metric Formulas (Phase 4 Audit)
- Extraction composite: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email = 69.1
- Ranking: 95 domain-matched in top-5 across 20 JDs = 95/(20×5)
- Knockout: 3/3
- Domain: (5076 - 339) / 5076 = 93.3%
- FP: 5 / (20 × 10) = 2.5%
- FN: 139 cases

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
- **Composite Score**: 69.1/100
- **Formula**: `0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email`

### Field Extraction Rates
| Field | Present | Rate | Formula | Avg Count |
|-------|---------|------|---------|-----------|
| name | 2711 | 53.4% | 2711/5076 | - |
| email | 3809 | 75.0% | 3809/5076 | - |
| phone | 3734 | 73.6% | 3734/5076 | - |
| skills | 4653 | 91.7% | 4653/5076 | 13.9 |
| experience | 2546 | 50.2% | 2546/5076 | 3.9 |
| education | 3929 | 77.4% | 3929/5076 | 2.0 |
| projects | 610 | 12.0% | 610/5076 | - |
| certs | 793 | 15.6% | 793/5076 | - |

### Name Precision Audit
- **Valid names**: 2711
- **Blank names**: 2365
- **Blacklisted names**: 96
- **Name Precision**: 96.6%
- **Formula**: `2711/(2711+96)`
- **Confidence distribution**: {'high': 2373, 'medium': 242, 'low': 96, 'zero': 2365}

### Anomalies
- Tag leaks: 4
- Skill duplicates: 12
- Low quality: 348

---
## Phase 2.5 — Deduplication Audit
- **Total PDFs**: 5076
- **Unique PDFs (by SHA256)**: 3856
- **Exact duplicates**: 1220 (1051 groups)
- **Near duplicates**: 154 (123 groups)
- **Dedup rate**: 27.1%

### Exact Duplicate Samples
- `21a975187145...`: cv (1).pdf, cv (4837).pdf
- `b47c741903a1...`: cv (10).pdf, cv (4843).pdf
- `6c83556835bc...`: cv (1054).pdf, cv (1055).pdf
- `d89c849c0d18...`: cv (11).pdf, cv (4844).pdf
- `745cac622eea...`: cv (1170).pdf, cv (1171).pdf
### Near Duplicate Samples
- `81285e886e96...`: cv (1002).pdf, cv (1393).pdf
- `4b45d2d2442d...`: cv (101).pdf, cv (53).pdf
- `4d4a626d75b8...`: cv (102).pdf, cv (388).pdf
- `31940ae997e2...`: cv (104).pdf, cv (222).pdf, cv (372).pdf
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
| #1 | Kiran Malhotra | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #2 | Rahul Gupta | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #3 | Shalini Nair | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #4 | Vikram Rao | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #5 | ZOE THOMPSON | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #6 | MARCUS HALL | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #7 | Aditya Joshi | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #8 | Amit Sharma | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #9 | Ananya Desai | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #10 | Neha Singh | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #11 | Priya Pa | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #12 | Rohan Mehra | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #13 | Unknown Candidate | 55.0 | engineering | software_engineering | 3/10 | 4 |
| #14 | Unknown Candidate | 55.0 | engineering | software_engineering | 3/10 | 5 |
| #15 | Pavithra Shetty | 55.0 | engineering | software_engineering | 3/10 | 4 |
| #16 | Unknown Candidate | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #17 | John Smith | 50.0 | engineering | software_engineering | 4/10 | 2 |
| #18 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #19 | Mashad Abbas | 50.0 | engineering | software_engineering | 2/10 | 23 |
| #20 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 7 |

### Frontend Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 65.0 | engineering | software_engineering | 6/10 | 3 |
| #2 | Harper Garcia | 60.0 | engineering | software_engineering | 5/10 | 3 |
| #3 | Unknown Candidate | 55.0 | engineering | software_engineering | 3/10 | 5 |
| #4 | Ujjwal Kumar | 55.0 | engineering | software_engineering | 3/10 | 8 |
| #5 | Unknown Candidate | 55.0 | engineering | software_engineering | 4/10 | 3 |
| #6 | DANIEL GAN | 50.0 | engineering | civil_engineering | 6/10 | 2 |
| #7 | HARI KRISHNAN | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #8 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #9 | Ramya. M | 50.0 | engineering | software_engineering | 2/10 | 5 |
| #10 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 7 |
| #11 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #12 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 9 |
| #13 | Unknown Candidate | 50.0 | engineering | software_engineering | 2/10 | 7 |
| #14 | Unknown Candidate | 50.0 | engineering | software_engineering | 5/10 | 1 |
| #15 | Unknown Candidate | 50.0 | engineering | software_engineering | 5/10 | 1 |
| #16 | Amit Sharma | 45.0 | engineering | software_engineering | 2/10 | 3 |
| #17 | Priya Elza | 45.0 | engineering | software_engineering | 3/10 | 2 |
| #18 | Unknown Candidate | 45.0 | engineering | software_engineering | 3/10 | 2 |
| #19 | Karthika Kumanan | 45.0 | engineering | software_engineering | 1/10 | 4 |
| #20 | Unknown Candidate | 45.0 | engineering | software_engineering | 1/10 | 6 |

### Fullstack Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #2 | Amit Sharma | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #3 | ZOE THOMPSON | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #4 | Unknown Candidate | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #5 | Aditya Joshi | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #6 | Ananya Desai | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #7 | Kiran Malhotra | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #8 | Neha Singh | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #9 | Priya Pa | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #10 | Rahul Gupta | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #11 | Rohan Mehra | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #12 | Shalini Nair | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #13 | Vikram Rao | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #14 | VICTORIA BAKER | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #15 | Harper Garcia | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #16 | Unknown Candidate | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #17 | Pavithra Shetty | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #18 | Unknown Candidate | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #19 | Unknown Candidate | 45.6 | engineering | software_engineering | 1/9 | 4 |
| #20 | Unknown Candidate | 45.6 | engineering | software_engineering | 1/9 | 5 |

### DevOps Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | VICTORIA BAKER | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #2 | Amit Sharma | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #3 | Ananya Desai | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #4 | Neha Singh | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #5 | Rahul Gupta | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #6 | Shalini Nair | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #7 | Unknown Candidate | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #8 | Joseline | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #9 | Joseline | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #10 | Aditya Joshi | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #11 | Kiran Malhotra | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #12 | Priya Pa | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #13 | Rohan Mehra | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #14 | Vikram Rao | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #15 | ZOE THOMPSON | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #16 | Unknown Candidate | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #17 | MARCUS HALL | 46.1 | engineering | software_engineering | 2/9 | 3 |
| #18 | Unknown Candidate | 45.6 | engineering | software_engineering | 1/9 | 4 |
| #19 | HARI KRISHNAN | 45.6 | engineering | software_engineering | 1/9 | 9 |
| #20 | Unknown Candidate | 45.6 | engineering | software_engineering | 1/9 | 5 |

### Data Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Aditya Joshi | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #2 | Ananya Desai | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #3 | Rohan Mehra | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #4 | Shalini Nair | 73.9 | engineering | software_engineering | 7/9 | 3 |
| #5 | Kiran Malhotra | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #6 | Neha Singh | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #7 | Priya Pa | 68.3 | engineering | software_engineering | 6/9 | 3 |
| #8 | John Smith | 63.3 | engineering | software_engineering | 6/9 | 2 |
| #9 | Amit Sharma | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #10 | Vikram Rao | 62.8 | engineering | software_engineering | 5/9 | 3 |
| #11 | Rahul Gupta | 57.2 | engineering | software_engineering | 4/9 | 3 |
| #12 | MARCUS HALL | 51.7 | engineering | software_engineering | 3/9 | 3 |
| #13 | Unknown Candidate | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #14 | Mashad Abbas | 51.1 | engineering | software_engineering | 2/9 | 23 |
| #15 | Unknown Candidate | 51.1 | engineering | software_engineering | 2/9 | 5 |
| #16 | Pavithra Shetty | 51.1 | engineering | software_engineering | 2/9 | 4 |
| #17 | Unknown Candidate | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #18 | Unknown Candidate | 47.2 | engineering | software_engineering | 4/9 | 1 |
| #19 | HARI KRISHNAN | 45.6 | engineering | software_engineering | 1/9 | 9 |
| #20 | Unknown Candidate | 45.6 | engineering | software_engineering | 1/9 | 5 |

### Data Scientist
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Aditya Joshi | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #2 | Rahul Gupta | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #3 | Rohan Mehra | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #4 | Amit Sharma | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #5 | Ananya Desai | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #6 | Kiran Malhotra | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #7 | Neha Singh | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #8 | Priya Pa | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #9 | Unknown Candidate | 58.8 | engineering | software_engineering | 3/8 | 5 |
| #10 | Pavithra Shetty | 58.8 | engineering | software_engineering | 3/8 | 4 |
| #11 | Chechnik | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #12 | Gruvil Technologies | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #13 | Chechnik | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #14 | Unknown Candidate | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #15 | Joseline | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #16 | Unknown Candidate | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #17 | Joseline | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #18 | Edison | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #19 | BLAKE MESTLY | 56.2 | engineering | software_engineering | 5/8 | 1 |
| #20 | Gruvil Technologies | 56.2 | engineering | software_engineering | 5/8 | 1 |

### ML Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Rahul Gupta | 66.2 | engineering | software_engineering | 5/8 | 3 |
| #2 | Unknown Candidate | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #3 | Joseline | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #4 | Unknown Candidate | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #5 | Joseline | 62.5 | engineering | software_engineering | 6/8 | 1 |
| #6 | Amit Sharma | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #7 | Kiran Malhotra | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #8 | VICTORIA BAKER | 60.0 | engineering | software_engineering | 4/8 | 3 |
| #9 | Priya Pa | 53.8 | engineering | software_engineering | 3/8 | 3 |
| #10 | Aditya Joshi | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #11 | Ananya Desai | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #12 | Neha Singh | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #13 | Rohan Mehra | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #14 | Shalini Nair | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #15 | Vikram Rao | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #16 | MARCUS HALL | 47.5 | engineering | software_engineering | 2/8 | 3 |
| #17 | Unknown Candidate | 46.2 | engineering | software_engineering | 1/8 | 4 |
| #18 | Unknown Candidate | 46.2 | engineering | software_engineering | 1/8 | 5 |
| #19 | Unknown Candidate | 46.2 | engineering | software_engineering | 1/8 | 5 |
| #20 | Pavithra Shetty | 46.2 | engineering | software_engineering | 1/8 | 4 |

### Marketing Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | LIAM | 65.7 | marketing | marketing | 5/7 | 2 |
| #2 | Christopher Fowler | 63.6 | marketing | marketing | 4/7 | 3 |
| #3 | ELIJAH BROWN | 63.6 | marketing | marketing | 4/7 | 3 |
| #4 | SAYYED SHAIFAL ABBAS | 54.3 | marketing | marketing | 2/7 | 8 |
| #5 | SAYYED SHAIFAL ABBAS | 54.3 | marketing | marketing | 2/7 | 8 |
| #6 | Unknown Candidate | 54.3 | marketing | marketing | 2/7 | 9 |
| #7 | Unknown Candidate | 54.3 | marketing | marketing | 2/7 | 7 |
| #8 | Daiana Rocha | 54.3 | marketing | marketing | 2/7 | 4 |
| #9 | Unknown Candidate | 53.6 | marketing | marketing | 4/7 | 1 |
| #10 | Unknown Candidate | 49.3 | marketing | marketing | 2/7 | 3 |
| #11 | Alfred (Yi) Zhang | 49.3 | marketing | marketing | 2/7 | 3 |
| #12 | Anju Sasi | 47.1 | marketing | marketing | 1/7 | 5 |
| #13 | Unknown Candidate | 47.1 | marketing | marketing | 1/7 | 9 |
| #14 | Reetabrata Bhattacharya | 47.1 | marketing | marketing | 1/7 | 6 |
| #15 | Unknown Candidate | 47.1 | marketing | marketing | 1/7 | 4 |
| #16 | Unknown Candidate | 47.1 | marketing | marketing | 1/7 | 4 |
| #17 | Esteemed Organization | 47.1 | marketing | marketing | 1/7 | 4 |
| #18 | Christopher Fowler | 46.4 | marketing | marketing | 3/7 | 1 |
| #19 | Unknown Candidate | 46.4 | marketing | marketing | 3/7 | 1 |
| #20 | Unknown Candidate | 46.4 | marketing | marketing | 3/7 | 1 |

### Sales Executive
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ISAAC HALL | 75.0 | sales | sales | 4/5 | 3 |
| #2 | PRAKASH PINDARI | 70.0 | sales | sales | 3/5 | 11 |
| #3 | SALIK SHAIKH | 70.0 | sales | sales | 3/5 | 5 |
| #4 | SALIK SHAIKH | 70.0 | sales | sales | 3/5 | 5 |
| #5 | PRAKASH PINDARI | 70.0 | sales | sales | 3/5 | 11 |
| #6 | Unknown Candidate | 65.0 | sales | sales | 4/5 | 1 |
| #7 | M S | 60.0 | sales | sales | 2/5 | 6 |
| #8 | Oman Career Software | 60.0 | sales | sales | 2/5 | 4 |
| #9 | Shahriar Saaed Niazi | 60.0 | sales | sales | 2/5 | 5 |
| #10 | SHOIAB KHAN | 60.0 | sales | sales | 2/5 | 12 |
| #11 | Unknown Candidate | 55.0 | sales | sales | 2/5 | 3 |
| #12 | Dheeraj S. Sharma | 55.0 | sales | sales | 3/5 | 1 |
| #13 | MOHITH KRISHNAN | 55.0 | sales | sales | 2/5 | 3 |
| #14 | Unknown Candidate | 55.0 | sales | sales | 2/5 | 3 |
| #15 | Shahadat Hussain | 55.0 | sales | sales | 2/5 | 3 |
| #16 | Shahadat Hussain | 55.0 | sales | sales | 2/5 | 3 |
| #17 | Unknown Candidate | 55.0 | sales | sales | 3/5 | 1 |
| #18 | Unknown Candidate | 55.0 | sales | sales | 3/5 | 1 |
| #19 | Career Overview | 55.0 | sales | sales | 3/5 | 1 |
| #20 | SEBASTIAN MARTIN | 55.0 | sales | sales | 2/5 | 3 |

### HR Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 50.0 | hr | hr | 3/6 | 1 |
| #2 | Unknown Candidate | 50.0 | hr | hr | 3/6 | 1 |
| #3 | Mahendra Kumar Yogi | 48.3 | hr | hr | 1/6 | 13 |
| #4 | M Priyadharsini | 48.3 | hr | hr | 1/6 | 4 |
| #5 | Unknown Candidate | 48.3 | hr | hr | 1/6 | 8 |
| #6 | Unknown Candidate | 48.3 | hr | hr | 1/6 | 8 |
| #7 | Radha HG | 48.3 | hr | hr | 1/6 | 6 |
| #8 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 9 |
| #9 | Unknown Candidate | 48.3 | hr | hr | 1/6 | 8 |
| #10 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 9 |
| #11 | Radha HG | 48.3 | hr | hr | 1/6 | 6 |
| #12 | Bhola Nagar | 48.3 | hr | hr | 1/6 | 13 |
| #13 | Mohammed Hidayath | 45.0 | hr | hr | 3/6 | 0 |
| #14 | Mohammed Hidayath | 45.0 | hr | hr | 3/6 | 0 |
| #15 | LOGISTICS AND SHIPPING | 43.3 | hr | hr | 1/6 | 3 |
| #16 | LOGISTICS AND SHIPPING | 43.3 | hr | hr | 1/6 | 3 |
| #17 | Unknown Candidate | 41.7 | hr | hr | 2/6 | 1 |
| #18 | Unknown Candidate | 41.7 | hr | hr | 2/6 | 1 |
| #19 | Unknown Candidate | 41.7 | hr | hr | 2/6 | 1 |
| #20 | Unknown Candidate | 41.7 | hr | hr | 2/6 | 1 |

### Accountant
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Godwin Opati Sitati | 54.3 | finance | finance | 2/7 | 8 |
| #2 | Abdullatif A. Shehadeh | 54.3 | finance | finance | 2/7 | 5 |
| #3 | ABU RAIS SIDDIQUI | 54.3 | finance | finance | 2/7 | 5 |
| #4 | Sammy Musungu | 48.6 | accounting | accounting | 4/7 | 6 |
| #5 | Khulood Rashed Al-Saad | 47.1 | finance | finance | 1/7 | 5 |
| #6 | Unknown Candidate | 47.1 | finance | finance | 1/7 | 14 |
| #7 | VINEET MATHRADAS | 42.1 | finance | finance | 1/7 | 3 |
| #8 | Virak Internship Hdfc | 40.0 | finance | finance | 0/7 | 10 |
| #9 | Dinesh Joghee Sockkan | 40.0 | finance | finance | 0/7 | 6 |
| #10 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 10 |
| #11 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 7 |
| #12 | CHAISE JAYAPRAKASH (CPSM) | 40.0 | finance | finance | 0/7 | 4 |
| #13 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #14 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #15 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #16 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #17 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #18 | Unknown Candidate | 40.0 | finance | finance | 0/7 | 12 |
| #19 | CHAISE JAYAPRAKASH (CPSM) | 40.0 | finance | finance | 0/7 | 4 |
| #20 | Unknown Candidate | 39.3 | finance | finance | 2/7 | 1 |

### Civil Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #2 | Unknown Candidate | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #3 | Unknown Candidate | 51.4 | engineering | civil_engineering | 3/7 | 1 |
| #4 | Emily Davies | 47.1 | engineering | civil_engineering | 1/7 | 3 |
| #5 | Unknown Candidate | 47.1 | engineering | civil_engineering | 1/7 | 3 |
| #6 | September IBIS Ho | 46.4 | engineering | civil_engineering | 3/7 | 0 |
| #7 | ASEEM PEER MOHAMMAD | 46.4 | engineering | civil_engineering | 3/7 | 0 |
| #8 | Unknown Candidate | 45.0 | engineering | civil_engineering | 0/7 | 67 |
| #9 | Unknown Candidate | 45.0 | engineering | civil_engineering | 0/7 | 4 |
| #10 | Mohammed Abdul Nayeem. | 44.3 | engineering | civil_engineering | 2/7 | 1 |
| #11 | Mohammed Abdul Nayeem. | 44.3 | engineering | civil_engineering | 2/7 | 1 |
| #12 | Mohammed Abdul Nayeem. | 44.3 | engineering | civil_engineering | 2/7 | 1 |
| #13 | Unknown Candidate | 44.3 | engineering | civil_engineering | 2/7 | 1 |
| #14 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 7 |
| #15 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 12 |
| #16 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 7 |
| #17 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 7 |
| #18 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 7 |
| #19 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 12 |
| #20 | RAJESH K R | 41.4 | healthcare | healthcare | 3/7 | 7 |

### Electrical Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | WORKING RF SYSTEMS ENGINEER | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #2 | Project Manager | 37.1 | engineering | electrical_engineering | 1/7 | 1 |
| #3 | Unknown Candidate | 32.1 | engineering | software_engineering | 1/7 | 5 |
| #4 | Ramya. M | 32.1 | engineering | software_engineering | 1/7 | 5 |
| #5 | Unknown Candidate | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #6 | Unknown Candidate | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #7 | Unknown Candidate | 32.1 | engineering | electrical_engineering | 1/7 | 0 |
| #8 | Ujjwal Kumar | 32.1 | engineering | software_engineering | 1/7 | 8 |
| #9 | CVCV | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #10 | Kumar N.Y. | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #11 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #12 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #13 | Unknown Candidate | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #14 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #15 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #16 | Unknown Candidate | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #17 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #18 | Kumar N.Y. | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #19 | Kumar N.Y. | 30.0 | engineering | electrical_engineering | 0/7 | 1 |
| #20 | Mohammad Fahimuddin | 30.0 | engineering | electrical_engineering | 0/7 | 1 |

### Mechanical Engineer
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #2 | Unknown Candidate | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #3 | Unknown Candidate | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #4 | Unknown Candidate | 54.3 | engineering | mechanical_engineering | 2/7 | 3 |
| #5 | ANUJ UPPAL | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #6 | Unknown Candidate | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #7 | M.YAKOOTH | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #8 | Unknown Candidate | 53.6 | engineering | mechanical_engineering | 4/7 | 0 |
| #9 | Unknown Candidate | 51.4 | engineering | mechanical_engineering | 3/7 | 1 |
| #10 | GYANESH GULSHAN | 48.6 | sales | sales | 4/7 | 7 |
| #11 | Deepak Patel | 48.6 | hr | hr | 4/7 | 6 |
| #12 | Kesava Career Work | 48.6 | healthcare | healthcare | 4/7 | 5 |
| #13 | JOHNS K ABRAHAM | 48.6 | healthcare | healthcare | 4/7 | 8 |
| #14 | Pankaj Kumar Gupt | 47.1 | engineering | mechanical_engineering | 1/7 | 3 |
| #15 | Unknown Candidate | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |
| #16 | Unknown Candidate | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |
| #17 | Unknown Candidate | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |
| #18 | Unknown Candidate | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |
| #19 | Aditya | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |
| #20 | Aditya | 46.4 | engineering | mechanical_engineering | 3/7 | 0 |

### Legal Advisor
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | John Smith | 60.0 | legal | legal | 3/5 | 2 |
| #2 | Adarsh Ramesh | 60.0 | legal | legal | 2/5 | 4 |
| #3 | Court Procedures Due Dilligenc | 55.0 | legal | legal | 3/5 | 1 |
| #4 | Unknown Candidate | 55.0 | legal | legal | 3/5 | 1 |
| #5 | MOHAMMED JAVED KHAN | 50.0 | legal | legal | 1/5 | 6 |
| #6 | Siddharth Aggarwal | 50.0 | legal | legal | 1/5 | 23 |
| #7 | Siddharth Aggarwal | 50.0 | legal | legal | 1/5 | 23 |
| #8 | Information Technology Special | 50.0 | legal | legal | 1/5 | 4 |
| #9 | ZAFER HUSSAIN | 45.0 | legal | legal | 1/5 | 3 |
| #10 | DR.R. Pradheep Kumar | 45.0 | legal | legal | 2/5 | 1 |
| #11 | DR.R. Pradheep Kumar | 45.0 | legal | legal | 2/5 | 1 |
| #12 | Unknown Candidate | 45.0 | legal | legal | 2/5 | 1 |
| #13 | Unknown Candidate | 45.0 | legal | legal | 2/5 | 1 |
| #14 | Unknown Candidate | 40.0 | education | education | 2/5 | 29 |
| #15 | Shabina P | 40.0 | marketing | marketing | 3/5 | 2 |
| #16 | Shabina P | 40.0 | marketing | marketing | 3/5 | 2 |
| #17 | Sonu Kumar Yadav | 40.0 | legal | legal | 0/5 | 4 |
| #18 | Unknown Candidate | 40.0 | legal | legal | 0/5 | 7 |
| #19 | Paulos Mubi Nkosi | 40.0 | legal | legal | 0/5 | 12 |
| #20 | Mechanical Engineer (Plumbing  | 40.0 | legal | legal | 0/5 | 8 |

### Healthcare Specialist
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 68.3 | healthcare | healthcare | 4/6 | 3 |
| #2 | Unknown Candidate | 58.3 | healthcare | healthcare | 4/6 | 1 |
| #3 | University Departmental Post | 56.7 | healthcare | healthcare | 2/6 | 5 |
| #4 | Charly Dolman | 51.7 | healthcare | healthcare | 2/6 | 3 |
| #5 | Core Accomplishments | 50.0 | healthcare | healthcare | 3/6 | 1 |
| #6 | Unknown Candidate | 50.0 | healthcare | healthcare | 3/6 | 1 |
| #7 | WANGILA Abraham Masinde | 48.3 | healthcare | healthcare | 1/6 | 4 |
| #8 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 11 |
| #9 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #10 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 23 |
| #11 | S.Patterson Gnanasamy | 48.3 | healthcare | healthcare | 1/6 | 25 |
| #12 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 8 |
| #13 | EDUCATIONAL & PERSONAL DETAIL | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #14 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 15 |
| #15 | K. HENRY JOSEPH | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #16 | K. HENRY JOSEPH | 48.3 | healthcare | healthcare | 1/6 | 6 |
| #17 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 15 |
| #18 | PREEDIPRAJ. M Mob. No. | 48.3 | healthcare | healthcare | 1/6 | 9 |
| #19 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 23 |
| #20 | Unknown Candidate | 48.3 | healthcare | healthcare | 1/6 | 22 |

### Teacher
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | RISHA SRITHARAN | 55.0 | education | education | 2/4 | 2 |
| #2 | Kimberly Fisheli | 52.5 | education | education | 1/4 | 6 |
| #3 | CLASSROOM TEACHER | 50.0 | education | education | 2/4 | 1 |
| #4 | ART TEACHER | 50.0 | education | education | 2/4 | 1 |
| #5 | HOMEBOUND TEACHER | 50.0 | education | education | 2/4 | 1 |
| #6 | Unknown Candidate | 50.0 | education | education | 2/4 | 1 |
| #7 | ENGLISH TEACHER | 50.0 | education | education | 2/4 | 1 |
| #8 | HISTORY TEACHER | 50.0 | education | education | 2/4 | 1 |
| #9 | Unknown Candidate | 50.0 | education | education | 2/4 | 1 |
| #10 | Unknown Candidate | 50.0 | education | education | 2/4 | 1 |
| #11 | LEAD TEACHER | 50.0 | education | education | 2/4 | 1 |
| #12 | Unknown Candidate | 50.0 | education | education | 2/4 | 1 |
| #13 | Unknown Candidate | 50.0 | education | education | 2/4 | 1 |
| #14 | Science Education. | 50.0 | education | education | 2/4 | 1 |
| #15 | READING TEACHER | 50.0 | education | education | 2/4 | 1 |
| #16 | Microsoft Office | 47.5 | education | education | 1/4 | 3 |
| #17 | Unknown Candidate | 47.5 | education | education | 1/4 | 3 |
| #18 | U. Jagadeeswari | 42.5 | education | education | 1/4 | 2 |
| #19 | LEAD TEACHER | 42.5 | education | education | 1/4 | 2 |
| #20 | SURESH.S | 40.0 | education | education | 0/4 | 5 |

### Hotel Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 45.0 | healthcare | healthcare | 2/4 | 23 |
| #2 | Unknown Candidate | 45.0 | healthcare | healthcare | 2/4 | 23 |
| #3 | Unknown Candidate | 40.0 | hospitality | hospitality | 0/4 | 5 |
| #4 | Unknown Candidate | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #5 | Geoffrey Makoe | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #6 | Unknown Candidate | 40.0 | hospitality | hospitality | 0/4 | 7 |
| #7 | UPADHYAY | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #8 | CURRICULAM VITEA | 40.0 | hospitality | hospitality | 0/4 | 8 |
| #9 | CHETAN SWARUP | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #10 | Mohammed Fazil.F.M | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #11 | Sabique Hasan | 40.0 | hospitality | hospitality | 0/4 | 23 |
| #12 | Unknown Candidate | 40.0 | hospitality | hospitality | 0/4 | 8 |
| #13 | Mohammad Anwar Hussain | 40.0 | hospitality | hospitality | 0/4 | 4 |
| #14 | Mohammad Anwar Hussain | 40.0 | hospitality | hospitality | 0/4 | 4 |
| #15 | Unknown Candidate | 40.0 | hospitality | hospitality | 0/4 | 8 |
| #16 | Sabique Hasan | 40.0 | hospitality | hospitality | 0/4 | 23 |
| #17 | Mohammed Fazil.F.M | 40.0 | hospitality | hospitality | 0/4 | 6 |
| #18 | SADATH BASHA.A.M | 40.0 | hospitality | hospitality | 0/4 | 5 |
| #19 | Unknown Candidate | 37.5 | hospitality | hospitality | 1/4 | 1 |
| #20 | Gaurav Kumar | 35.0 | hospitality | hospitality | 0/4 | 3 |

### Construction Manager
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Ramkumar Kasilingam | 77.5 | construction | construction | 3/4 | 5 |
| #2 | Ramkumar Kasilingam | 77.5 | construction | construction | 3/4 | 5 |
| #3 | AQEEL AHMED | 67.5 | construction | construction | 3/4 | 2 |
| #4 | Unknown Candidate | 65.0 | construction | construction | 2/4 | 4 |
| #5 | Senior Planning | 65.0 | construction | construction | 2/4 | 16 |
| #6 | Career Objectives | 65.0 | construction | construction | 2/4 | 12 |
| #7 | Career Objectives | 65.0 | construction | construction | 2/4 | 12 |
| #8 | Unknown Candidate | 65.0 | construction | construction | 2/4 | 4 |
| #9 | ELECTRICAL ENGINEER | 65.0 | construction | construction | 2/4 | 4 |
| #10 | Unknown Candidate | 55.0 | construction | construction | 2/4 | 2 |
| #11 | RAMKUMAR | 55.0 | construction | construction | 2/4 | 2 |
| #12 | RAMKUMAR | 55.0 | construction | construction | 2/4 | 2 |
| #13 | Unknown Candidate | 52.5 | construction | construction | 1/4 | 11 |
| #14 | Unknown Candidate | 52.5 | construction | construction | 1/4 | 4 |
| #15 | KAVIYALAN ANNADURAI | 52.5 | construction | construction | 1/4 | 16 |
| #16 | RAHIL | 52.5 | construction | construction | 1/4 | 5 |
| #17 | RAHIL | 52.5 | construction | construction | 1/4 | 5 |
| #18 | Unknown Candidate | 52.5 | construction | construction | 1/4 | 16 |
| #19 | RAHIL | 52.5 | construction | construction | 1/4 | 5 |
| #20 | MOHD AAMIR | 52.5 | construction | construction | 1/4 | 12 |

### Office Admin
Total candidates: 5076

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Premananda Das | 52.5 | admin | admin | 1/4 | 8 |
| #2 | Taniamangalam VILL | 52.5 | admin | admin | 1/4 | 9 |
| #3 | Maintenance Executive ABFRL GR | 52.5 | admin | admin | 1/4 | 5 |
| #4 | MAHESH CHANDRA S | 52.5 | admin | admin | 1/4 | 34 |
| #5 | Taniamangalam VILL | 52.5 | admin | admin | 1/4 | 9 |
| #6 | K.J.MOHAMMED IRFAN | 52.5 | admin | admin | 1/4 | 4 |
| #7 | K.J.MOHAMMED IRFAN | 52.5 | admin | admin | 1/4 | 4 |
| #8 | Taniamangalam VILL | 52.5 | admin | admin | 1/4 | 9 |
| #9 | MAHESH CHANDRA S | 52.5 | admin | admin | 1/4 | 34 |
| #10 | Maintenance Executive ABFRL GR | 52.5 | admin | admin | 1/4 | 5 |
| #11 | Maintenance Executive ABFRL GR | 52.5 | admin | admin | 1/4 | 5 |
| #12 | JEWELRY CONSULTANT | 50.0 | admin | admin | 2/4 | 1 |
| #13 | Unknown Candidate | 50.0 | admin | admin | 2/4 | 1 |
| #14 | Unknown Candidate | 50.0 | admin | admin | 2/4 | 1 |
| #15 | Unknown Candidate | 45.0 | healthcare | healthcare | 2/4 | 4 |
| #16 | Unknown Candidate | 45.0 | healthcare | healthcare | 2/4 | 4 |
| #17 | Unknown Candidate | 42.5 | admin | admin | 1/4 | 2 |
| #18 | Unknown Candidate | 42.5 | admin | admin | 1/4 | 2 |
| #19 | Position Desire | 42.5 | admin | admin | 1/4 | 2 |
| #20 | Unknown Candidate | 42.5 | admin | admin | 1/4 | 2 |

---
## Phase 5 — False Positive Audit
- **Count**: 5
- **FP Rate**: 2.5%
- **Formula**: 5 / (20 × 10)

| JD | Name | Score | Domain | Sub-Domain | Skills | Exp | Reason |
|----|------|-------|--------|------------|--------|-----|--------|
| Frontend Engineer | DANIEL GAN | 50.0 | engineering | civil_engineering | 6/10 | 2 | civil_engineering candidate in software JD 'Fronte |
| Electrical Engineer | Unknown Candidate | 32.1 | engineering | software_engineering | 1/7 | 5 | software_engineering candidate in Electrical Engin |
| Electrical Engineer | Ramya. M | 32.1 | engineering | software_engineering | 1/7 | 5 | software_engineering candidate in Electrical Engin |
| Electrical Engineer | Ujjwal Kumar | 32.1 | engineering | software_engineering | 1/7 | 8 | software_engineering candidate in Electrical Engin |
| Mechanical Engineer | GYANESH GULSHAN | 48.6 | sales | sales | 4/7 | 7 | sales candidate in Mechanical Engineer JD |

---
## Phase 6 — False Negative Audit
- **Count**: 139

| JD | Name | Domain | Sub-Domain | Skills | Overlap | Reason |
|----|------|--------|------------|--------|---------|--------|
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 18 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 11 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Shanbagam Thanikachalam | engineering | software_engineering | 39 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | NOLAN | engineering | software_engineering | 15 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | WORKING RF SYSTEMS ENGINE | engineering | electrical_engineering | 46 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 55 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 49 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | People Centered Leadershi | engineering | civil_engineering | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 63 | 4 | Domain match + 4/10 skill overlap but not in  |
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
| Frontend Engineer | Unknown Candidate | engineering | software_engineering | 31 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Akila Palanimuthu | engineering | software_engineering | 33 | 4 | Domain match + 4/10 skill overlap but not in  |
| Frontend Engineer | MOHD RASHID | engineering | software_engineering | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | MOHD. RASHID | engineering | software_engineering | 8 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Unknown Candidate | engineering | software_engineering | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Unknown Candidate | engineering | software_engineering | 17 | 3 | Domain match + 3/10 skill overlap but not in  |

---
## Phase 6b — Domain Classification
- **Classified**: 93.3%
- **Formula**: `(5076 - 339) / 5076`
- **Unknown**: 339 (6.7%)

| Domain | Count | % | Avg Confidence |
|--------|-------|---|----------------|
| engineering | 1383 | 27.2% | 0.728 |
| healthcare | 765 | 15.1% | 0.565 |
| hr | 530 | 10.4% | 0.658 |
| insufficient_data | 407 | 8.0% | 0.0 |
| unknown | 339 | 6.7% | 0.0 |
| construction | 300 | 5.9% | 0.49 |
| education | 285 | 5.6% | 0.483 |
| accounting | 250 | 4.9% | 0.508 |
| marketing | 228 | 4.5% | 0.491 |
| sales | 221 | 4.4% | 0.43 |
| legal | 142 | 2.8% | 0.539 |
| hospitality | 80 | 1.6% | 0.477 |
| finance | 77 | 1.5% | 0.528 |
| admin | 69 | 1.4% | 0.417 |

---
## Phase 7 — Performance
| PDFs | Extract | Rank | Per-PDF | Memory | Failures |
|------|---------|------|---------|--------|----------|
| 1 | 0.16s | 0.005s | 157.1ms | 224.9MB | 0 |
| 10 | 1.33s | 0.062s | 132.7ms | 224.9MB | 0 |
| 100 | 15.17s | 2.53s | 151.7ms | 257.1MB | 0 |
| 1000 | 185.12s | 223.007s | 185.1ms | 257.1MB | 0 |
| 5076 | 881.46s | N/A | 173.7ms | 257.1MB | 0 | (Phase 1 batch extraction data)

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
