# Benchmark v7 — Ranking Integrity & Truthfulness Report
Generated: 2026-06-23T21:53:46.405006
Version: 7.0.0

## Production Readiness Scorecard

| Category | Score | Weight | Formula |
|----------|-------|--------|---------|
| Extraction Quality | 72/100 ██████████████░░░░░░ | 25% | — |
| Ranking Quality | 67/100 █████████████░░░░░░░ | 20% | — |
| Knockout Reliability | 100/100 ████████████████████ | 15% | — |
| Domain Accuracy | 95/100 ███████████████████░ | 15% | — |
| False Positive Control | 55/100 ███████████░░░░░░░░░ | 10% | — |
| False Negative Control | 75/100 ███████████████░░░░░ | 10% | — |
| Performance | 80/100 ████████████████░░░░ | 5% | — |
| **OVERALL** | **78/100** | **100%** | |

### Verdict: 🟡 BETA READY

### Metric Formulas (Phase 4 Audit)
- Extraction composite: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email = 72.4
- Ranking: 67 domain-matched in top-5 across 20 JDs = 67/(20×5)
- Knockout: 3/3
- Domain: (2234 - 106) / 2234 = 95.3%
- FP: 18 / (20 × 10) = 9.0%
- FN: 155 cases

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
- **Total PDFs**: 3856
- **Success Rate**: 57.9% (2234/3856)
- **Composite Score**: 72.4/100
- **Formula**: `0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email`

### Field Extraction Rates
| Field | Present | Rate | Formula | Avg Count |
|-------|---------|------|---------|-----------|
| name | 1940 | 86.8% | 1940/2234 | - |
| email | 1483 | 66.4% | 1483/2234 | - |
| phone | 1440 | 64.5% | 1440/2234 | - |
| skills | 1906 | 85.3% | 1906/2234 | 15.0 |
| experience | 1086 | 48.6% | 1086/2234 | 4.1 |
| education | 1660 | 74.3% | 1660/2234 | 2.0 |
| projects | 282 | 12.6% | 282/2234 | - |
| certs | 371 | 16.6% | 371/2234 | - |

### Name Precision Audit
- **Valid names**: 1940
- **Blank names**: 294
- **Blacklisted names**: 64
- **Name Precision**: 96.8%
- **Formula**: `1940/(1940+64)`
- **Confidence distribution**: {'high': 1704, 'medium': 172, 'low': 64, 'zero': 294}

### Unknown Candidate Breakdown (missing_name_reason)
| Reason | Count | % of Unknown |
|--------|-------|-------------|
| UNKNOWN | 293 | 99.7% |
| EMPTY_DOCUMENT | 1 | 0.3% |

### Anomalies
- Tag leaks: 1
- Skill duplicates: 8
- Low quality: 295

---
## Phase 2.5 — Deduplication Audit
- **Total PDFs**: 3856
- **Unique PDFs (by SHA256)**: 3856
- **Exact duplicates**: 0 (0 groups)
- **Near duplicates**: 566 (160 groups)
- **Dedup rate**: 14.7%

### Near Duplicate Samples
- `cbe5cfdf7c21...`: cv (1003).pdf, cv (1004).pdf, cv (1005).pdf
- `4d4a626d75b8...`: cv (102).pdf, cv (388).pdf
- `fdf04b4ed281...`: cv (1045).pdf, cv (1046).pdf
- `385c80a3973f...`: cv (1053).pdf, cv (1442).pdf
- `0bac3ca03fcf...`: cv (109).pdf, cv (144).pdf, cv (1666).pdf

---
## Phase 3 — Skill Intelligence
- **Accuracy**: 100.0%  **P**: 100.0%  **R**: 100.0%  **F1**: 100.0%
- TP=15  TN=4  FP=0  FN=0

---
## Phase 4 — Ranking Accuracy

### Backend Engineer
Total candidates: 411

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ZOE THOMPSON | 80.6 | engineering | software | 8/10 | 6 |
| #2 | Rahul Gupta | 72.5 | engineering | software | 9/10 | 12 |
| #3 | Kiran Malhotra | 68.8 | engineering | data | 7/10 | 12 |
| #4 | Amit Sharma | 66.6 | engineering | software | 8/10 | 12 |
| #5 | Vikram Rao | 66.0 | engineering | data | 7/10 | 12 |
| #6 | Ananya Desai | 65.9 | engineering | data | 7/10 | 11 |
| #7 | Rohan Mehra | 65.9 | engineering | data | 7/10 | 11 |
| #8 | Priya Pa | 65.9 | engineering | data | 7/10 | 11 |
| #9 | Shalini Nair | 63.9 | engineering | data | 7/10 | 12 |
| #10 | Aditya Joshi | 63.9 | engineering | data | 7/10 | 11 |
| #11 | Neha Singh | 63.0 | engineering | software | 7/10 | 11 |
| #12 | It Consultant | 58.3 | engineering | software | 6/10 | 6 |
| #13 | MARCUS HALL | 56.9 | engineering | software | 7/10 | 10 |
| #14 | John Smith | 53.8 | engineering | data | 5/10 | 5 |
| #15 | Pavithra Shetty | 52.6 | engineering | software | 5/10 | 11 |
| #16 | VICTORIA BAKER | 52.5 | engineering | devops | 4/10 | 6 |
| #17 | Wms Consultant | 51.0 | engineering | backend | 4/10 | 14 |
| #18 | Souvik Karmakar | 49.8 | engineering | software | 8/10 | 0 |
| #19 | Database Programmer/Analyst (. | 49.4 | engineering | software | 6/10 | 0 |
| #20 | Database Programmer/Analyst (. | 49.2 | engineering | software | 7/10 | 1 |

### Frontend Engineer
Total candidates: 360

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | It Consultant | 62.4 | engineering | software | 8/10 | 6 |
| #2 | MARCUS HALL | 60.1 | engineering | software | 9/10 | 10 |
| #3 | Harper Garcia | 53.9 | engineering | software | 9/10 | 9 |
| #4 | Akila Palanimuthu | 53.4 | engineering | software | 8/10 | 0 |
| #5 | Database Programmer/Analyst (. | 49.3 | engineering | software | 8/10 | 0 |
| #6 | Souvik Karmakar | 47.1 | engineering | software | 8/10 | 0 |
| #7 | Database Programmer/Analyst (. | 46.9 | engineering | software | 8/10 | 1 |
| #8 | Objectives | 46.5 | engineering | software | 7/10 | 0 |
| #9 | P.O BOX | 43.9 | admin | admin | 7/10 | 0 |
| #10 | ZOE THOMPSON | 43.6 | engineering | software | 3/10 | 6 |
| #11 | Frederick Chen | 43.1 | education | education | 7/10 | 0 |
| #12 | MEHTA PANKAJ KUMAR PUNASHANKAR | 43.0 | engineering | software | 8/10 | 0 |
| #13 | TANVEER RAZA | 42.9 | engineering | software | 8/10 | 0 |
| #14 | JULIA | 42.2 | engineering | software | 7/10 | 5 |
| #15 | Thiruvallam P.O | 41.5 | engineering | software | 7/10 | 0 |
| #16 | CARRIER OBJECTIVES | 41.5 | engineering | software | 7/10 | 0 |
| #17 | MOHD RASHID | 41.1 | engineering | software | 7/10 | 8 |
| #18 | Chicago | 41.1 | engineering | software | 7/10 | 3 |
| #19 | It Management | 40.5 | engineering | software | 7/10 | 0 |
| #20 | Career Objective:- | 40.5 | engineering | software | 7/10 | 0 |

