# Benchmark v7 — Ranking Integrity & Truthfulness Report
Generated: 2026-06-23T20:29:22.622648
Version: 7.0.0

## Production Readiness Scorecard

| Category | Score | Weight | Formula |
|----------|-------|--------|---------|
| Extraction Quality | 69/100 █████████████░░░░░░░ | 25% | — |
| Ranking Quality | 69/100 █████████████░░░░░░░ | 20% | — |
| Knockout Reliability | 100/100 ████████████████████ | 15% | — |
| Domain Accuracy | 93/100 ██████████████████░░ | 15% | — |
| False Positive Control | 25/100 █████░░░░░░░░░░░░░░░ | 10% | — |
| False Negative Control | 75/100 ███████████████░░░░░ | 10% | — |
| Performance | 100/100 ████████████████████ | 5% | — |
| **OVERALL** | **75/100** | **100%** | |

### Verdict: 🟡 BETA READY

### Metric Formulas (Phase 4 Audit)
- Extraction composite: 0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email = 69.0
- Ranking: 69 domain-matched in top-5 across 20 JDs = 69/(20×5)
- Knockout: 3/3
- Domain: (5076 - 339) / 5076 = 93.3%
- FP: 30 / (20 × 10) = 15.0%
- FN: 200 cases

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
- **Composite Score**: 69.0/100
- **Formula**: `0.20*name + 0.25*skills + 0.25*experience + 0.20*education + 0.10*email`

### Field Extraction Rates
| Field | Present | Rate | Formula | Avg Count |
|-------|---------|------|---------|-----------|
| name | 2675 | 52.7% | 2675/5076 | - |
| email | 3809 | 75.0% | 3809/5076 | - |
| phone | 3734 | 73.6% | 3734/5076 | - |
| skills | 4653 | 91.7% | 4653/5076 | 13.9 |
| experience | 2546 | 50.2% | 2546/5076 | 3.9 |
| education | 3929 | 77.4% | 3929/5076 | 2.0 |
| projects | 610 | 12.0% | 610/5076 | - |
| certs | 793 | 15.6% | 793/5076 | - |

### Name Precision Audit
- **Valid names**: 2675
- **Blank names**: 2401
- **Blacklisted names**: 96
- **Name Precision**: 96.5%
- **Formula**: `2675/(2675+96)`
- **Confidence distribution**: {'high': 2337, 'medium': 242, 'low': 96, 'zero': 2401}

### Anomalies
- Tag leaks: 4
- Skill duplicates: 12
- Low quality: 348

---
## Phase 2.5 — Deduplication Audit
- **Total PDFs**: 5076
- **Unique PDFs (by SHA256)**: 3856
- **Exact duplicates**: 1220 (1051 groups)
- **Near duplicates**: 155 (123 groups)
- **Dedup rate**: 27.1%

### Exact Duplicate Samples
- `21a975187145...`: cv (1).pdf, cv (4837).pdf
- `b47c741903a1...`: cv (10).pdf, cv (4843).pdf
- `6c83556835bc...`: cv (1054).pdf, cv (1055).pdf
- `d89c849c0d18...`: cv (11).pdf, cv (4844).pdf
- `745cac622eea...`: cv (1170).pdf, cv (1171).pdf
### Near Duplicate Samples
- `132bb64f072b...`: cv (1002).pdf, cv (1220).pdf, cv (1393).pdf
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
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ZOE THOMPSON | 90.4 | engineering | Backend Engineer | 8/10 | 0 |
| #2 | Unknown Candidate | 83.8 | engineering |  | 9/10 | 0 |
| #3 | Rahul Gupta | 80.8 | engineering | Software Engineer | 9/10 | 3 |
| #4 | Amit Sharma | 73.7 | engineering | Software Engineer | 8/10 | 3 |
| #5 | Kiran Malhotra | 71.3 | engineering | Data Engineer | 7/10 | 3 |
| #6 | Vikram Rao | 68.6 | engineering | Data Engineer | 7/10 | 3 |
| #7 | Shalini Nair | 68.5 | engineering | Data Engineer | 7/10 | 3 |
| #8 | Ananya Desai | 68.4 | engineering | Software Engineer | 7/10 | 3 |
| #9 | Priya Pa | 68.4 | engineering | Data Engineer | 7/10 | 2 |
| #10 | Neha Singh | 68.4 | engineering | Software Engineer | 7/10 | 3 |
| #11 | Rohan Mehra | 68.4 | engineering | Software Engineer | 7/10 | 3 |
| #12 | Aditya Joshi | 66.4 | engineering | Software Engineer | 7/10 | 3 |
| #13 | MARCUS HALL | 63.7 | engineering |  | 7/10 | 10 |
| #14 | Unknown Candidate | 58.4 | engineering |  | 7/10 | 0 |
| #15 | Souvik Karmakar | 57.0 | engineering |  | 8/10 | 0 |
| #16 | Database Programmer/Analyst (. | 56.1 | engineering |  | 7/10 | 0 |
| #17 | John Smith | 55.9 | engineering | Data Engineer | 5/10 | 5 |
| #18 | Pavithra Shetty | 55.7 | engineering | Software Engineer Company Name | 5/10 | 11 |
| #19 | People Centered Leadership | 55.6 | engineering |  | 6/10 | 0 |
| #20 | VICTORIA BAKER | 54.8 | engineering | DevOps Engineer | 4/10 | 0 |

### Frontend Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 71.1 | engineering |  | 9/10 | 10 |
| #2 | Amit Sharma | 68.3 | engineering | Software Engineer | 9/10 | 3 |
| #3 | Unknown Candidate | 67.1 | engineering |  | 9/10 | 0 |
| #4 | Harper Garcia | 63.4 | engineering |  | 9/10 | 9 |
| #5 | It Consultant | 62.6 | engineering |  | 8/10 | 0 |
| #6 | Akila Palanimuthu | 60.8 | engineering |  | 8/10 | 0 |
| #7 | Asp.Net Web Developer | 58.6 | engineering |  | 8/10 | 0 |
| #8 | Unknown Candidate | 57.2 | engineering |  | 8/10 | 0 |
| #9 | Database Programmer/Analyst (. | 56.9 | engineering |  | 8/10 | 0 |
| #10 | Database Programmer/Analyst (. | 56.5 | engineering |  | 8/10 | 0 |
| #11 | Vikram Rao | 55.3 | engineering | Data Engineer | 6/10 | 3 |
| #12 | Souvik Karmakar | 55.2 | engineering |  | 8/10 | 0 |
| #13 | Unknown Candidate | 55.1 | engineering |  | 7/10 | 0 |
| #14 | Shalini Nair | 55.0 | engineering | Data Engineer | 6/10 | 3 |
| #15 | Kiran Malhotra | 54.9 | engineering | Data Engineer | 6/10 | 3 |
| #16 | Ananya Desai | 54.8 | engineering | Software Engineer | 6/10 | 3 |
| #17 | Priya Pa | 54.8 | engineering | Data Engineer | 6/10 | 2 |
| #18 | Rohan Mehra | 54.8 | engineering | Software Engineer | 6/10 | 3 |
| #19 | Rahul Gupta | 54.7 | engineering | Software Engineer | 6/10 | 3 |
| #20 | Neha Singh | 54.6 | engineering | Software Engineer | 6/10 | 3 |

