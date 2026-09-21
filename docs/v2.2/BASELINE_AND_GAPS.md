# SWYRA Sortlist v2.2 — Factual Baseline & Technical Gap Analysis

**Document Status:** BASELINE ONLY (Pre-Implementation Audit)  
**Target Release:** `v2.2 — Evidence Integrity, Strict Relevance Scoring, and ATS Diagnostics`  
**Working Branch:** `v2.1`  
**Audit Date:** 2026-09-20  

---

## 1. Precise Name-Extraction Failure Mode

The current contact extraction layer in `backend/src/extractors/contact/contact_parser.py` implements a greedy, first-match scanning heuristic rather than an evidence-based identity resolver:

1. **Greedy First-Match Exit:** The method `_extract_name()` iterates through text lines. The moment a line satisfies the boolean predicate `_is_name_line()`, execution terminates immediately and returns that text as the candidate's full name (`lines 480, 490, 514, 523, 528, 545, 548, 562`).
2. **Absence of Candidate Arbitration:** Candidates generated from layout tags (`[NAME]`), ODL heading tags (`type == 'heading'`), and raw text lines are not collected, scored, or ranked against each other.
3. **No Spatial or Structural Grounding:** Lines located in the middle or bottom of page 1, or within secondary content columns, are evaluated with the same priority as lines positioned at the top header zone.
4. **No Contact Adjacency Requirement:** The parser does not verify whether the candidate string is physically adjacent to verified contact anchors (email address, telephone number, LinkedIn URL, or location).
5. **Absence of Positive Identity Signals:** The heuristic relies almost entirely on *negative exclusion* (checking if words are not in blacklists). Any capitalized 2-to-3 word phrase that avoids the blacklist is assumed to be a human name.

---

## 2. Current Name Extraction Strategies in Priority Order

The method `ContactParser._extract_name()` executes the following strategies in strict sequence:

| Priority | Strategy | Source | Implementation Mechanism |
| :---: | :--- | :--- | :--- |
| **0** | ODL JSON Heading | `elements` (ODL JVM AST) | Flattens AST nodes, looks for `type == 'heading'` or `pdfua_tag.startswith('H')`, splits on `[,\|]`, and tests with `_is_name_line()` (`lines 459–480`). |
| **1** | Layout Tag `[NAME]` | `full_width_text`, `sidebar_text`, `raw_text` | Regex search `\[NAME\](.*?)\[/NAME\]` produced by `LayoutAwarePDFExtractor` (`lines 482–490`). |
| **2** | Sequential Line Scan (First 30 lines) | `main_text`, `raw_text`, `sidebar_text`, `pymupdf_text` | Scans first 30 lines of each source. Checks for `Last, First` regex, then tests single line, two consecutive lines, and split contact lines using `_is_name_line()` (`lines 496–529`). |
| **3** | Head & Tail Scan (30 lines top / 30 lines bottom) | `raw_text`, `pymupdf_text` | Scans `lines[:30] + lines[-30:]` with `_is_name_line()` and split checks (`lines 530–549`). |
| **4** | ALL-CAPS Fallback (15 lines top / 15 lines bottom) | `raw_text`, `pymupdf_text` | Looks for any line where `1 <= len(words) <= 4`, `candidate.isupper()`, and no digits exist (`lines 550–563`). |

---

## 3. Why “Insights possible sub-space.” Passes Validation

The phrase **“Insights possible sub-space.”** passes the current `_is_name_line()` predicate in `backend/src/extractors/contact/contact_parser.py` due to specific logical loopholes:

1. **Word Count Check (`lines 224–226`):**
   ```python
   words = s.split() # ['Insights', 'possible', 'sub-space.'] -> len = 3
   1 <= len(words) <= 5 # True
   ```
2. **Character & Punctuation Stripping (`lines 229–232`):**
   ```python
   clean = re.sub(r"[.\-']", '', w)
   ```
   - `'Insights'` $\rightarrow$ `'Insights'` (`isalpha() == True`)
   - `'possible'` $\rightarrow$ `'possible'` (`isalpha() == True`)
   - `'sub-space.'` $\rightarrow$ `'subspace'` (`isalpha() == True`)