### Fullstack Engineer
Total candidates: 298

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 83.2 | engineering | software | 8/9 | 10 |
| #2 | ZOE THOMPSON | 67.7 | engineering | software | 7/9 | 6 |
| #3 | Harper Garcia | 65.3 | engineering | software | 4/9 | 9 |
| #4 | Database Programmer/Analyst (. | 57.6 | engineering | software | 7/9 | 1 |
| #5 | It Consultant | 54.4 | engineering | software | 6/9 | 6 |
| #6 | Souvik Karmakar | 53.3 | engineering | software | 7/9 | 0 |
| #7 | Database Programmer/Analyst (. | 52.5 | engineering | software | 6/9 | 0 |
| #8 | & Analyst Ml | 50.1 | engineering | software | 6/9 | 7 |
| #9 | Akila Palanimuthu | 47.9 | engineering | software | 5/9 | 0 |
| #10 | JULIA | 47.4 | engineering | software | 6/9 | 5 |
| #11 | Objectives | 45.3 | engineering | software | 6/9 | 0 |
| #12 | It Management | 45.3 | engineering | software | 6/9 | 0 |
| #13 | KEISUKE YAMAMOTO | 43.6 | engineering | software | 7/9 | 0 |
| #14 | Chicago | 42.1 | engineering | software | 6/9 | 3 |
| #15 | Puja Deshmukh | 41.8 | engineering | software | 5/9 | 0 |
| #16 | SARATH KS | 41.4 | engineering | software | 5/9 | 0 |
| #17 | CARRIER OBJECTIVES | 41.2 | engineering | software | 5/9 | 0 |
| #18 | P.O BOX | 41.1 | admin | admin | 4/9 | 0 |
| #19 | Career Objective:- | 40.9 | engineering | software | 5/9 | 0 |
| #20 | TANVEER RAZA | 40.8 | engineering | software | 5/9 | 0 |

### DevOps Engineer
Total candidates: 371

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | VICTORIA BAKER | 85.9 | engineering | devops | 7/9 | 6 |
| #2 | Amit Sharma | 72.2 | engineering | software | 7/9 | 12 |
| #3 | Neha Singh | 70.3 | engineering | software | 6/9 | 11 |
| #4 | ANURADHA K | 66.7 | engineering | devops | 8/9 | 0 |
| #5 | Rahul Gupta | 65.1 | engineering | software | 6/9 | 12 |
| #6 | Shalini Nair | 62.6 | engineering | data | 5/9 | 12 |
| #7 | Ananya Desai | 61.2 | engineering | data | 5/9 | 11 |
| #8 | ZOE THOMPSON | 60.7 | engineering | software | 6/9 | 6 |
| #9 | Priya Pa | 59.4 | engineering | data | 3/9 | 11 |
| #10 | Joseline | 57.0 | engineering | ml | 8/9 | 7 |
| #11 | Kiran Malhotra | 56.1 | engineering | data | 3/9 | 12 |
| #12 | Rohan Mehra | 56.1 | engineering | data | 3/9 | 11 |
| #13 | Vikram Rao | 52.9 | engineering | data | 3/9 | 12 |
| #14 | Aditya Joshi | 50.8 | engineering | data | 3/9 | 11 |
| #15 | Master Data Manager | 49.6 | sales | sales | 5/9 | 5 |
| #16 | Passed Year Class | 43.8 | healthcare | healthcare | 2/9 | 0 |
| #17 | Objectives | 43.3 | education | education | 3/9 | 0 |
| #18 | Asp.Net Web Developer | 43.3 | engineering | software | 3/9 | 14 |
| #19 | Pavithra Shetty | 42.8 | engineering | software | 4/9 | 11 |
| #20 | Objectives | 42.6 | engineering | software | 5/9 | 0 |

### Data Engineer
Total candidates: 407

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Ananya Desai | 94.8 | engineering | data | 8/9 | 11 |
| #2 | Rohan Mehra | 94.8 | engineering | data | 8/9 | 11 |
| #3 | Aditya Joshi | 92.9 | engineering | data | 8/9 | 11 |
| #4 | Shalini Nair | 90.8 | engineering | data | 7/9 | 12 |
| #5 | Priya Pa | 90.3 | engineering | data | 7/9 | 11 |
| #6 | Kiran Malhotra | 84.0 | engineering | data | 6/9 | 12 |
| #7 | Neha Singh | 81.3 | engineering | software | 7/9 | 11 |
| #8 | Vikram Rao | 81.1 | engineering | data | 5/9 | 12 |
| #9 | Amit Sharma | 73.8 | engineering | software | 6/9 | 12 |
| #10 | John Smith | 70.3 | engineering | data | 6/9 | 5 |
| #11 | Rahul Gupta | 68.1 | engineering | software | 5/9 | 12 |
| #12 | Master Data Manager | 55.3 | sales | sales | 5/9 | 5 |
| #13 | JEROME PELINSKY | 50.3 | engineering | software | 3/9 | 6 |
| #14 | ZOE THOMPSON | 46.6 | engineering | software | 2/9 | 6 |
| #15 | Owen Machine | 44.8 | engineering | software | 3/9 | 6 |
| #16 | Pavithra Shetty | 44.3 | engineering | software | 2/9 | 11 |
| #17 | ALEXIS | 43.9 | engineering | ml | 1/9 | 6 |
| #18 | GRANT | 42.3 | engineering | software | 2/9 | 7 |
| #19 | Mashad Abbas | 42.0 | engineering | data | 2/9 | 0 |
| #20 | MARCUS HALL | 41.3 | engineering | software | 5/9 | 10 |