### Fullstack Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | MARCUS HALL | 93.4 | engineering | Full Stack Developer | 8/9 | 10 |
| #2 | Unknown Candidate | 81.0 | engineering |  | 8/9 | 0 |
| #3 | ZOE THOMPSON | 75.8 | engineering | Backend Developer | 7/9 | 0 |
| #4 | Harper Garcia | 70.5 | engineering | Developer | 4/9 | 9 |
| #5 | Amit Sharma | 69.0 | engineering |  | 8/9 | 3 |
| #6 | Rahul Gupta | 66.6 | engineering |  | 8/9 | 3 |
| #7 | Unknown Candidate | 66.2 | engineering |  | 8/9 | 0 |
| #8 | Vikram Rao | 61.9 | engineering |  | 7/9 | 3 |
| #9 | Souvik Karmakar | 61.6 | engineering |  | 7/9 | 0 |
| #10 | Kiran Malhotra | 61.6 | engineering |  | 7/9 | 3 |
| #11 | Shalini Nair | 61.6 | engineering |  | 7/9 | 3 |
| #12 | Ananya Desai | 61.5 | engineering |  | 7/9 | 3 |
| #13 | Priya Pa | 61.5 | engineering |  | 7/9 | 2 |
| #14 | Rohan Mehra | 61.5 | engineering |  | 7/9 | 3 |
| #15 | Unknown Candidate | 61.5 | engineering | Intern Application Developer | 6/9 | 0 |
| #16 | Neha Singh | 61.3 | engineering |  | 7/9 | 3 |
| #17 | Database Programmer/Analyst (. | 60.7 | engineering |  | 7/9 | 0 |
| #18 | Unknown Candidate | 60.3 | engineering |  | 6/9 | 0 |
| #19 | Aditya Joshi | 59.6 | engineering |  | 7/9 | 3 |
| #20 | It Consultant | 58.7 | engineering |  | 6/9 | 0 |

### DevOps Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | VICTORIA BAKER | 85.0 | engineering | DevOps Engineer | 7/9 | 0 |
| #2 | Amit Sharma | 79.8 | engineering | Software Engineer | 7/9 | 3 |
| #3 | Neha Singh | 75.9 | engineering | Software Engineer | 6/9 | 3 |
| #4 | Rahul Gupta | 69.8 | engineering | Software Engineer | 6/9 | 3 |
| #5 | Unknown Candidate | 68.3 | engineering |  | 8/9 | 0 |
| #6 | Shalini Nair | 66.6 | engineering | Data Engineer | 5/9 | 3 |
| #7 | ANURADHA K | 66.3 | engineering |  | 8/9 | 0 |
| #8 | ZOE THOMPSON | 66.3 | engineering | Backend Engineer | 6/9 | 0 |
| #9 | Ananya Desai | 63.2 | engineering | Software Engineer | 5/9 | 3 |
| #10 | Priya Pa | 60.2 | engineering | Data Engineer | 3/9 | 2 |
| #11 | Kiran Malhotra | 56.9 | engineering | Data Engineer | 3/9 | 3 |
| #12 | Rohan Mehra | 56.9 | engineering | Software Engineer | 3/9 | 3 |
| #13 | Unknown Candidate | 54.0 | engineering |  | 6/9 | 0 |
| #14 | Joseline | 53.8 | engineering |  | 8/9 | 0 |
| #15 | Vikram Rao | 53.7 | engineering | Data Engineer | 3/9 | 3 |
| #16 | Project Management | 53.5 | engineering |  | 6/9 | 0 |
| #17 | Aditya Joshi | 51.6 | engineering | Software Engineer | 3/9 | 3 |
| #18 | Unknown Candidate | 51.5 | engineering |  | 4/9 | 0 |
| #19 | Unknown Candidate | 51.3 | sales |  | 4/9 | 0 |
| #20 | Unknown Candidate | 50.8 | engineering |  | 6/9 | 0 |

### Data Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Ananya Desai | 95.0 | engineering | Software Engineer | 8/9 | 3 |
| #2 | Rohan Mehra | 95.0 | engineering | Software Engineer | 8/9 | 3 |
| #3 | Aditya Joshi | 93.0 | engineering | Software Engineer | 8/9 | 3 |
| #4 | Shalini Nair | 92.9 | engineering | Data Engineer | 7/9 | 3 |
| #5 | Priya Pa | 90.4 | engineering | Data Engineer | 7/9 | 2 |
| #6 | Neha Singh | 90.0 | engineering | Software Engineer | 7/9 | 3 |
| #7 | Kiran Malhotra | 84.1 | engineering | Data Engineer | 6/9 | 3 |
| #8 | Vikram Rao | 81.1 | engineering | Data Engineer | 5/9 | 3 |
| #9 | Amit Sharma | 80.8 | engineering | Software Engineer | 6/9 | 3 |
| #10 | Rahul Gupta | 73.2 | engineering | Software Engineer | 5/9 | 3 |
| #11 | John Smith | 70.1 | engineering | Data Engineer | 6/9 | 5 |
| #12 | Master Data Manager | 57.0 | engineering |  | 5/9 | 0 |
| #13 | ZOE THOMPSON | 48.2 | engineering | Backend Engineer | 2/9 | 0 |
| #14 | Unknown Candidate | 46.6 | engineering |  | 5/9 | 0 |
| #15 | MARCUS HALL | 46.5 | engineering |  | 5/9 | 10 |
| #16 | Pavithra Shetty | 45.5 | engineering | Software Engineer Company Name | 2/9 | 11 |
| #17 | ADJUNCT INSTRUCTOR | 45.3 | hr |  | 3/9 | 0 |
| #18 | Unknown Candidate | 44.8 | engineering |  | 3/9 | 0 |
| #19 | JEROME PELINSKY | 43.5 | engineering |  | 3/9 | 0 |
| #20 | Tata Consultancy Services Ltd. | 42.8 | engineering |  | 2/9 | 0 |