3. **No Numbers or Symbols (`lines 233–238`):**
   No digits, no `@`, and no `http` URLs exist in the string.
4. **Section Keyword Exclusion (`lines 239–240`):**
   `{'insights', 'possible', 'sub-space.'} & _SECTION_KW` is empty.
5. **The Fatal Lowercase Permissiveness Loophole (`lines 241–248`):**
   ```python
   for i, w in enumerate(words):
       if not w[0].isupper() and w.lower() not in _NAME_PARTICLES:
           if i > 0 and len(words) <= 3:
               pass  # Intended to allow e.g. "Jitender kumar"
           else:
               return False
   ```
   `words[0]` (`"Insights"`) starts with uppercase `'I'`. Because `len(words) == 3`, word 1 (`"possible"`) and word 2 (`"sub-space."`) are excused by the `if i > 0 and len(words) <= 3: pass` branch, even though they are completely lowercase!
6. **Blacklist Gaps (`lines 250–316`):**
   - The phrase is absent from `_NOT_NAMES`, `_NAME_HARD_BLACKLIST`, and `_HEADER_FRAGMENTS`.
   - `_TECH_WORDS` only rejects if *all* words are tech terms (`lower_words.issubset(_TECH_WORDS)`).
   - `_GENERIC_WORDS` only rejects if $\ge 2$ words match its static 40-word dictionary.
   - Suffix/prefix title checks do not match `"insights"` or `"sub-space"`.
7. **Verdict:** `_is_name_line()` evaluates to `True`, and Strategy 2 returns `"Insights possible sub-space."` as the candidate's name.

---

## 4. Where False Non-Empty Names Lock Out Fallback

A false non-empty name extraction causes a catastrophic downstream lockout in two specific locations:

### A. Fallback Trigger Gate (`backend/src/extraction/markdown_extraction_service.py`)
In `MarkdownExtractionService.extract()` (`lines 71–73`):
```python
if not fields["name"]:
    missing_critical = True
```
Because `fields["name"]` is populated with `"Insights possible sub-space."`, `not fields["name"]` is `False`. The extraction pipeline concludes that candidate identity has been successfully resolved and does not mark `missing_critical = True` or package the contact header chunk for LLM infill (`lines 78–80`).

### B. Merge Protection Rule R-08 (`backend/src/extraction/fallback/nova_service.py`)
In `NovaService.resolve_chunks()` (`lines 74–76` and `_merge()`):
```python
# R-08 — NEVER overwrite a field already resolved by the deterministic engine.
```
Even if Nova is invoked to resolve other fields (e.g., missing experience), Rule R-08 strictly forbids overwriting any field where the deterministic parser returned a non-null value. Consequently, the false name is permanently preserved.

---

## 5. Scoring Policy Violations in Current Executable Code

Comparing `backend/src/ranking/scorer.py` against `docs/v2-release/SCORING-POLICY.md` reveals five active violations:

1. **Nice-to-Have Skill Inflation (`scorer.py:793`):**
   ```python
   nice_to_have_bonus = len(result.matched_nice_to_have) * 10.0
   ```
   Each matched nice-to-have skill adds a flat +10.0 points directly to `total_bonus`. A candidate matching 4 secondary skills gains +40.0 points, overwhelming core requirements.
2. **Non-Job-Relevant Hackathon Scoring (`scorer.py:364–381`):**
   `_cert_bonus()` parses raw resume text for hackathon keywords, granting +1.0 for wins and +0.5 for participation. `SCORING-POLICY.md` explicitly bans hackathon scoring unless the job description explicitly requires competitive programming.
3. **Hard Knockout Information Zeroing (`scorer.py:802–804`):**
   ```python
   if result.knocked_out:
       result.final_score = 0.0
   ```
   Zeroing the final score destroys explainability. `SCORING-POLICY.md` requires that sub-scores, evidence, and factor ledgers remain visible and calculated.