### Data Scientist
Total candidates: 391

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Kiran Malhotra | 77.1 | engineering | data | 7/8 | 12 |
| #2 | Priya Pa | 74.9 | engineering | data | 8/8 | 11 |
| #3 | Ananya Desai | 73.0 | engineering | data | 8/8 | 11 |
| #4 | Shalini Nair | 73.0 | engineering | data | 7/8 | 12 |
| #5 | Rohan Mehra | 71.4 | engineering | data | 8/8 | 11 |
| #6 | Vikram Rao | 71.2 | engineering | data | 7/8 | 12 |
| #7 | Rahul Gupta | 71.1 | engineering | software | 7/8 | 12 |
| #8 | Aditya Joshi | 69.5 | engineering | data | 8/8 | 11 |
| #9 | Joseline | 69.4 | engineering | ml | 8/8 | 7 |
| #10 | Amit Sharma | 68.2 | engineering | software | 7/8 | 12 |
| #11 | Pavithra Shetty | 67.6 | engineering | software | 8/8 | 11 |
| #12 | Evelynn Graduate Curriculars | 64.3 | engineering | ml | 7/8 | 0 |
| #13 | LISA JENNINGS | 63.7 | engineering | data | 8/8 | 0 |
| #14 | Daniel | 62.8 | engineering | data | 8/8 | 7 |
| #15 | Neha Singh | 61.3 | engineering | software | 8/8 | 11 |
| #16 | MASON | 60.4 | engineering | ml | 8/8 | 7 |
| #17 | SaiKo Computation | 59.7 | engineering | ml | 6/8 | 0 |
| #18 | John Smith | 59.4 | engineering | data | 7/8 | 5 |
| #19 | LANDO | 58.7 | engineering | data | 7/8 | 2 |
| #20 | GRANT | 58.2 | engineering | software | 8/8 | 7 |

### ML Engineer
Total candidates: 388

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Amit Sharma | 73.7 | engineering | software | 7/8 | 12 |
| #2 | Rahul Gupta | 72.9 | engineering | software | 6/8 | 12 |
| #3 | Ananya Desai | 67.8 | engineering | data | 5/8 | 11 |
| #4 | Kiran Malhotra | 66.4 | engineering | data | 5/8 | 12 |
| #5 | Joseline | 66.3 | engineering | ml | 7/8 | 7 |
| #6 | Rohan Mehra | 63.6 | engineering | data | 5/8 | 11 |
| #7 | Vikram Rao | 61.5 | engineering | data | 4/8 | 12 |
| #8 | Priya Pa | 60.7 | engineering | data | 5/8 | 11 |
| #9 | Shalini Nair | 59.4 | engineering | data | 4/8 | 12 |
| #10 | Neha Singh | 56.6 | engineering | software | 5/8 | 11 |
| #11 | Aditya Joshi | 55.2 | engineering | data | 4/8 | 11 |
| #12 | Evelynn Graduate Curriculars | 52.8 | engineering | ml | 4/8 | 0 |
| #13 | Pavithra Shetty | 48.4 | engineering | software | 4/8 | 11 |
| #14 | MASON | 48.2 | engineering | ml | 6/8 | 7 |
| #15 | VICTORIA BAKER | 47.1 | engineering | devops | 4/8 | 6 |
| #16 | ALEXIS | 45.8 | engineering | ml | 3/8 | 6 |
| #17 | Learning Engineer | 45.7 | engineering | ml | 4/8 | 7 |
| #18 | Owen Machine | 44.9 | engineering | software | 4/8 | 6 |
| #19 | & Analyst Ml | 44.6 | engineering | software | 4/8 | 7 |
| #20 | MARIANA | 44.3 | engineering | ml | 5/8 | 0 |

### Marketing Manager
Total candidates: 314

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ELIJAH BROWN | 100.0 | marketing | marketing | 7/7 | 8 |
| #2 | LIAM | 97.5 | marketing | marketing | 7/7 | 3 |
| #3 | Founder/Strategic Account Dire | 73.7 | marketing | marketing | 6/7 | 11 |
| #4 | Business Systems Analyst I | 71.8 | marketing | marketing | 7/7 | 12 |
| #5 | Christopher Fowler | 69.8 | marketing | marketing | 7/7 | 0 |
| #6 | Anand Street | 69.5 | marketing | marketing | 7/7 | 0 |
| #7 | Christopher Fowler | 68.2 | marketing | marketing | 6/7 | 0 |
| #8 | Vice President | 67.3 | marketing | marketing | 6/7 | 11 |
| #9 | Leasing Consultant | 66.0 | accounting | accounting | 6/7 | 13 |
| #10 | Property Management Assistant | 64.7 | marketing | marketing | 5/7 | 12 |
| #11 | Bablu Kumar Yadav | 62.7 | marketing | marketing | 7/7 | 0 |
| #12 | Ananya Desai | 57.5 | engineering | data | 6/7 | 11 |
| #13 | Marketing Coordinator | 55.4 | marketing | marketing | 3/7 | 5 |
| #14 | Rohan Mehra | 54.7 | engineering | data | 6/7 | 11 |
| #15 | Google Analytics. Ex | 54.6 | marketing | marketing | 5/7 | 2 |
| #16 | SEBASTIAN MARTIN | 54.5 | sales | sales | 5/7 | 12 |
| #17 | Shabina P | 54.2 | marketing | marketing | 5/7 | 0 |
| #18 | Shabina P | 54.2 | marketing | marketing | 5/7 | 0 |
| #19 | It Management | 53.9 | engineering | software | 6/7 | 0 |
| #20 | BTech SNGIST NORTH | 53.2 | marketing | marketing | 6/7 | 0 |

### Sales Executive
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ISAAC HALL | 90.4 | sales | sales | 5/5 | 9 |
| #2 | PRAKASH PINDARI | 80.3 | sales | sales | 5/5 | 0 |
| #3 | MAHAMMADJUBER M. PATEL | 79.6 | sales | sales | 5/5 | 14 |
| #4 | Core Compentencies | 73.9 | sales | sales | 5/5 | 9 |
| #5 | SEBASTIAN MARTIN | 73.1 | sales | sales | 5/5 | 12 |
| #6 | Dheeraj S. Sharma | 73.0 | sales | sales | 5/5 | 0 |
| #7 | MS Office | 72.5 | sales | sales | 5/5 | 11 |
| #8 | Shahadat Hussain | 72.4 | sales | sales | 5/5 | 0 |
| #9 | Mail Id | 72.2 | sales | sales | 5/5 | 14 |
| #10 | Mohd Abid Ahmad Siddiqui | 71.2 | sales | sales | 5/5 | 12 |
| #11 | SALIK SHAIKH | 71.1 | sales | sales | 5/5 | 0 |
| #12 | Shahriar Saaed Niazi | 70.8 | sales | sales | 5/5 | 0 |
| #13 | Rajaneesh Kumar Singh Janwar | 69.8 | marketing | marketing | 5/5 | 0 |
| #14 | Geoffrey Makoe | 69.6 | hospitality | hospitality | 5/5 | 14 |
| #15 | Mohammed Imran Khan | 68.2 | marketing | marketing | 5/5 | 0 |
| #16 | Customer Service. | 67.1 | healthcare | healthcare | 5/5 | 11 |
| #17 | Oman Career Software | 66.7 | sales | sales | 5/5 | 0 |
| #18 | SHOIAB KHAN | 66.4 | sales | sales | 5/5 | 0 |
| #19 | Master Data Manager | 66.2 | sales | sales | 5/5 | 5 |
| #20 | Sagar Talreja | 66.1 | sales | sales | 5/5 | 2 |