### Data Scientist
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Rahul Gupta | 80.3 | engineering |  | 7/8 | 3 |
| #2 | Kiran Malhotra | 78.8 | engineering | Data Engineer | 7/8 | 3 |
| #3 | Priya Pa | 77.1 | engineering | Data Engineer | 8/8 | 2 |
| #4 | Amit Sharma | 76.8 | engineering |  | 7/8 | 3 |
| #5 | Shalini Nair | 76.7 | engineering | Data Engineer | 7/8 | 3 |
| #6 | Pavithra Shetty | 76.6 | engineering |  | 8/8 | 11 |
| #7 | Ananya Desai | 75.3 | engineering |  | 8/8 | 3 |
| #8 | Rohan Mehra | 73.6 | engineering |  | 8/8 | 3 |
| #9 | Vikram Rao | 72.9 | engineering | Data Engineer | 7/8 | 3 |
| #10 | Aditya Joshi | 71.7 | engineering |  | 8/8 | 3 |
| #11 | Neha Singh | 70.8 | engineering |  | 8/8 | 3 |
| #12 | Christian | 66.9 | engineering | Data Analyst Intern | 8/8 | 0 |
| #13 | Joseline | 66.7 | engineering |  | 8/8 | 0 |
| #14 | LISA JENNINGS | 66.0 | engineering |  | 8/8 | 0 |
| #15 | E-Novate Labs | 64.3 | engineering |  | 7/8 | 0 |
| #16 | MATILDA | 63.6 | engineering |  | 8/8 | 0 |
| #17 | ANTHONY GUAP | 62.9 | engineering |  | 7/8 | 1 |
| #18 | GINANNA | 61.9 | engineering |  | 8/8 | 0 |
| #19 | John Smith | 61.1 | engineering | Data Engineer | 7/8 | 5 |
| #20 | LANDO | 60.4 | engineering |  | 7/8 | 2 |

### ML Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Amit Sharma | 81.3 | engineering | Software Engineer | 7/8 | 3 |
| #2 | Rahul Gupta | 80.6 | engineering | Software Engineer | 6/8 | 3 |
| #3 | Ananya Desai | 68.9 | engineering | Software Engineer | 5/8 | 3 |
| #4 | Kiran Malhotra | 67.7 | engineering | Data Engineer | 5/8 | 3 |
| #5 | Rohan Mehra | 64.7 | engineering | Software Engineer | 5/8 | 3 |
| #6 | Vikram Rao | 62.6 | engineering | Data Engineer | 4/8 | 3 |
| #7 | Shalini Nair | 62.4 | engineering | Data Engineer | 4/8 | 3 |
| #8 | Priya Pa | 61.9 | engineering | Data Engineer | 5/8 | 2 |
| #9 | Neha Singh | 61.3 | engineering | Software Engineer | 5/8 | 3 |
| #10 | Joseline | 58.8 | engineering |  | 7/8 | 0 |
| #11 | Unknown Candidate | 57.2 | engineering |  | 7/8 | 0 |
| #12 | Aditya Joshi | 56.2 | engineering | Software Engineer | 4/8 | 3 |
| #13 | E-Novate Labs | 52.8 | engineering |  | 4/8 | 0 |
| #14 | VICTORIA BAKER | 51.3 | engineering | DevOps Engineer | 4/8 | 0 |
| #15 | JULIA | 48.5 | engineering |  | 6/8 | 0 |
| #16 | ABIGAIL | 47.1 | engineering |  | 6/8 | 0 |
| #17 | ANTHONY GUAP | 46.9 | engineering |  | 5/8 | 1 |
| #18 | MASON | 46.5 | engineering |  | 6/8 | 0 |
| #19 | MIKAYLA | 46.3 | engineering |  | 6/8 | 0 |
| #20 | SEAN CAMPBELL | 45.7 | engineering |  | 6/8 | 0 |

### Marketing Manager
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ELIJAH BROWN | 100.0 | marketing | Digital Marketing Manager | 7/7 | 0 |
| #2 | LIAM | 97.5 | marketing | Digital Marketing Specialist | 7/7 | 0 |
| #3 | Unknown Candidate | 76.7 | marketing |  | 7/7 | 11 |
| #4 | Marketing Consultant | 75.5 | marketing |  | 7/7 | 0 |
| #5 | Unknown Candidate | 72.7 | marketing | Successfully wrote and produced over 75 digital marketing pieces | 6/7 | 0 |
| #6 | Unknown Candidate | 72.2 | marketing |  | 7/7 | 0 |
| #7 | Christopher Fowler | 69.5 | marketing |  | 7/7 | 0 |
| #8 | Anand Street | 69.1 | marketing |  | 7/7 | 0 |
| #9 | Unknown Candidate | 69.1 | marketing |  | 7/7 | 0 |
| #10 | Joomla Content Management | 68.6 | marketing |  | 6/7 | 0 |
| #11 | Unknown Candidate | 68.6 | marketing |  | 6/7 | 0 |
| #12 | Unknown Candidate | 68.5 | hospitality |  | 6/7 | 0 |
| #13 | BUSINESS SYSTEMS ANALYST I | 68.4 | marketing |  | 7/7 | 0 |
| #14 | Unknown Candidate | 68.2 | marketing | Assistant Operations Manager Company Name - City | 5/7 | 0 |
| #15 | Christopher Fowler | 67.9 | marketing | Digital Marketer | 6/7 | 0 |
| #16 | Information Technology Consult | 67.2 | marketing |  | 6/7 | 0 |
| #17 | UNIT PUBLICIST | 66.8 | marketing |  | 6/7 | 0 |
| #18 | Web Development Coordinator | 66.5 | marketing |  | 6/7 | 0 |
| #19 | Web Marketing | 66.0 | marketing | Successfully supported all country managers and channel partners in exceeding revenue goals through these marketing programs | 6/7 | 0 |
| #20 | Administrative Assistant | 66.0 | marketing |  | 6/7 | 0 |

### Sales Executive
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ISAAC HALL | 90.4 | sales | Sales Executive | 5/5 | 0 |
| #2 | PRAKASH PINDARI | 80.2 | sales | Reporting to the Director Sales & Marketing | 5/5 | 0 |
| #3 | Marketing Consultant | 77.6 | marketing |  | 5/5 | 0 |
| #4 | Unknown Candidate | 74.3 | sales | State Sales and Marketing Director | 5/5 | 0 |
| #5 | Dheeraj S. Sharma | 73.0 | sales |  | 5/5 | 0 |
| #6 | SEBASTIAN MARTIN | 73.0 | sales | Sales Operations Manager | 5/5 | 0 |
| #7 | Unknown Candidate | 73.0 | sales | Sales & Marketing | 5/5 | 0 |
| #8 | Shahadat Hussain | 72.3 | sales |  | 5/5 | 0 |
| #9 | Unknown Candidate | 71.0 | sales |  | 5/5 | 0 |
| #10 | SALIK SHAIKH | 71.0 | sales | Business Development Executive | 5/5 | 0 |
| #11 | Unknown Candidate | 70.8 | accounting |  | 5/5 | 0 |
| #12 | Shahriar Saaed Niazi | 70.8 | sales | 2017 Du channel partner sales executive & business | 5/5 | 0 |
| #13 | Rajaneesh Kumar Singh Janwar | 69.7 | marketing |  | 5/5 | 0 |
| #14 | Business Consultant | 69.2 | sales |  | 5/5 | 10 |
| #15 | Mohammed Imran Khan | 68.1 | marketing |  | 5/5 | 0 |
| #16 | Unknown Candidate | 67.8 | hospitality |  | 5/5 | 0 |
| #17 | Unknown Candidate | 67.7 | sales |  Helping sales team to achieve set sales targets | 5/5 | 0 |
| #18 | Master Data Manager | 67.5 | engineering |  | 5/5 | 0 |
| #19 | Oman Career Software | 66.6 | sales | Sales Representative | 5/5 | 0 |
| #20 | SHOIAB KHAN | 66.3 | sales | Designation : Manager (direct Sales) | 5/5 | 0 |

