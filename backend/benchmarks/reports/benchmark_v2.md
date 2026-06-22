# Benchmark v2 — Extraction Correctness Report

Generated: 2026-06-22T22:43:04.528423

## Summary

| Metric | Value |
|--------|-------|
| PDFs Tested | 16 |
| All Passing | 16/16 |
| Overall Accuracy | 100.0% |

## Accuracy by Category

| Category | Accuracy |
|----------|----------|
| Name | 100.0% |
| Name Not Header | 100.0% |
| Skills | 100.0% |
| Experience | 100.0% |
| Education | 100.0% |
| No Tag Leaks | 100.0% |
| No Skill Bundles | 100.0% |
| Overall | 100.0% |

## Gates

| Gate | Status |
|------|--------|
| Name Accuracy Gte 95 | ✅ PASS |
| No Section Header Names | ✅ PASS |
| No Duplicated Skill Bundles | ✅ PASS |
| No Parser Tags In Output | ✅ PASS |
| Extraction Accuracy Gte 95 | ✅ PASS |

## Detailed Results

| PDF | Name | Skills | Experience | Education | Tags | Bundles | Status |
|-----|------|--------|------------|-----------|------|---------|--------|
| 1.pdf | JULIE MONROE | 12/8+ | 2/2+ | 3/1+ | 0 | 0 | ✅ |
| 2.pdf | DANIEL GAN | 28/15+ | 2/2+ | 1/1+ | 0 | 0 | ✅ |
| 3.pdf | Christopher Fowler | 10/8+ | 3/2+ | 2/1+ | 0 | 0 | ✅ |
| 5.pdf | John Smith | 13/10+ | 2/2+ | 1/1+ | 0 | 0 | ✅ |
| 6.pdf | Eddy Butler | 8/6+ | 2/2+ | 2/1+ | 0 | 0 | ✅ |
| 7.pdf | Sarah West | 16/10+ | 2/2+ | 1/1+ | 0 | 0 | ✅ |
| 9.pdf | ROBERT COOPER | 23/10+ | 2/2+ | 1/1+ | 0 | 0 | ✅ |
| 11.pdf | Emily Davies | 15/10+ | 3/2+ | 1/1+ | 0 | 0 | ✅ |
| 15.pdf | John Smith | 14/10+ | 2/2+ | 2/1+ | 0 | 0 | ✅ |
| backend.pdf | ZOE THOMPSON | 14/10+ | 3/3+ | 1/1+ | 0 | 0 | ✅ |
| fullstack.pdf | MARCUS HALL | 43/20+ | 3/3+ | 1/1+ | 0 | 0 | ✅ |
| SUBHADIPcv.pdf | SUBHADIP MONDAL | 12/10+ | 1/1+ | 2/2+ | 0 | 0 | ✅ |
| souvik.pdf | Souvik Karmakar | 42/20+ | 0/0+ | 2/1+ | 0 | 0 | ✅ |
| frontend.pdf | Harper Garcia | 22/10+ | 3/0+ | 2/1+ | 0 | 0 | ✅ |
| front-end.pdf | First Last | 14/10+ | 3/0+ | 1/1+ | 0 | 0 | ✅ |
| devops.pdf | VICTORIA BAKER | 16/10+ | 3/0+ | 1/1+ | 0 | 0 | ✅ |

## Fixes Applied

1. **Name Extraction**: Sidebar large-font names now get `doc_name` role (fixes frontend.pdf Harper Garcia)
2. **Name Blacklist**: Hard blacklist + tech word filter prevents section headers/skill phrases becoming names
3. **Section Detection**: Registry-based sidebar header detection (relaxed from strict bold+CAPS)
4. **Section Registry**: Added "RELEVANT WORK EXPERIENCE" alias
5. **Date Format**: Added MM/YYYY support in experience parser (fixes devops.pdf)
6. **Sidebar Merge**: Sidebar section content now fills gaps in main-column sections
7. **Skill Dedup**: Bundle splitting (space/slash/ampersand) + containment deduplication
8. **Tag Cleanup**: Bare LOC: tags now stripped from output