### HR Manager
Total candidates: 268

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | J.KRISHNAMOORTHY | 78.9 | healthcare | healthcare | 6/6 | 0 |
| #2 | Human Resources Supervisor | 77.3 | hr | hr | 6/6 | 11 |
| #3 | Customer Service. | 75.6 | healthcare | healthcare | 6/6 | 11 |
| #4 | Bhola Nagar | 69.6 | hr | hr | 5/6 | 1 |
| #5 | Aviation Electronics Technicia | 68.9 | hr | hr | 5/6 | 13 |
| #6 | Mohammed Hidayath | 68.3 | hr | hr | 6/6 | 0 |
| #7 | Radha HG | 66.3 | hr | hr | 5/6 | 9 |
| #8 | UPADHYAY | 64.7 | hospitality | hospitality | 6/6 | 0 |
| #9 | NOOR MOHAMED. | 63.7 | healthcare | healthcare | 5/6 | 2 |
| #10 | Aviation Maintainer | 62.6 | sales | sales | 4/6 | 11 |
| #11 | ZAFER HUSSAIN | 62.2 | legal | legal | 6/6 | 0 |
| #12 | Mohd Ameen Khan | 62.2 | hr | hr | 3/6 | 0 |
| #13 | CUSTOMER SERVICE REP | 61.7 | healthcare | healthcare | 4/6 | 13 |
| #14 | MUHAMME HASIF PP | 61.4 | hr | hr | 4/6 | 0 |
| #15 | "GULAM ROSHAN ZAMEER" | 61.3 | hr | hr | 3/6 | 0 |
| #16 | AIRCRAFT SALES | 60.5 | sales | sales | 4/6 | 13 |
| #17 | Lawrence Swift | 59.4 | healthcare | healthcare | 3/6 | 0 |
| #18 | Premananda Das | 59.2 | admin | admin | 3/6 | 0 |
| #19 | M Priyadharsini | 59.0 | hr | hr | 3/6 | 0 |
| #20 | SUBHADIP MONDAL | 58.9 | hr | hr | 3/6 | 0 |

### Accountant
Total candidates: 378

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Abhishek Kumar | 85.5 | accounting | accounting | 5/7 | 13 |
| #2 | ATHAVUL JAWAD S.M | 84.9 | accounting | accounting | 6/7 | 0 |
| #3 | Baraa Al-Jabi | 77.0 | accounting | accounting | 6/7 | 0 |
| #4 | Resume for the Post of Account | 74.4 | accounting | accounting | 6/7 | 0 |
| #5 | Dilshad Garden | 74.4 | accounting | accounting | 6/7 | 10 |
| #6 | Sammy Musungu | 72.4 | accounting | accounting | 6/7 | 0 |
| #7 | BASIL P BAVA | 72.0 | accounting | accounting | 5/7 | 4 |
| #8 | PRIYANKA SANGANERIA GUPTA | 71.9 | accounting | accounting | 6/7 | 0 |
| #9 | UAE) | 70.9 | accounting | accounting | 5/7 | 4 |
| #10 | ABIGAIL HALL | 70.7 | accounting | accounting | 5/7 | 3 |
| #11 | Saurabh Kishorbhai Seta | 69.9 | accounting | accounting | 5/7 | 0 |
| #12 | ABU RAIS SIDDIQUI | 68.3 | finance | finance | 6/7 | 0 |
| #13 | ROBAI | 68.0 | accounting | accounting | 5/7 | 0 |
| #14 | APARNA BHANU | 67.3 | accounting | accounting | 5/7 | 2 |
| #15 | Educational Qualification | 66.0 | sales | sales | 6/7 | 0 |
| #16 | V.P.O. Nangal Bhur | 65.8 | accounting | accounting | 6/7 | 0 |
| #17 | Covering Letter | 65.1 | accounting | accounting | 4/7 | 6 |
| #18 | Master Data Manager | 65.0 | sales | sales | 7/7 | 5 |
| #19 | CA. SONA A. DEVASSY | 64.7 | accounting | accounting | 5/7 | 0 |
| #20 | Ayman Zarrouq | 64.3 | accounting | accounting | 5/7 | 12 |

### Civil Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Ramkumar Kasilingam | 62.4 | construction | construction | 3/7 | 0 |
| #2 | RAJESH K R | 61.8 | healthcare | healthcare | 4/7 | 0 |
| #3 | Civil Engineer | 57.2 | construction | construction | 3/7 | 6 |
| #4 | Anna Cad | 57.0 | construction | construction | 3/7 | 5 |
| #5 | RAJESH K R | 56.1 | healthcare | healthcare | 4/7 | 0 |
| #6 | SURESH KUMAR MAHENDRAN | 55.7 | construction | construction | 3/7 | 0 |
| #7 | SURESH KUMAR MAHENDRAN | 54.1 | construction | construction | 3/7 | 0 |
| #8 | SAURABH SAXENA | 53.6 | construction | construction | 2/7 | 0 |
| #9 | Passed Year Class | 52.2 | healthcare | healthcare | 3/7 | 0 |
| #10 | G S SUBRAHMANYA VARMA | 52.1 | unknown | unknown | 3/7 | 0 |
| #11 | ABBAS MANTHIRI. U | 51.6 | construction | construction | 2/7 | 0 |
| #12 | Khalid Othman | 51.6 | construction | construction | 4/7 | 12 |
| #13 | LOGACHANDIRANE R | 51.4 | construction | construction | 1/7 | 6 |
| #14 | B.Mohamed Hamdhan | 51.2 | healthcare | healthcare | 3/7 | 0 |
| #15 | Jayakumar Murugesan | 50.5 | construction | construction | 3/7 | 0 |
| #16 | Nagar Extension | 50.5 | construction | construction | 3/7 | 0 |
| #17 | ARUMUGAM BALA | 50.4 | construction | construction | 3/7 | 5 |
| #18 | Engineering Softwares. | 50.2 | hr | hr | 3/7 | 0 |
| #19 | DR.R. Pradheep Kumar | 50.1 | legal | legal | 2/7 | 0 |
| #20 | MOHD AAMIR | 49.7 | construction | construction | 3/7 | 0 |