### HR Manager
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | J.KRISHNAMOORTHY | 79.2 | healthcare | – 2010 (Administration Manager - Qatar) | 6/6 | 0 |
| #2 | Unknown Candidate | 76.4 | hr |  | 6/6 | 0 |
| #3 | Unknown Candidate | 75.2 | admin | HR Executive/ Administration | 6/6 | 0 |
| #4 | Human Resources Supervisor | 72.5 | hr |  | 6/6 | 0 |
| #5 | Unknown Candidate | 72.1 | hr |  | 6/6 | 0 |
| #6 | Unknown Candidate | 70.4 | healthcare |  | 6/6 | 0 |
| #7 | Bhola Nagar | 70.3 | hr | Designation: Sr. Executive –HR & ADMIN | 5/6 | 1 |
| #8 | Mohammed Hidayath | 68.4 | hr |  | 6/6 | 0 |
| #9 | Customer Service. | 68.1 | healthcare |  | 6/6 | 0 |
| #10 | Radha HG | 66.8 | hr | Process Executive – HR : - First American India, Bangalore, India ( | 5/6 | 7 |
| #11 | Unknown Candidate | 65.9 | hr |  | 6/6 | 0 |
| #12 | Unknown Candidate | 65.3 | hr |  | 3/6 | 0 |
| #13 | UPADHYAY | 64.8 | hospitality | Assistant HR | 6/6 | 0 |
| #14 | NOOR MOHAMED. | 64.3 | healthcare | Worked as HR&ADMINASSISTANT in POINEER HOSPTIAL | 5/6 | 2 |
| #15 | Unknown Candidate | 63.6 | healthcare |  | 6/6 | 0 |
| #16 | Quality Assurance Manager | 63.2 | education |  | 4/6 | 0 |
| #17 | Unknown Candidate | 63.1 | marketing |  | 3/6 | 0 |
| #18 | Unknown Candidate | 63.1 | hr |  | 3/6 | 0 |
| #19 | Mohd Ameen Khan | 62.8 | hr | Designation: HR RECRUITER | 3/6 | 0 |
| #20 | Substitute Teacher | 62.8 | hr |  | 5/6 | 0 |

### Accountant
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | ATHAVUL JAWAD S.M | 84.6 | accounting | Senior Accountant | 6/7 | 0 |
| #2 | Unknown Candidate | 83.4 | accounting | Accountant; | 6/7 | 0 |
| #3 | Unknown Candidate | 81.9 | accounting | Certified Public Accountant Part 3(Sec 5 & 6 )[  ] | 7/7 | 4 |
| #4 | Abhishek Kumar | 77.9 | accounting |  | 6/7 | 0 |
| #5 | Unknown Candidate | 77.8 | accounting |  | 7/7 | 0 |
| #6 | Baraa Al-Jabi | 77.1 | accounting |  | 6/7 | 0 |
| #7 | Resume for the Post of Account | 74.8 | accounting | Position:Accountant | 6/7 | 0 |
| #8 | Unknown Candidate | 74.1 | accounting |  | 7/7 | 0 |
| #9 | Unknown Candidate | 73.8 | accounting |  | 6/7 | 0 |
| #10 | Sammy Musungu | 72.0 | accounting |  | 6/7 | 0 |
| #11 | PRIYANKA SANGANERIA GUPTA | 71.5 | accounting |  | 6/7 | 0 |
| #12 | ABIGAIL HALL | 71.2 | accounting | Junior Cost Accountant | 5/7 | 0 |
| #13 | Unknown Candidate | 71.1 | accounting |  | 6/7 | 0 |
| #14 | Saurabh Kishorbhai Seta | 70.1 | accounting | I have worked As An Accountant Cum Treasury Officer in Taageer Finance Co | 5/7 | 0 |
| #15 | ABU RAIS SIDDIQUI | 68.7 | finance |  Sr. Accountant | 6/7 | 0 |
| #16 | ROBAI | 67.9 | accounting | Jan 2009 to ACCOUNTANT – AL-SAIAR TOURS | 5/7 | 0 |
| #17 | Master Data Manager | 67.8 | engineering |  | 7/7 | 0 |
| #18 | Dilshad Garden | 66.9 | accounting |  | 5/7 | 3 |
| #19 | Unknown Candidate | 66.1 | sales |  | 6/7 | 0 |
| #20 | V.P.O. Nangal Bhur | 66.1 | accounting |  | 6/7 | 0 |

### Civil Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 63.0 | construction |  Office Civil Engineer | 3/7 | 12 |
| #2 | Ramkumar Kasilingam | 62.6 | construction | Yuksel Inshaat A.S (Site Engineer) Oct 11 | 3/7 | 0 |
| #3 | RAJESH K R | 61.0 | healthcare |  Trainee Engineer - Estimation | 4/7 | 0 |
| #4 | Unknown Candidate | 57.4 | finance |  | 4/7 | 9 |
| #5 | Unknown Candidate | 56.6 | construction |  | 3/7 | 0 |
| #6 | SURESH KUMAR MAHENDRAN | 56.1 | construction |  | 3/7 | 0 |
| #7 | RAJESH K R | 55.3 | healthcare |  Trainee Engineer - Estimation | 4/7 | 0 |
| #8 | Unknown Candidate | 55.1 | construction | Civil | 2/7 | 0 |
| #9 | Unknown Candidate | 55.0 | construction | Designation : Civil & Plumbing site Engineer | 3/7 | 0 |
| #10 | Academic Record | 54.6 | construction | Working as Quantity Surveyor & Civil Engineer with PEE KAY | 2/7 | 0 |
| #11 | SURESH KUMAR MAHENDRAN | 54.3 | construction |  | 3/7 | 0 |
| #12 | MUSTAFA AHMAD | 53.5 | construction |  | 3/7 | 0 |
| #13 | SAURABH SAXENA | 53.4 | construction |  | 2/7 | 0 |
| #14 | GSM And CDMA Systems | 52.4 | healthcare | Client: General Authority of Civil Aviation | 3/7 | 0 |
| #15 | LOGACHANDIRANE R | 51.7 | construction | Safety Engineer | 1/7 | 6 |
| #16 | G S SUBRAHMANYA VARMA | 51.7 | unknown |  | 3/7 | 0 |
| #17 | B.Mohamed Hamdhan | 51.4 | healthcare |  | 3/7 | 0 |
| #18 | Khalid Othman | 51.3 | construction | () ▪ Site Engineer for solar pumping systems | 4/7 | 12 |
| #19 | Unknown Candidate | 51.0 | construction | Position : Assistent Material Engineer | 1/7 | 0 |
| #20 | Jayakumar Murugesan | 50.7 | construction | Site Engineer Oviya Builders | 3/7 | 0 |