4. **Absence of Separate Decision Fields (`schemas/scoring.py:33–98`):**
   `ScoredCandidate` lacks distinct `relevance_score` vs. `eligibility_status` (`ELIGIBLE`, `REVIEW_REQUIRED`, `DOES_NOT_MEET_CRITERIA`), conflating algorithmic relevance with recruiter eligibility.
5. **Missing Score Lineage and Factor Ledger:**
   `ScoredCandidate` does not persist `score_version`, `policy_version`, `job_version`, normalized weights, or evidence provenance pointers.

---

## 6. ATS Diagnostic Limitations & Geometry Deficiencies

In `backend/src/ranking/ats_scorer.py`:

1. **Hardcoded Page Numbers (`ats_scorer.py:50`):**
   All bounding boxes emitted for column layout risks are hardcoded to `page=1`, regardless of which page the two-column structure actually occurs on.
2. **Fabricated Bounding Box Widths (`ats_scorer.py:53`):**
   ```python
   x1=line.x0 + len(line.text) * 5 # estimate width
   ```
   The right coordinate `x1` is calculated using an arbitrary 5-pixel-per-character multiplier rather than extracting real PDF glyph/span bounding boxes from PyMuPDF.
3. **Conflated Risk Dimensions:**
   Internal parser extraction quality and external ATS compatibility risk are conflated into a single penalization formula without separating extractor confidence from structural format risk.
4. **Missing Informational Fallback:**
   When exact geometry cannot be verified, the service currently synthesizes inaccurate coordinates rather than omitting the visual overlay and emitting an informational flag.

---

## 7. Test Coverage Audit: Existing vs. Missing Tests

### Existing Test Coverage
- `backend/tests/integration/test_v2_acceptance.py`: Covers security headers, auth registration, tenant isolation, PDF magic bytes, disabled FAANG prestige bonus, disabled career gap penalty, determinism, rejection reasons, CSV export, audit logs, and cascading deletion.
- `backend/tests/integration/test_scorer.py`: Tests candidate ranking outputs against 6 job descriptions.
- `backend/tests/test_domain_guardrails.py`: Tests domain classification proximity.
- `backend/tests/test_merge_rule.py`: Tests R-08/R-09 deterministic priority in `NovaService`.
- `backend/tests/unit/test_experience_parser.py`: Tests experience date regex lookarounds.

### Missing Test Coverage (Required for v2.2)
1. **Identity Resolution Unit Tests (`test_candidate_identity_resolver.py`):**
   - Standard header (`First Last` with email/phone).
   - All-caps name headers (`FIRST LAST`).
   - Inverted name headers (`Last, First`).
   - Two-column layouts with sidebar contact blocks.
   - Negative rejection of descriptive phrases, summary sentences, job titles, and specifically `"Insights possible sub-space."`.
   - International Latin-script names (accents, particles: `de`, `van`, `al`).
   - Scanned, garbled, or low-evidence resumes yielding `UNRESOLVED` (`display_name = null`).
2. **Scoring Policy Unit Tests (`test_scoring_policy_v2_2.py`):**
   - Proof that nice-to-have bonuses are bounded and cannot override missing must-have requirements.
   - Proof that hackathon mentions do not inflate scores.
   - Proof that low-confidence extractions trigger `eligibility_status = REVIEW_REQUIRED`.
   - Proof that knocked-out candidates retain full sub-score breakdowns and explanations.
3. **ATS Diagnostics Geometry Tests (`test_ats_diagnostics.py`):**
   - Verification that all bounding box coordinates fall strictly within actual PDF page dimensions.
   - Verification that bounding boxes reference the true page number.
   - Verification that ATS scoring never mutates candidate relevance scores or rank order.
4. **Frontend E2E Tests (Playwright):**
   - Verifying the "Name needs review" badge and warning icon when identity is unresolved.
   - Verifying the "Why this name?" identity provenance drawer in candidate detail.

---

*Baseline audit complete. Proceeding to P0 implementation.*