### Electrical Engineer
Total candidates: 298

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Electrical Engineer | 67.5 | construction | construction | 4/7 | 13 |
| #2 | ISHTIAQUE KAZMI | 65.0 | healthcare | healthcare | 2/7 | 2 |
| #3 | MD REHAN AHMAD | 64.1 | construction | construction | 1/7 | 13 |
| #4 | Passed Year Class | 62.5 | healthcare | healthcare | 4/7 | 0 |
| #5 | E K T | 61.2 | healthcare | healthcare | 1/7 | 0 |
| #6 | Anil Paudel | 60.1 | healthcare | healthcare | 2/7 | 0 |
| #7 | Sadam Hussain S | 60.1 | sales | sales | 3/7 | 0 |
| #8 | AKHLAKUR RAHMAN | 58.3 | construction | construction | 2/7 | 0 |
| #9 | RAJA PAULRAJ | 57.7 | construction | construction | 3/7 | 8 |
| #10 | Karguvel Raja | 57.5 | healthcare | healthcare | 3/7 | 14 |
| #11 | Nagaraj.P | 56.7 | healthcare | healthcare | 3/7 | 0 |
| #12 | Working Rf Systems Engineer | 56.4 | engineering | electrical | 2/7 | 14 |
| #13 | SUKHVINDER SINGH | 54.2 | healthcare | healthcare | 1/7 | 0 |
| #14 | MOHAMMAD AZHAR IMAM | 54.1 | construction | construction | 1/7 | 0 |
| #15 | BALAJI LOGANATHAN | 53.4 | healthcare | healthcare | 2/7 | 0 |
| #16 | Mohammad Fahimuddin | 51.7 | healthcare | healthcare | 0/7 | 3 |
| #17 | RELIANCE UTILITIES & POWER LIM | 50.3 | healthcare | healthcare | 0/7 | 0 |
| #18 | ABDULLA MEEZAN BATCHA M.I | 50.0 | healthcare | healthcare | 0/7 | 0 |
| #19 | ProfessionalProfessional Overv | 48.5 | healthcare | healthcare | 1/7 | 0 |
| #20 | Vanmikinathan K | 48.4 | healthcare | healthcare | 1/7 | 0 |

### Mechanical Engineer
Total candidates: 356

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | JOHNS K ABRAHAM | 75.6 | healthcare | healthcare | 6/7 | 0 |
| #2 | Kesava Career Work | 63.1 | healthcare | healthcare | 4/7 | 0 |
| #3 | GYANESH GULSHAN | 60.4 | sales | sales | 4/7 | 11 |
| #4 | Prasaath Balachandran | 57.8 | sales | sales | 3/7 | 0 |
| #5 | Rakesh Singh Bisht | 57.3 | education | education | 5/7 | 6 |
| #6 | Electrical Engineer | 56.2 | construction | construction | 4/7 | 13 |
| #7 | Siddharth Aggarwal | 54.4 | legal | legal | 3/7 | 0 |
| #8 | Sagar Baburao Bhadange | 53.1 | healthcare | healthcare | 1/7 | 0 |
| #9 | Working Rf Systems Engineer | 52.6 | engineering | electrical | 1/7 | 14 |
| #10 | AQEEL AHMED | 52.3 | construction | construction | 2/7 | 1 |
| #11 | Aasif Khan | 51.6 | healthcare | healthcare | 3/7 | 0 |
| #12 | The Mathworks MATLAB | 51.1 | education | education | 1/7 | 12 |
| #13 | R. Harinath | 50.9 | healthcare | healthcare | 3/7 | 0 |
| #14 | S.HASSANATH MUKTHAR | 50.5 | healthcare | healthcare | 4/7 | 0 |
| #15 | Khalid Othman | 50.3 | construction | construction | 2/7 | 12 |
| #16 | MECHANICAL ENGINEER (M.Tech) | 50.0 | education | education | 0/7 | 0 |
| #17 | Sadulpur Churu | 50.0 | construction | construction | 0/7 | 11 |
| #18 | E- Mail | 49.2 | healthcare | healthcare | 1/7 | 14 |
| #19 | SUMEET MAHAJAN | 48.9 | healthcare | healthcare | 3/7 | 0 |
| #20 | Saravanan L | 48.8 | healthcare | healthcare | 3/7 | 2 |

### Legal Advisor
Total candidates: 312

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | John Smith | 72.1 | legal | legal | 4/5 | 6 |
| #2 | Working Rf Systems Engineer | 62.3 | engineering | electrical | 4/5 | 14 |
| #3 | MUYALA EDWARD | 60.3 | legal | legal | 3/5 | 0 |
| #4 | Marketing And Communications D | 59.8 | marketing | marketing | 5/5 | 0 |
| #5 | Information Technology Provisi | 58.4 | legal | legal | 4/5 | 14 |
| #6 | Human Resources Supervisor | 57.5 | hr | hr | 4/5 | 11 |
| #7 | Substitute Teacher | 56.4 | legal | legal | 3/5 | 14 |
| #8 | Shabina P | 55.3 | marketing | marketing | 4/5 | 0 |
| #9 | Shabina P | 55.3 | marketing | marketing | 4/5 | 0 |
| #10 | ZAFER HUSSAIN | 54.3 | legal | legal | 3/5 | 0 |
| #11 | J.KRISHNAMOORTHY | 53.5 | healthcare | healthcare | 4/5 | 0 |
| #12 | The Mathworks MATLAB | 53.1 | education | education | 4/5 | 12 |
| #13 | Geoffrey Makoe | 52.2 | hospitality | hospitality | 4/5 | 14 |
| #14 | Aviation Supply Technician | 51.4 | healthcare | healthcare | 4/5 | 11 |
| #15 | DR.R. Pradheep Kumar | 49.8 | legal | legal | 4/5 | 0 |
| #16 | DEEPAK NAIR | 46.8 | engineering | software | 4/5 | 0 |
| #17 | Master Data Manager | 46.5 | sales | sales | 3/5 | 5 |
| #18 | MOHAMEDMUSTHAFA. | 46.2 | hospitality | hospitality | 3/5 | 0 |
| #19 | Customer Service. | 46.2 | healthcare | healthcare | 3/5 | 11 |
| #20 | NOOR MOHAMED. | 45.9 | healthcare | healthcare | 2/5 | 2 |