### Electrical Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Electrical Engineer | 70.1 | construction | Electrical Engineer | 4/7 | 0 |
| #2 | GSM And CDMA Systems | 63.2 | healthcare | Electrical Engineer Main Project: King Abdulaziz International Airport New Project Jeddah | 4/7 | 0 |
| #3 | ISHTIAQUE KAZMI | 63.1 | healthcare | Position: SITE ELECTRICAL ENGINEER | 2/7 | 2 |
| #4 | E K T | 61.2 | healthcare | QA Engineer (Electrical) | 1/7 | 0 |
| #5 | Unknown Candidate | 61.1 | legal | Designation : Electrical Project Engineer | 1/7 | 10 |
| #6 | Sadam Hussain S | 61.1 | sales | Electrical Engineer | 3/7 | 0 |
| #7 | Anil Paudel | 60.8 | healthcare | Electrical Engineer | 2/7 | 0 |
| #8 | RAJA PAULRAJ | 58.6 | construction |  | 3/7 | 0 |
| #9 | AKHLAKUR RAHMAN | 58.2 | construction | Designation: Electrical Site Engineer | 2/7 | 0 |
| #10 | Nagaraj.P | 57.2 | healthcare |  | 3/7 | 0 |
| #11 | Unknown Candidate | 55.8 | healthcare | Designation:-Project Engineer Electrical | 1/7 | 0 |
| #12 | Unknown Candidate | 55.8 | healthcare | Designation:-Project Engineer Electrical | 1/7 | 0 |
| #13 | BIPIN KUMAR SINGH | 55.4 | healthcare | Assistant Engineer | 2/7 | 0 |
| #14 | SUKHVINDER SINGH | 54.9 | healthcare | Electrical Equipment Electrician | 1/7 | 0 |
| #15 | MOHAMMAD AZHAR IMAM | 54.1 | construction | Designation : Electrical Site Engineer | 1/7 | 0 |
| #16 | BALAJI LOGANATHAN | 53.9 | healthcare | Junior Engineer | 2/7 | 0 |
| #17 | Unknown Candidate | 52.4 | healthcare | Engineer; Services-Electrical Maintenance” from Aug 2016 to present | 1/7 | 0 |
| #18 | Unknown Candidate | 51.7 | finance | Designation: Electrical Engineer | 0/7 | 0 |
| #19 | Unknown Candidate | 51.5 | healthcare | Designation Electrical Engineer | 2/7 | 8 |
| #20 | Unknown Candidate | 50.8 | healthcare | Working as PROJECT ENGINEER(Electrical) | 1/7 | 0 |

### Mechanical Engineer
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | JOHNS K ABRAHAM | 76.0 | healthcare | Designation: Design Engineer | 6/7 | 0 |
| #2 | Unknown Candidate | 69.6 | accounting |  | 5/7 | 0 |
| #3 | Unknown Candidate | 67.3 | healthcare |  | 5/7 | 13 |
| #4 | Unknown Candidate | 62.5 | unknown |  | 5/7 | 0 |
| #5 | Kesava Career Work | 62.3 | healthcare | Designation :DESIGN ENGINEER | 4/7 | 0 |
| #6 | GYANESH GULSHAN | 60.0 | sales | Production Engineer | 4/7 | 11 |
| #7 | Prasaath Balachandran | 57.7 | sales | Production Engineer | 3/7 | 0 |
| #8 | Unknown Candidate | 57.0 | healthcare |  | 4/7 | 0 |
| #9 | Electrical Engineer | 56.5 | construction | Electrical Engineer | 4/7 | 0 |
| #10 | Unknown Candidate | 56.0 | sales | Position : EMPLOYEE (Production Engineer) | 4/7 | 11 |
| #11 | Unknown Candidate | 55.2 | healthcare | Sr.Mechanical Engineer Jan 2011 to Aug 2012 | 2/7 | 0 |
| #12 | Siddharth Aggarwal | 54.2 | legal | : Mechanical Engineer | 3/7 | 0 |
| #13 | Information Technology Manager | 53.0 | engineering |  | 4/7 | 0 |
| #14 | Unknown Candidate | 52.9 | healthcare | Nelcast Limited as Graduate Trainee Engineer (Manufacturing/Production) | 1/7 | 0 |
| #15 | Sagar Baburao Bhadange | 52.9 | healthcare | Designation: Assembly engineer | 1/7 | 0 |
| #16 | Unknown Candidate | 51.6 | marketing |  | 2/7 | 0 |
| #17 | Aasif Khan | 51.4 | healthcare | Education Qualification: Mechanical Engineering | 3/7 | 0 |
| #18 | Unknown Candidate | 51.3 | construction | Engineer-Electrical Maintenance | 3/7 | 0 |
| #19 | Unknown Candidate | 51.3 | healthcare |  | 4/7 | 11 |
| #20 | S.HASSANATH MUKTHAR | 51.1 | healthcare |  | 4/7 | 0 |

### Legal Advisor
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Biography Writer | 76.5 | education |  | 5/5 | 0 |
| #2 | John Smith | 71.8 | legal |  | 4/5 | 6 |
| #3 | Court Procedures Due Dilligenc | 71.0 | legal |  | 4/5 | 0 |
| #4 | Unknown Candidate | 70.7 | legal |  | 5/5 | 0 |
| #5 | Unknown Candidate | 60.2 | legal |  | 3/5 | 0 |
| #6 | Unknown Candidate | 59.9 | education | 6/95 to 5/99 LEGAL INTERN/RESEARCHER/INVESTIGATOR | 3/5 | 0 |
| #7 | Qualification Â | 59.2 | engineering |  | 4/5 | 0 |
| #8 | Information Technology Provisi | 58.9 | legal |  | 4/5 | 12 |
| #9 | Unknown Candidate | 58.4 | hr |  | 4/5 | 0 |
| #10 | Unknown Candidate | 56.9 | marketing |  | 4/5 | 0 |
| #11 | Professional Overview | 56.8 | sales |  | 4/5 | 0 |
| #12 | Unknown Candidate | 56.0 | sales |  | 4/5 | 0 |
| #13 | Unknown Candidate | 55.9 | healthcare |  | 3/5 | 0 |
| #14 | Shabina P | 54.9 | marketing |  | 4/5 | 0 |
| #15 | Shabina P | 54.9 | marketing |  | 4/5 | 0 |
| #16 | The Mathworks MATLAB | 54.9 | education |  | 4/5 | 0 |
| #17 | ZAFER HUSSAIN | 54.5 | legal |  | 3/5 | 0 |
| #18 | J.KRISHNAMOORTHY | 54.0 | healthcare |  | 4/5 | 0 |
| #19 | Unknown Candidate | 53.6 | hr |  | 4/5 | 0 |
| #20 | Unknown Candidate | 53.1 | hr |  | 3/5 | 0 |

### Healthcare Specialist
Total candidates: 491

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 77.3 | healthcare |  | 6/6 | 0 |
| #2 | Unknown Candidate | 72.5 | healthcare |  | 4/6 | 3 |
| #3 | BANK TELLER | 71.8 | admin |  | 6/6 | 0 |
| #4 | Unknown Candidate | 67.4 | healthcare |  | 6/6 | 0 |
| #5 | Unknown Candidate | 67.3 | healthcare |  | 4/6 | 0 |
| #6 | Unknown Candidate | 64.5 | healthcare |  | 3/6 | 0 |
| #7 | Unknown Candidate | 64.0 | healthcare |  | 6/6 | 0 |
| #8 | STAFF PHARMACIST | 63.5 | healthcare |  | 4/6 | 0 |
| #9 | Communications Consultant | 63.5 | healthcare |  | 4/6 | 0 |
| #10 | Communications Consultant | 63.2 | healthcare |  | 4/6 | 0 |
| #11 | Unknown Candidate | 62.6 | healthcare |  | 3/6 | 0 |
| #12 | Unknown Candidate | 62.5 | healthcare |  | 3/6 | 0 |
| #13 | Unknown Candidate | 62.1 | healthcare |  | 4/6 | 0 |
| #14 | Unknown Candidate | 62.1 | healthcare |  | 2/6 | 0 |
| #15 | Professional Overview | 60.4 | healthcare |  | 4/6 | 0 |
| #16 | DR.SANTOSH KAKADE | 60.1 | healthcare |  | 4/6 | 0 |
| #17 | Aviation Safety Assistant | 58.8 | hr |  | 4/6 | 0 |
| #18 | Marketing Consultant | 56.7 | marketing |  | 2/6 | 0 |
| #19 | Unknown Candidate | 54.9 | healthcare |  | 4/6 | 0 |
| #20 | Customer Service. | 54.9 | healthcare |  | 2/6 | 0 |

### Teacher
Total candidates: 457

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Classroom Management Interpers | 80.4 | education |  | 4/4 | 0 |
| #2 | Deaconess Children's CenterÂ | 79.2 | education | Lead Teacher Company Name - City | 2/4 | 0 |
| #3 | Science Education. | 78.8 | education |  | 3/4 | 0 |
| #4 | Unknown Candidate | 78.6 | education |  | 3/4 | 0 |
| #5 | Unknown Candidate | 78.6 | education |  | 3/4 | 0 |
| #6 | Unknown Candidate | 78.6 | education |  | 3/4 | 0 |
| #7 | Unknown Candidate | 78.5 | education |  | 3/4 | 0 |
| #8 | History Teacher | 78.5 | education |  | 3/4 | 0 |
| #9 | Unknown Candidate | 78.5 | education |  | 3/4 | 0 |
| #10 | Information Technology Analyst | 76.7 | education |  | 3/4 | 0 |
| #11 | Unknown Candidate | 76.7 | education |  | 3/4 | 0 |
| #12 | Unknown Candidate | 76.1 | education | Teacher | 1/4 | 0 |
| #13 | RISHA SRITHARAN | 75.1 | education | Post Graduate Teacher | 2/4 | 0 |
| #14 | Unknown Candidate | 73.8 | education |  | 3/4 | 0 |
| #15 | Kindergarten Teacher | 73.7 | education |  | 3/4 | 0 |
| #16 | Kimberly Fisheli | 73.1 | education | Substitute Teacher | 1/4 | 4 |
| #17 | Unknown Candidate | 72.1 | education |  | 2/4 | 0 |
| #18 | Marilyn Hunter | 72.0 | education | Substitute Teacher | 1/4 | 0 |
| #19 | SEI EndorsedÂ | 71.9 | education |  | 2/4 | 0 |
| #20 | Unknown Candidate | 70.8 | education |  | 2/4 | 1 |

### Hotel Manager
Total candidates: 210

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 84.3 | healthcare |  | 4/4 | 0 |
| #2 | Unknown Candidate | 60.6 | hospitality |  | 2/4 | 0 |
| #3 | Unknown Candidate | 55.0 | hospitality |  | 1/4 | 0 |
| #4 | CHETAN SWARUP | 50.0 | hospitality | Current : M/s AVS Facilities : Facility Manager | 1/4 | 0 |
| #5 | CONSULTANT TO OWNER | 49.7 | hospitality |  | 1/4 | 0 |
| #6 | Tactical Planning Goal-oriente | 49.4 | hospitality |  | 1/4 | 0 |
| #7 | SALIK SHAIKH | 49.3 | sales |  | 1/4 | 0 |
| #8 | Unknown Candidate | 48.1 | healthcare |  | 2/4 | 0 |
| #9 | Unknown Candidate | 46.7 | marketing |  | 1/4 | 0 |
| #10 | UPADHYAY | 45.2 | hospitality |  | 1/4 | 0 |
| #11 | Unknown Candidate | 45.2 | admin |  | 1/4 | 0 |
| #12 | Manager | 45.2 | marketing |  | 1/4 | 0 |
| #13 | General Manager | 45.2 | education |  | 1/4 | 0 |
| #14 | Mohammad | 44.0 | hospitality |  | 1/4 | 0 |
| #15 | Multi Task Abilities | 42.5 | sales |  | 1/4 | 0 |
| #16 | Unknown Candidate | 42.5 | sales |  | 1/4 | 0 |
| #17 | Unknown Candidate | 42.0 | hospitality |  | 0/4 | 0 |
| #18 | Office Administrator | 41.0 | marketing |  | 1/4 | 0 |
| #19 | Biography Writer | 41.0 | education |  | 1/4 | 0 |
| #20 | Unknown Candidate | 41.0 | education |  | 1/4 | 0 |