### Healthcare Specialist
Total candidates: 233

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Bank Teller | 74.5 | sales | sales | 6/6 | 15 |
| #2 | DR.SANTOSH KAKADE | 59.7 | healthcare | healthcare | 4/6 | 0 |
| #3 | Aviation Safety Assistant | 57.4 | healthcare | healthcare | 4/6 | 4 |
| #4 | DCPT | 54.5 | healthcare | healthcare | 0/6 | 0 |
| #5 | Customer Service. | 53.7 | healthcare | healthcare | 2/6 | 11 |
| #6 | Substitute Teacher | 53.3 | education | education | 0/6 | 12 |
| #7 | MOHAMMAD ASAD. | 52.4 | healthcare | healthcare | 5/6 | 0 |
| #8 | Qualification Dob Sex | 51.3 | healthcare | healthcare | 4/6 | 3 |
| #9 | Senior Warrant Officer Advisor | 51.1 | admin | admin | 1/6 | 0 |
| #10 | Dr. Ankit Patel | 48.8 | healthcare | healthcare | 1/6 | 3 |
| #11 | JULIE MONROE | 48.6 | healthcare | healthcare | 2/6 | 9 |
| #12 | ID NO | 48.6 | healthcare | healthcare | 2/6 | 0 |
| #13 | Information Technology (Intern | 47.4 | healthcare | healthcare | 2/6 | 4 |
| #14 | CRAIG C. McKIRGAN | 45.8 | healthcare | healthcare | 1/6 | 0 |
| #15 | B.PRASATH | 45.6 | healthcare | healthcare | 0/6 | 10 |
| #16 | Preschool Teacher | 45.0 | education | education | 3/6 | 11 |
| #17 | Adobe Reader Microsoft Office | 44.9 | admin | admin | 4/6 | 13 |
| #18 | Company Name | 44.5 | education | education | 3/6 | 12 |
| #19 | Leasing Consultant | 44.0 | accounting | accounting | 2/6 | 13 |
| #20 | RAJINDER KUMAR | 43.5 | healthcare | healthcare | 3/6 | 0 |

### Teacher
Total candidates: 243

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | English Teacher | 91.2 | education | education | 4/4 | 7 |
| #2 | Assistant Teacher | 83.0 | education | education | 2/4 | 12 |
| #3 | RISHA SRITHARAN | 75.2 | education | education | 2/4 | 0 |
| #4 | U. Jagadeeswari | 70.9 | education | education | 2/4 | 0 |
| #5 | Marilyn Hunter | 70.8 | education | education | 1/4 | 8 |
| #6 | Information Technology Analyst | 69.7 | education | education | 2/4 | 5 |
| #7 | Preschool Teacher | 69.2 | education | education | 1/4 | 11 |
| #8 | Master Teacher | 68.9 | education | education | 1/4 | 1 |
| #9 | Reading Teacher | 68.4 | education | education | 2/4 | 11 |
| #10 | Company Name | 67.9 | education | education | 1/4 | 12 |
| #11 | Guest Teacher | 67.8 | education | education | 1/4 | 8 |
| #12 | Assistant Teacher | 66.6 | education | education | 1/4 | 1 |
| #13 | Kpandipou Koffi | 66.5 | education | education | 2/4 | 3 |
| #14 | Pre-Service Teacher | 64.4 | education | education | 2/4 | 2 |
| #15 | Communications Magna Cum Laude | 62.4 | education | education | 1/4 | 8 |
| #16 | Sam Pronove | 62.3 | education | education | 0/4 | 0 |
| #17 | Preschool Teacher | 62.1 | education | education | 1/4 | 12 |
| #18 | History Teacher | 61.1 | education | education | 0/4 | 6 |
| #19 | MS Office MS Office | 61.1 | education | education | 0/4 | 12 |
| #20 | Robyn Goss | 57.4 | education | education | 1/4 | 0 |

### Hotel Manager
Total candidates: 108

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Marketing Coordinator | 55.2 | marketing | marketing | 1/4 | 5 |
| #2 | SALIK SHAIKH | 49.4 | sales | sales | 1/4 | 0 |
| #3 | CONSULTANT TO OWNER | 48.6 | healthcare | healthcare | 1/4 | 0 |
| #4 | UPADHYAY | 45.2 | hospitality | hospitality | 1/4 | 0 |
| #5 | Geoffrey Makoe | 44.3 | hospitality | hospitality | 0/4 | 14 |
| #6 | Mohammad | 44.0 | hospitality | hospitality | 1/4 | 0 |
| #7 | Google Analytics. Ex | 40.7 | marketing | marketing | 1/4 | 2 |
| #8 | MS Office MS Office | 40.3 | education | education | 1/4 | 12 |
| #9 | Esther Scott | 39.9 | hospitality | hospitality | 0/4 | 0 |
| #10 | Sabique Hasan | 39.7 | hospitality | hospitality | 0/4 | 0 |
| #11 | Substitute Teacher | 39.6 | education | education | 1/4 | 12 |
| #12 | APPLECARE CPU ADVISOR | 37.3 | sales | sales | 0/4 | 12 |
| #13 | TANVEER RAZA | 36.6 | engineering | software | 0/4 | 0 |
| #14 | SAYYED SHAIFAL ABBAS | 36.6 | marketing | marketing | 1/4 | 0 |
| #15 | Mother Tongue | 35.7 | education | education | 1/4 | 0 |
| #16 | Assistant Teacher | 35.4 | hospitality | hospitality | 1/4 | 7 |
| #17 | NOOR MOHAMED. | 35.4 | healthcare | healthcare | 1/4 | 2 |
| #18 | MS Office | 35.3 | sales | sales | 0/4 | 11 |
| #19 | MARCUS HALL | 34.5 | engineering | software | 1/4 | 10 |
| #20 | Vice President | 34.3 | marketing | marketing | 0/4 | 11 |

### Construction Manager
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Ramkumar Kasilingam | 79.5 | construction | construction | 3/4 | 0 |
| #2 | AQEEL AHMED | 79.4 | construction | construction | 4/4 | 1 |
| #3 | Construction Consultant | 76.6 | construction | construction | 3/4 | 8 |
| #4 | Jayakumar Murugesan | 74.2 | construction | construction | 3/4 | 0 |
| #5 | SURESH KUMAR MAHENDRAN | 72.9 | construction | construction | 2/4 | 0 |
| #6 | Naman Gala | 70.8 | sales | sales | 1/4 | 4 |
| #7 | Khalid Othman | 70.1 | construction | construction | 3/4 | 12 |
| #8 | Ata Ur Rahman | 69.9 | hospitality | hospitality | 3/4 | 0 |
| #9 | SURESH KUMAR MAHENDRAN | 69.1 | construction | construction | 2/4 | 0 |
| #10 | SUKHVINDER SINGH | 68.8 | healthcare | healthcare | 2/4 | 0 |
| #11 | Anna Cad | 67.9 | construction | construction | 3/4 | 5 |
| #12 | B.Mohamed Hamdhan | 67.9 | healthcare | healthcare | 2/4 | 0 |
| #13 | MD REHAN AHMAD | 67.7 | construction | construction | 3/4 | 13 |
| #14 | Deepak Nair | 66.7 | construction | construction | 2/4 | 2 |
| #15 | Mob No. | 64.3 | construction | construction | 2/4 | 0 |
| #16 | ARUMUGAM BALA | 63.4 | construction | construction | 2/4 | 5 |
| #17 | SHAIK SAHUL HAMEED AZEEM.A | 63.4 | sales | sales | 2/4 | 5 |
| #18 | G S SUBRAHMANYA VARMA | 62.8 | unknown | unknown | 2/4 | 0 |
| #19 | RAJA PAULRAJ | 61.9 | construction | construction | 2/4 | 8 |
| #20 | NIKHIL ARORA | 61.7 | construction | construction | 3/4 | 1 |

### Office Admin
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | History Teacher | 83.5 | education | education | 4/4 | 6 |
| #2 | Bank Teller | 78.3 | sales | sales | 2/4 | 15 |
| #3 | Godwin Opati Sitati | 73.2 | finance | finance | 3/4 | 0 |
| #4 | J.KRISHNAMOORTHY | 70.3 | healthcare | healthcare | 2/4 | 0 |
| #5 | Aviation Maintainer | 69.1 | sales | sales | 2/4 | 11 |
| #6 | Premananda Das | 69.1 | admin | admin | 2/4 | 0 |
| #7 | MUHAMMAD. | 67.0 | admin | admin | 1/4 | 0 |
| #8 | Aviation Safety Assistant | 62.5 | healthcare | healthcare | 2/4 | 4 |
| #9 | CAREER GOALS | 61.5 | admin | admin | 1/4 | 0 |
| #10 | APPLECARE CPU ADVISOR | 60.7 | sales | sales | 3/4 | 12 |
| #11 | Operations Manager | 57.3 | hr | hr | 2/4 | 13 |
| #12 | Fast Food Restaurant Manager | 56.5 | healthcare | healthcare | 2/4 | 14 |
| #13 | Viju Pisharody | 56.3 | admin | admin | 1/4 | 5 |
| #14 | MUNEEB AHMAD | 55.6 | hr | hr | 1/4 | 0 |
| #15 | Management And Program Analysi | 54.5 | sales | sales | 2/4 | 8 |
| #16 | Production Associate | 54.5 | healthcare | healthcare | 2/4 | 6 |
| #17 | SWAPNA.C.S | 54.0 | finance | finance | 0/4 | 12 |
| #18 | FAIZAN ALI | 53.9 | accounting | accounting | 2/4 | 0 |
| #19 | A N A A | 53.8 | accounting | accounting | 2/4 | 4 |
| #20 | PAUL WANJALA WEKESA | 53.3 | healthcare | healthcare | 2/4 | 2 |

---
## Phase 5 — False Positive Audit (3-Tier)
- **True FP Count**: 18
- **True FP Rate**: 9.0%
- **Formula**: 18 / (20 × 10)
- **Related-Domain Count**: 6
- **Same-Domain Count**: 1
- **All-inclusive FP Rate**: 12.5%

### True FP Cases (wrong domain entirely)
| JD | Name | Score | Domain | Sub-Domain | Tier | Reason |
|----|------|-------|--------|------------|------|--------|
| Frontend Engineer | P.O BOX | 43.9 | admin | admin | true_fp | admin candidate in software JD 'Frontend Engineer' |
| Civil Engineer | RAJESH K R | 61.8 | healthcare | healthcare | true_fp | healthcare candidate in Civil Engineer JD |
| Civil Engineer | RAJESH K R | 56.1 | healthcare | healthcare | true_fp | healthcare candidate in Civil Engineer JD |
| Civil Engineer | Passed Year Class | 52.2 | healthcare | healthcare | true_fp | healthcare candidate in Civil Engineer JD |
| Electrical Engineer | ISHTIAQUE KAZMI | 65.0 | healthcare | healthcare | true_fp | healthcare candidate in Electrical Engineer JD |
| Electrical Engineer | Passed Year Class | 62.5 | healthcare | healthcare | true_fp | healthcare candidate in Electrical Engineer JD |
| Electrical Engineer | E K T | 61.2 | healthcare | healthcare | true_fp | healthcare candidate in Electrical Engineer JD |
| Electrical Engineer | Anil Paudel | 60.1 | healthcare | healthcare | true_fp | healthcare candidate in Electrical Engineer JD |
| Electrical Engineer | Sadam Hussain S | 60.1 | sales | sales | true_fp | sales candidate in Electrical Engineer JD |
| Electrical Engineer | Karguvel Raja | 57.5 | healthcare | healthcare | true_fp | healthcare candidate in Electrical Engineer JD |
| Mechanical Engineer | JOHNS K ABRAHAM | 75.6 | healthcare | healthcare | true_fp | healthcare candidate in Mechanical Engineer JD |
| Mechanical Engineer | Kesava Career Work | 63.1 | healthcare | healthcare | true_fp | healthcare candidate in Mechanical Engineer JD |
| Mechanical Engineer | GYANESH GULSHAN | 60.4 | sales | sales | true_fp | sales candidate in Mechanical Engineer JD |
| Mechanical Engineer | Prasaath Balachandran | 57.8 | sales | sales | true_fp | sales candidate in Mechanical Engineer JD |
| Mechanical Engineer | Rakesh Singh Bisht | 57.3 | education | education | true_fp | education candidate in Mechanical Engineer JD |
| Mechanical Engineer | Siddharth Aggarwal | 54.4 | legal | legal | true_fp | legal candidate in Mechanical Engineer JD |
| Mechanical Engineer | Sagar Baburao Bhadange | 53.1 | healthcare | healthcare | true_fp | healthcare candidate in Mechanical Engineer JD |
| Legal Advisor | Working Rf Systems Engine | 62.3 | engineering | electrical | true_fp | engineering candidate in non-eng JD 'Legal Advisor |