### Construction Manager
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | Unknown Candidate | 81.4 | healthcare | Doha – Qatar as Project Manager (Estimation | 4/4 | 0 |
| #2 | AQEEL AHMED | 79.4 | construction |  | 4/4 | 1 |
| #3 | Ramkumar Kasilingam | 79.1 | construction | China petroleum Engineering & Construction Corporation (CPECC) Since Dec | 3/4 | 0 |
| #4 | Unknown Candidate | 79.0 | finance |  | 3/4 | 9 |
| #5 | Unknown Candidate | 76.5 | healthcare |  | 4/4 | 0 |
| #6 | Unknown Candidate | 75.7 | construction |  | 3/4 | 12 |
| #7 | Jayakumar Murugesan | 74.8 | construction | 8+ years of construction experience in India and 4 years experience in | 3/4 | 0 |
| #8 | Unknown Candidate | 74.7 | construction | Organization : Krishna Sahil Construction Pvt. Ltd | 2/4 | 0 |
| #9 | Unknown Candidate | 74.5 | construction |  | 3/4 | 0 |
| #10 | Construction Consultant | 71.9 | construction |  | 3/4 | 0 |
| #11 | Naman Gala | 71.2 | sales | Simplex Prefab (Precast Construction) | 1/4 | 4 |
| #12 | Unknown Candidate | 70.7 | healthcare |  | 3/4 | 0 |
| #13 | Unknown Candidate | 70.4 | construction |  | 3/4 | 0 |
| #14 | Unknown Candidate | 69.8 | construction |  | 2/4 | 11 |
| #15 | Ata Ur Rahman | 69.5 | hospitality |  | 3/4 | 0 |
| #16 | SURESH KUMAR MAHENDRAN | 69.4 | construction |  | 2/4 | 0 |
| #17 | Unknown Candidate | 68.3 | legal |  | 3/4 | 10 |
| #18 | B.Mohamed Hamdhan | 68.3 | healthcare |  | 2/4 | 0 |
| #19 | System Standard | 67.6 | engineering |  | 2/4 | 0 |
| #20 | Unknown Candidate | 65.9 | construction |  Construction Safety | 1/4 | 0 |

### Office Admin
Total candidates: 500

| Rank | Name | Score | Domain | Sub-Domain | Skills | Exp |
|------|------|-------|--------|------------|--------|-----|
| #1 | History Teacher | 84.7 | education |  | 4/4 | 0 |
| #2 | Staff Assistant | 79.5 | admin |  | 4/4 | 0 |
| #3 | Unknown Candidate | 79.0 | admin |  | 4/4 | 0 |
| #4 | Unknown Candidate | 75.9 | healthcare |  | 3/4 | 0 |
| #5 | BANK TELLER | 74.2 | admin |  | 2/4 | 0 |
| #6 | Unknown Candidate | 72.8 | legal |  | 3/4 | 0 |
| #7 | Godwin Opati Sitati | 72.8 | finance |  | 3/4 | 0 |
| #8 | Unknown Candidate | 72.3 | marketing |  | 3/4 | 0 |
| #9 | Microsoft Office Proficiency | 72.3 | admin |  | 3/4 | 0 |
| #10 | Unknown Candidate | 71.0 | marketing |  | 3/4 | 0 |
| #11 | J.KRISHNAMOORTHY | 69.2 | healthcare |  | 2/4 | 0 |
| #12 | Premananda Das | 68.5 | admin | Post Held: Asst. Administrator | 2/4 | 0 |
| #13 | AVIATION MAINTAINER | 68.0 | sales |  | 2/4 | 11 |
| #14 | Passenger Services Officer | 66.2 | sales |  | 3/4 | 0 |
| #15 | MUHAMMAD. | 65.9 | admin |  | 1/4 | 0 |
| #16 | Aviation Safety Assistant | 64.7 | hr |  | 2/4 | 0 |
| #17 | General Manager | 64.5 | education |  | 2/4 | 0 |
| #18 | Unknown Candidate | 64.2 | hr |  | 2/4 | 0 |
| #19 | Financial Technician | 64.2 | accounting |  | 2/4 | 0 |
| #20 | CONTENT STRATEGIST | 62.5 | marketing |  | 3/4 | 0 |

---
## Phase 5 — False Positive Audit
- **Count**: 30
- **FP Rate**: 15.0%
- **Formula**: 30 / (20 × 10)

| JD | Name | Score | Domain | Sub-Domain | Skills | Exp | Reason |
|----|------|-------|--------|------------|--------|-----|--------|
| Civil Engineer | Unknown Candidate | 63.0 | construction |  Office Civil Engineer | 3/7 | 12 |  Office Civil Engineer candidate in Civil Enginee |
| Civil Engineer | Ramkumar Kasilingam | 62.6 | construction | Yuksel Inshaat A.S (Site Engineer) Oct 11 | 3/7 | 0 | Yuksel Inshaat A.S (Site Engineer) Oct 11 candidat |
| Civil Engineer | RAJESH K R | 61.0 | healthcare |  Trainee Engineer - Estimation | 4/7 | 0 |  Trainee Engineer - Estimation candidate in Civil |
| Civil Engineer | Unknown Candidate | 57.4 | finance |  | 4/7 | 9 | finance candidate in Civil Engineer JD |
| Civil Engineer | Unknown Candidate | 56.6 | construction |  | 3/7 | 0 | construction candidate in Civil Engineer JD |
| Civil Engineer | SURESH KUMAR MAHENDRAN | 56.1 | construction |  | 3/7 | 0 | construction candidate in Civil Engineer JD |
| Civil Engineer | RAJESH K R | 55.3 | healthcare |  Trainee Engineer - Estimation | 4/7 | 0 |  Trainee Engineer - Estimation candidate in Civil |
| Civil Engineer | Unknown Candidate | 55.1 | construction | Civil | 2/7 | 0 | Civil candidate in Civil Engineer JD |
| Civil Engineer | Unknown Candidate | 55.0 | construction | Designation : Civil & Plumbing site Engineer | 3/7 | 0 | Designation : Civil & Plumbing site Engineer candi |
| Civil Engineer | Academic Record | 54.6 | construction | Working as Quantity Surveyor & Civil Engineer with PEE KAY | 2/7 | 0 | Working as Quantity Surveyor & Civil Engineer with |
| Electrical Engineer | Electrical Engineer | 70.1 | construction | Electrical Engineer | 4/7 | 0 | Electrical Engineer candidate in Electrical Engine |
| Electrical Engineer | GSM And CDMA Systems | 63.2 | healthcare | Electrical Engineer Main Project: King Abdulaziz International Airport New Project Jeddah | 4/7 | 0 | Electrical Engineer Main Project: King Abdulaziz I |
| Electrical Engineer | ISHTIAQUE KAZMI | 63.1 | healthcare | Position: SITE ELECTRICAL ENGINEER | 2/7 | 2 | Position: SITE ELECTRICAL ENGINEER candidate in El |
| Electrical Engineer | E K T | 61.2 | healthcare | QA Engineer (Electrical) | 1/7 | 0 | QA Engineer (Electrical) candidate in Electrical E |
| Electrical Engineer | Unknown Candidate | 61.1 | legal | Designation : Electrical Project Engineer | 1/7 | 10 | Designation : Electrical Project Engineer candidat |
| Electrical Engineer | Sadam Hussain S | 61.1 | sales | Electrical Engineer | 3/7 | 0 | Electrical Engineer candidate in Electrical Engine |
| Electrical Engineer | Anil Paudel | 60.8 | healthcare | Electrical Engineer | 2/7 | 0 | Electrical Engineer candidate in Electrical Engine |
| Electrical Engineer | RAJA PAULRAJ | 58.6 | construction |  | 3/7 | 0 | construction candidate in Electrical Engineer JD |
| Electrical Engineer | AKHLAKUR RAHMAN | 58.2 | construction | Designation: Electrical Site Engineer | 2/7 | 0 | Designation: Electrical Site Engineer candidate in |
| Electrical Engineer | Nagaraj.P | 57.2 | healthcare |  | 3/7 | 0 | healthcare candidate in Electrical Engineer JD |
| Mechanical Engineer | JOHNS K ABRAHAM | 76.0 | healthcare | Designation: Design Engineer | 6/7 | 0 | Designation: Design Engineer candidate in Mechanic |
| Mechanical Engineer | Unknown Candidate | 69.6 | accounting |  | 5/7 | 0 | accounting candidate in Mechanical Engineer JD |
| Mechanical Engineer | Unknown Candidate | 67.3 | healthcare |  | 5/7 | 13 | healthcare candidate in Mechanical Engineer JD |
| Mechanical Engineer | Kesava Career Work | 62.3 | healthcare | Designation :DESIGN ENGINEER | 4/7 | 0 | Designation :DESIGN ENGINEER candidate in Mechanic |
| Mechanical Engineer | GYANESH GULSHAN | 60.0 | sales | Production Engineer | 4/7 | 11 | Production Engineer candidate in Mechanical Engine |
| Mechanical Engineer | Prasaath Balachandran | 57.7 | sales | Production Engineer | 3/7 | 0 | Production Engineer candidate in Mechanical Engine |
| Mechanical Engineer | Unknown Candidate | 57.0 | healthcare |  | 4/7 | 0 | healthcare candidate in Mechanical Engineer JD |
| Mechanical Engineer | Electrical Engineer | 56.5 | construction | Electrical Engineer | 4/7 | 0 | Electrical Engineer candidate in Mechanical Engine |
| Mechanical Engineer | Unknown Candidate | 56.0 | sales | Position : EMPLOYEE (Production Engineer) | 4/7 | 11 | Position : EMPLOYEE (Production Engineer) candidat |
| Legal Advisor | Qualification Â | 59.2 | engineering |  | 4/5 | 0 | engineering candidate in non-eng JD 'Legal Advisor |

---
## Phase 6 — False Negative Audit
- **Count**: 200

| JD | Name | Domain | Sub-Domain | Skills | Overlap | Reason |
|----|------|--------|------------|--------|---------|--------|
| Backend Engineer | John Smith | engineering | software_engineering | 13 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Aditya Joshi | engineering | software_engineering | 19 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Amit Sharma | engineering | software_engineering | 26 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Ananya Desai | engineering | software_engineering | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Kiran Malhotra | engineering | software_engineering | 19 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Priya Pa | engineering | software_engineering | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Neha Singh | engineering | software_engineering | 23 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Rahul Gupta | engineering | software_engineering | 21 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Rohan Mehra | engineering | software_engineering | 20 | 4 | Domain match + 4/10 skill overlap but not in  |
| Backend Engineer | Shalini Nair | engineering | software_engineering | 18 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Vikram Rao | engineering | software_engineering | 15 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | ZOE THOMPSON | engineering | software_engineering | 14 | 5 | Domain match + 5/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 16 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 18 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 11 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Shanbagam Thanikachalam | engineering | software_engineering | 39 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | NOLAN | engineering | software_engineering | 15 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Qualification Â | engineering | electrical_engineering | 46 | 3 | Domain match + 3/10 skill overlap but not in  |
| Backend Engineer | Unknown Candidate | engineering | software_engineering | 55 | 4 | Domain match + 4/10 skill overlap but not in  |
| Frontend Engineer | DANIEL GAN | engineering | civil_engineering | 28 | 6 | Domain match + 6/10 skill overlap but not in  |
| Frontend Engineer | Thiruvallam P.O | engineering | software_engineering | 33 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Priya Elza | engineering | software_engineering | 27 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Unknown Candidate | engineering | software_engineering | 18 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Unknown Candidate | engineering | software_engineering | 31 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | CARRIER OBJECTIVES | engineering | software_engineering | 24 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | Akila Palanimuthu | engineering | software_engineering | 33 | 4 | Domain match + 4/10 skill overlap but not in  |
| Frontend Engineer | MOHD RASHID | engineering | software_engineering | 7 | 3 | Domain match + 3/10 skill overlap but not in  |
| Frontend Engineer | KEISUKE YAMAMOTO | engineering | software_engineering | 12 | 3 | Domain match + 3/10 skill overlap but not in  |

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
| 1 | 0.15s | 0.003s | 149.4ms | 400.6MB | 0 |
| 10 | 1.3s | 0.035s | 130.1ms | 463.9MB | 0 |
| 100 | 13.08s | 0.313s | 130.8ms | 521.9MB | 0 |
| 1000 | 169.86s | 3.564s | 169.9ms | 531.3MB | 0 |
| 5076 | 865.47s | N/A | 170.5ms | 531.3MB | 0 | (Phase 1 batch extraction data)

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
| Extraction Quality | 69/100 | 69/100 | +0 | ⚪ same |
| Ranking Quality | 95/100 | 69/100 | -26 | 🔴 -26 |
| Knockout Reliability | 100/100 | 100/100 | +0 | ⚪ same |
| Domain Accuracy | 93/100 | 93/100 | +0 | 🟢 +0 |
| False Positive Control | 88/100 | 25/100 | -63 | 🔴 -63 |
| False Negative Control | 75/100 | 75/100 | +0 | ⚪ same |
| Performance | 100/100 | 100/100 | +0 | ⚪ same |
| **OVERALL** | **86/100** | **75/100** | **-11** | **🔴 -11** |

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