### Related-Domain Cases (not counted as FP)
| JD | Name | Score | Domain | Sub-Domain | Reason |
|----|------|-------|--------|------------|--------|
| Civil Engineer | Ramkumar Kasilingam | 62.4 | construction | construction | construction candidate in Civil Engineer (related) |
| Civil Engineer | Civil Engineer | 57.2 | construction | construction | construction candidate in Civil Engineer (related) |
| Civil Engineer | Anna Cad | 57.0 | construction | construction | construction candidate in Civil Engineer (related) |
| Civil Engineer | SURESH KUMAR MAHENDRAN | 55.7 | construction | construction | construction candidate in Civil Engineer (related) |
| Civil Engineer | SURESH KUMAR MAHENDRAN | 54.1 | construction | construction | construction candidate in Civil Engineer (related) |
| Civil Engineer | SAURABH SAXENA | 53.6 | construction | construction | construction candidate in Civil Engineer (related) |

### Same-Domain Cases (wrong subdomain)
| JD | Name | Score | Domain | Sub-Domain | Reason |
|----|------|-------|--------|------------|--------|
| Mechanical Engineer | Working Rf Systems Engine | 52.6 | engineering | electrical | engineering.electrical in Mechanical Engineer JD |

---
## Phase 6 — False Negative Audit
- **Count**: 155

| JD | Name | Domain | Sub-Domain | Skills | Overlap | Reason |
|----|------|--------|------------|--------|---------|--------|
| Backend Engineer | John Smith | engineering | data | 13 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Aditya Joshi | engineering | data | 19 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Amit Sharma | engineering | software | 26 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Ananya Desai | engineering | data | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Neha Singh | engineering | software | 23 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Kiran Malhotra | engineering | data | 19 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Rohan Mehra | engineering | data | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Priya Pa | engineering | data | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Rahul Gupta | engineering | software | 21 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Shalini Nair | engineering | data | 18 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Vikram Rao | engineering | data | 15 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | ZOE THOMPSON | engineering | software | 14 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Shanbagam Thanikachalam | engineering | software | 39 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | KEISUKE YAMAMOTO | engineering | software | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | NOLAN | engineering | software | 15 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Working Rf Systems Engine | engineering | electrical | 46 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Pavithra Shetty | engineering | software | 21 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Jose Curricular | engineering | software | 10 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | JACOB | engineering | software | 16 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | FRESHER | engineering | software | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | DANIEL GAN | engineering | software | 28 | 6 | Domain match + 6/10 skill overlap but not in  |
| Frontend Engineer | Thiruvallam P.O | engineering | software | 33 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Priya Elza | engineering | software | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Akila Palanimuthu | engineering | software | 33 | 4 | Domain match + 4/10 skill overlap but not in  |
| Frontend Engineer | MOHD RASHID | engineering | software | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | KEISUKE YAMAMOTO | engineering | software | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | MOHD. RASHID | engineering | software | 8 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Puja Deshmukh | engineering | software | 10 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | AMITENDRA GAURAV | engineering | software | 11 | 3 | Domain match + 3/10 skill overlap but not in  |

---
## Phase 6b — Domain Classification
- **Classified**: 95.3%
- **Formula**: `(2234 - 106) / 2234`
- **Unknown**: 106 (4.7%)

| Domain | Count | % | Avg Confidence |
|--------|-------|---|----------------|
| engineering | 582 | 26.1% | 0.722 |
| healthcare | 343 | 15.4% | 0.535 |
| insufficient_data | 325 | 14.5% | 0.0 |
| hr | 174 | 7.8% | 0.643 |
| education | 116 | 5.2% | 0.529 |
| marketing | 107 | 4.8% | 0.497 |
| accounting | 106 | 4.7% | 0.507 |
| unknown | 106 | 4.7% | 0.0 |
| sales | 97 | 4.3% | 0.453 |
| construction | 94 | 4.2% | 0.486 |
| legal | 87 | 3.9% | 0.539 |
| admin | 36 | 1.6% | 0.452 |
| finance | 32 | 1.4% | 0.495 |
| hospitality | 29 | 1.3% | 0.452 |

---
## Phase 7 — Performance
| PDFs | Extract | Rank | Per-PDF | Memory | Failures |
|------|---------|------|---------|--------|----------|
| 1 | 0.16s | 0.001s | 156.0ms | 424.7MB | 0 |
| 10 | 1.36s | 0.032s | 136.0ms | 454.5MB | 0 |
| 100 | 9.64s | 0.223s | 96.4ms | 513.1MB | 16 |
| 1000 | 136.63s | 1.777s | 136.6ms | 516.1MB | 372 |
| 3856 | 462.96s | N/A | 120.1ms | 516.1MB | 0 | (Phase 1 batch extraction data)

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

---
## V6 → V7 Comparison

| Category | V6 Score | V7 Score | Change | Status |
|----------|----------|----------|--------|--------|
| Extraction Quality | 69/100 | 72/100 | +3 | 🟢 +3 |
| Ranking Quality | 95/100 | 67/100 | -28 | 🔴 -28 |
| Knockout Reliability | 100/100 | 100/100 | +0 | ⚪ same |
| Domain Accuracy | 93/100 | 95/100 | +2 | 🟢 +2 |
| False Positive Control | 88/100 | 55/100 | -33 | 🔴 -33 |
| False Negative Control | 75/100 | 75/100 | +0 | ⚪ same |
| Performance | 100/100 | 80/100 | -20 | 🔴 -20 |
| **OVERALL** | **86/100** | **78/100** | **-8** | **🔴 -8** |

### V7 Changes Applied
- ✅ **Real CandidateScorer**: V6 used lightweight 3-dimension approximation. V7 uses production 7-dimension scorer.
- ✅ **Empty keyword fix**: `similarity.py` now returns 0.0 for empty keywords (was 100.0).
- ✅ **Weight redistribution**: Keyword weight redistributed to other dimensions when JD has no keywords.
- ✅ **Name extraction hardening**: Job title suffix + section header blacklists added to `contact_parser.py`.
- ✅ **Year validation**: `parse_date()` rejects years < 1900 or > 2100 (was crashing on year=0).
- ✅ **Pre-filter ranking**: Candidates pre-filtered by skill/keyword overlap before scoring (2972 → ~200-600/JD).
- ✅ **Threaded extraction**: 8-thread parallel PDF extraction.
- ✅ **Threaded scoring**: 4-thread parallel JD scoring.

### V6 Issues Audited in V7
| V6 Issue | V7 Status | Evidence |
|----------|-----------|----------|
| Score saturation (all ranks 60.0) | Fixed | Real scorer produces varied 7-dimension scores |
| Lightweight benchmark formula | Fixed | Using production CandidateScorer.rank() |
| Empty keyword = 100% inflation | Fixed | similarity.py returns 0.0 for empty keywords |
| Score clustering/ties | Fixed | Weight redistribution eliminates flat-score JDs |
| Year=0 crash in date parsing | Fixed | Year validation in parse_date() |
| Name extraction false positives | Improved | Job title + section header blacklists |
