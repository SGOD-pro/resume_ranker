# Resume Ranking System — Implementation Design Document

**Version**: 4B (Post Extraction Routing Refactor)
**Last Updated**: 2026-06-20
**Audience**: Developers, Reviewers, AI Assistants

---

## 1. Project Overview

### 1.1 Business Problem

Hiring teams spend **6–8 seconds** per resume in an initial screen. For a single job posting that receives 150–300 applications, this means 20–40 hours of manual review. The process has three critical flaws:

1. **Inconsistency**: Different reviewers weight criteria differently. A resume screened at 9am gets a different read than the same resume at 4pm.
2. **Keyword blindness**: Humans miss skill synonyms. A JD asking for "Kubernetes" will miss a candidate who wrote "K8s" or "container orchestration."
3. **Recency bias**: The last resume reviewed disproportionately influences comparison rankings.

### 1.2 Why This System Exists

This system automates the **screen** stage — not the **decision** stage. It takes PDF resumes and a structured Job Description, extracts candidate profiles, scores them on measurable criteria, and produces a ranked candidate list with explainable breakdowns.

The output is not "hire this person." The output is: "Here are your 20 candidates ordered by relevance to this specific JD, with per-field scoring breakdowns, anomaly flags, and knockout reasons."

### 1.3 Why Classical NLP (No LLMs)

Three constraints drove this decision:

1. **Determinism**: The same resume + JD pair must always produce the same score. LLM-based scoring introduces temperature-dependent variance.
2. **Explainability**: HR teams need to justify ranking decisions. "The model said 82%" is not defensible in regulated hiring. "Matched 8/10 must-have skills, 5.2 years experience vs 3yr minimum, bachelor's vs bachelor's required" is.
3. **Cost / Latency**: Processing 200 resumes through an LLM API costs $2–15 per batch and takes 3–10 minutes. This system processes 20 resumes in <3 seconds on a single core, zero API costs.

Embedding-based scoring is planned as a **supplement** (Phase 6+), not a replacement.

---

## 2. High-Level Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        RESUME RANKING SYSTEM                          │
│                                                                        │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐ │
│  │ Resume   │    │ Layout   │    │ Section  │    │ Field Extraction │ │
│  │ PDF      │───►│ Analysis │───►│ Detection│───►│ (6 Parsers)      │ │
│  │          │    │ PyMuPDF  │    │ Registry │    │                  │ │
│  └──────────┘    └──────────┘    └──────────┘    └────────┬─────────┘ │
│                                                            │           │
│                                                            ▼           │
│                                                   ┌────────────────┐  │
│                                                   │ Structured     │  │
│                                                   │ Candidate JSON │  │
│                                                   └────────┬───────┘  │
│                                                            │           │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │           │
│  │ Job      │    │ BM25 /   │    │ Ranking  │◄────────────┘           │
│  │ Descript.│───►│ TF-IDF   │───►│ Engine   │                         │
│  │          │    │ Scoring  │    │ 3-Phase  │                         │
│  └──────────┘    └──────────┘    └──────────┘                         │
│                                        │                               │
│                                        ▼                               │
│                               ┌────────────────┐                      │
│                               │ Ranked Results │                      │
│                               │ + Explanations │                      │
│                               └────────────────┘                      │
└────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Stages (Detailed)

```
Resume PDF
    │
    ▼
[1] PyMuPDF dict-mode extraction
    │   • Extracts words with font name, size, bbox, bold/italic flags
    │   • De-letterspaces "D E T A I L S" → "DETAILS"
    │   • Cleans (cid:XX) artifacts from corrupted font encodings
    │
    ▼
[2] Layout Classification
    │   • Detects column split via x-coordinate gap analysis
    │   • Identifies: single_column | two_column | header_sidebar_main | table_based
    │   • Classifies each line: doc_name, section_header, job_title, edu_line,
    │     date_range, bullet, body, sidebar_header, sidebar_value
    │
    ▼
[3] Block Detection
    │   • Maps spatial regions → semantic blocks: { header, sidebar, main, footer }
    │   • Separates full-width header band from body columns
    │
    ▼
[4] Section Detection (3 strategies)
    │   ├─ Layout tags (from [SECTION] markers in tagged text)
    │   ├─ Section detector (regex header matching on plain text)
    │   └─ Fallback detector (classified line scanning + header scoring)
    │
    ▼
[5] Unified Section Map (SectionContent)
    │   • Merges all 3 detection paths
    │   • Preserves tagged_text (for assembler) AND plain_text (for standalone)
    │   • Each section has source: "layout" | "section_detector" | "fallback"
    │
    ▼
[6] Field Extraction (Run-Both-Score-Both)
    │   ├─ Path A: ResumeAssembler (token state machine on tagged text)
    │   ├─ Path B: Standalone parsers (regex on plain text)
    │   └─ Quality scoring picks best result per field
    │
    ▼
[7] Normalized JSON
    │   • personal_info, summary, skills, experience, education,
    │     projects, certifications, languages
    │   • _clean_output: dedup, swap detection, tag stripping
    │
    ▼
[8] CandidateScorer (3-Phase Ranking)
        Phase 1: Hard knockout (missing must-have skills, insufficient years)
        Phase 2: Multi-signal scoring (BM25 skills, experience, keywords, education)
        Phase 3: Rank, percentile, bonuses, anomaly detection
```

---

## 3. Evolution of the Extraction Pipeline

### 3.1 Why Evolution Was Necessary

The pipeline went through 4 major versions. Each version solved a specific class of failure that only became visible after testing on real-world resumes.

> **Key insight**: You cannot design a resume parser from first principles. Resumes have no standard format, no guaranteed structure, and no consistent font usage. Every design decision is reactive — you build what you think works, test it against 20 real PDFs, and discover 5 failure modes you didn't anticipate.

### 3.2 Version 1 — Simple PDF Text Extraction

**Architecture**: `pdfplumber.extract_text()` → regex → JSON

**What worked**: Extracted contact info (email, phone) from simple single-column resumes.

**What failed**:
- **Two-column layouts**: Text extraction interleaved sidebar and main content. "Python" from the sidebar appeared between "Senior" and "Engineer" from the main column.
- **No section boundaries**: Without layout understanding, "Education" section content bled into "Experience."
- **No font information**: Couldn't distinguish headers from body text.

**Root cause**: `pdfplumber.extract_text()` returns a flat string. PDF is a spatial format, not a sequential one.

### 3.3 Version 2 — Layout Extraction

**Architecture**: `pdfplumber` with word-level extraction → column detection → classified lines → tagged text

**What it solved**:
- Column split detection (find x-coordinate gap between sidebar and main)
- Font-based role classification (bold + large = name, bold + small + UPPERCASE = section header)
- Spatial zone separation (header band, sidebar, main body)

**What failed**:
- **Font name variance**: Resumes used `EBGaramond-Medium`, `Roboto-Black`, `Inter-Medium` — none triggered the "Bold" check because the font name didn't literally contain "Bold."
- **Template diversity**: 5/20 resumes produced zero detected sections because the section headers didn't match font-based rules.
- **pdfplumber limitations**: `(cid:XX)` artifacts in corrupted fonts, slower extraction speed, less accurate bbox positioning than PyMuPDF.

### 3.4 Version 3 — Section Detection + Section Registry

**Architecture**: Layout extraction + section detection + section registry + fallback header detection

**What it solved**:
- **Section Registry** (Phase 1): Single source of truth for 140+ section aliases → 11 canonical sections. Every section name variant lives in one file.
- **Profession aliases** (Phase 2): Medical ("Clinical Experience" → experience), Legal ("Practice Areas" → experience), Sales ("Key Accounts" → experience).
- **SectionBlock model** (Phase 3): Each block carries `parser_source` tracking.
- **Section merging** (Phase 4A): Tagged sections (layout) merged with plain sections (detector), with fallback header detection for zero-section resumes.
- **Fallback detection** (Phase 4A.6): Two-strategy fallback for resumes where layout-based parsing found no sections — scans classified lines for left-column entries that resolve in the registry, scores header candidates on uppercase/length/position/registry-match.

**Impact**: Experience extraction went from 70% to 90%. Zero-section resumes went from 5 to 1 (the remaining one needs OCR).

### 3.5 Version 4 — Unified Routing

**Architecture**: Run-both-score-both for all fields. Unified section map preserving both tagged and plain text.

**What it solved**:
- **Primary/fallback anti-pattern**: The old code used assembler-first, standalone-fallback. Some resumes produced better results from the standalone parser even when the assembler had data. The fix: run both, score both, pick the winner using quality scoring.
- **Text preservation**: `SectionContent` preserves both `tagged_text` (with `[JOB_TITLE]`, `[DATE]`, `[BULLET]` tokens for the assembler) and `plain_text` (for standalone regex parsers). Neither path is degraded.
- **Content length arbitration**: When the section detector finds more content than the fallback detector (because the fallback incorrectly split a section at a spurious header), the longer content wins.

**Impact**: Certifications improved from 45% to 55%. Skills improved on 3 resumes. Zero regressions on experience, education, contact.

---

## 4. PDF Extraction Layer

### 4.1 Why pdfplumber Was Used Initially

pdfplumber was the original extraction library because:
- Pure Python, simple API: `pdf.pages[0].extract_words()`
- Word-level extraction with bbox coordinates
- Active community and documentation

### 4.2 Why PyMuPDF Replaced It

A 20-resume benchmark revealed:

| Metric | pdfplumber | PyMuPDF |
|---|---|---|
| Equal quality | 13/20 | 13/20 |
| Better quality | 0/20 | **7/20** |
| Avg quality score | 0.64 | 0.74 |
| Extraction speed | ~200ms/page | ~50ms/page |

PyMuPDF provides:
- **dict-mode** output: blocks → lines → spans with font name, size, color, bbox
- **Richer font metadata**: font flags, font name includes style variants
- **Faster extraction**: C-based core vs Python-based pdfplumber
- **Better CID handling**: Produces cleaner text from corrupted font subsets

> **Decision**: PyMuPDF became the sole extraction library. pdfplumber remains as a dependency but is not used in the active pipeline.

### 4.3 Font Corruption Case Study — Resume 16

**Symptom**: 0 sections detected, garbled contact info, `mark_for_ocr = True`.

**Root cause**: The PDF uses 3 font subsets with `Identity-H` encoding. One subset (`UCUEVF+Ubuntu-Regular`) has a **broken ToUnicode CMap** — it maps glyph IDs to wrong Unicode codepoints.

```
Garbled:   "1515 Pacivc A,eL osn ACgelenL 9A"
Expected:  "1515 Pacific Ave, Los Angeles, CA"
```

**Critical finding**: All 4 tested libraries (pdfplumber, PyMuPDF, pymupdf4llm, pdfminer) produce **identical garbled text**. The corruption is baked into the PDF's font encoding table, not the extraction library.

**133/661 words** across the entire resume are garbled. Only OCR (rendering glyphs to images, then running character recognition) can recover the correct text.

### 4.4 Why OCR Is Not Implemented Yet

1. Only 2/20 (10%) benchmark resumes actually need OCR
2. OCR adds Tesseract or a cloud API dependency (cost, latency, complexity)
3. The quality scoring system already flags corrupted PDFs with `mark_for_ocr = True`
4. The system extracts what it can from the non-corrupted font subsets

> **Design decision**: Flag corrupted PDFs for a future OCR queue. Do not block the entire pipeline on 10% edge cases.

---

## 5. Layout Detection

### 5.1 Layout Types

The system classifies every PDF into one of four layouts:

| Layout | Description | Example |
|---|---|---|
| `single_column` | ATS-style, stacked vertically | Traditional resume |
| `two_column` | Left sidebar (skills/contact) + right main | Canva templates |
| `header_sidebar_main` | Wide header band + two-column body | Creative resumes |
| `table_based` | Content in pipe-separated table rows | Spreadsheet-style |

### 5.2 Column Split Detection

```python
def _find_column_split(self, words, page_width):
    """
    Scan x-range 10%-75% of page.
    Find longest horizontal gap where no word starts.
    If gap > 30px AND separates meaningful content on both sides,
    that's the column split.
    """
```

The algorithm builds a set of word-start x-coordinates, then scans for the widest unoccupied gap. A gap must be at least 30px wide and fall between 10%–75% of the page width to qualify.

**Right-sidebar detection**: If the left column has 3x more words than the right column, the roles are swapped — the sidebar is actually on the right.

### 5.3 Why Layout Understanding Is Necessary

Without layout detection, a two-column resume produces:

```
Python          Senior Software
SQL             Engineer at Google
Docker          Jan 2021 – Present
```

Which text extraction reads as:

```
Python Senior Software SQL Engineer at Google Docker Jan 2021 – Present
```

Making it impossible to determine that "Python" is a skill and "Senior Software Engineer at Google" is a job title. Column detection separates these into distinct text streams before any parsing begins.

### 5.4 Line Classification

Each line is classified by font analysis:

| Role | Detection Rule |
|---|---|
| `doc_name` | Bold, font size ≥14pt, in header band |
| `doc_title` | In header band, smaller than doc_name |
| `section_header` | Bold, 8-10pt, ≤5 words, ALL_CAPS or matches registry |
| `job_title` | Bold, 9-10pt, not ALL_CAPS, not a header |
| `edu_line` | Contains degree keyword (Bachelor, Master, etc.) |
| `date_range` | Matches `Month Year – Month Year` pattern |
| `bullet` | Starts with •, ▪, -, * |
| `body` | Regular font, paragraph text |
| `sidebar_header` | In left column, matches registry keyword |
| `sidebar_value` | In left column, not a header |

---

## 6. Section Detection System

### 6.1 Section Registry ([section_registry.py](file:///home/swyra/Desktop/resume-ranking/section_registry.py))

The **single source of truth** for section names. No other module defines section aliases.

#### Canonical Sections

```
summary, experience, education, projects, skills,
certifications, languages, awards, achievements,
publications, references
```

#### Alias Mapping (140+ entries)

Every real-world variation of a section header maps to one canonical name:

```python
"EMPLOYMENT HISTORY"       → "experience"
"CLINICAL EXPERIENCE"      → "experience"    # Medical
"PRACTICE AREAS"           → "experience"    # Legal
"DEAL EXPERIENCE"          → "experience"    # Finance
"KEY ACCOUNTS"             → "experience"    # Sales
"INTERNSHIP AND TRAINING"  → "experience"    # Interns
"CORE COMPETENCIES"        → "skills"
"THERAPEUTIC MODALITIES"   → "skills"        # Medical
"BAR ADMISSIONS"           → "certifications"# Legal
"COURSES"                  → "certifications"
"CASE STUDIES"             → "projects"      # Consulting
"RESEARCH PROJECTS"        → "projects"      # Academic
```

#### Resolution API

```python
from section_registry import resolve

resolve("Employment History")   # → "experience"
resolve("CLINICAL EXPERIENCE")  # → "experience"
resolve("random text")          # → None
```

Resolution tries exact match on uppercased input, then strips trailing special characters (`/ - | &`) and retries.

#### Assembler Compatibility Layer

The `ResumeAssembler` (section_parser.py) uses internal canonical names (`"employment"`, `"profile"`, `"courses"`). The registry provides a translation map:

```python
ASSEMBLER_KEY_MAP = {
    "experience":      "employment",
    "summary":         "profile",
    "certifications":  "courses",
    "achievements":    "accomplishments",
}
```

### 6.2 Three Detection Strategies

```
Strategy 1: Layout Tags
    [EMPLOYMENT HISTORY]  ←  from layout_extractor (font-based detection)

Strategy 2: Section Detector
    Plain text line matching:
      if line is 1-5 words AND resolves in registry AND no year digits
      → section boundary

Strategy 3: Fallback Header Detector
    For zero-section resumes:
      Scan classified_lines for left-column entries resolving in registry.
      Score candidates: registry_match(+0.50) + uppercase(+0.15)
        + short_line(+0.15) + position(+0.10) + word_count(+0.10)
      Threshold: ≥ 0.5
```

### 6.3 Why Section Detection Was the Main Bottleneck

Before Phase 4A.6, **5/20 resumes** produced zero sections. The failures all shared the same pattern: left-sidebar layout with section headers in the sidebar column, using fonts that weren't flagged as "Bold."

| Resume | Font | Bold? | Headers Detected? |
|---|---|---|---|
| 6 | EBGaramond-Medium | No | ❌ |
| 7 | Roboto-Black | No ("Black" ≠ "Bold") | ❌ |
| 8 | Inter-Medium | No | ❌ |
| 14 | EBGaramond-Medium | No | ❌ |
| 16 | Ubuntu-Regular | N/A (corrupted) | ❌ |

The fallback header detector solved resumes 6, 7, 8, 14 by scanning classified lines in the sidebar and scoring them against the registry. Resume 16 requires OCR.

---

## 7. Structured Resume Extraction

### 7.1 ContactParser ([contact_parser.py](file:///home/swyra/Desktop/resume-ranking/contact_parser.py))

**Extracts**: name, email, phone, linkedin, github, location

**Strategy**: Zero NER. Pure regex + layout tags + heuristic name detection.

#### Name Detection (3-tier)

1. `[NAME]` tag from layout_extractor — bold large font, most reliable
2. Heuristic: first 10 lines, 2-4 words, no digits, no @, no URL, no section keywords
3. ALL CAPS line in first 5 lines (common resume template pattern)

#### Challenges

- **Job titles that look like names**: "Amanda Project Manager" — the parser maintains a blocklist of 80+ job title patterns (`_NOT_NAMES`)
- **Location confusion**: Names like "Charlotte Davidson" match city names. The parser cross-references against a US city set and country list.
- **Phone format variance**: US (`(555) 123-4567`), Indian (`+91 98765 43210`), European (`+44 20 7946 0958`). The regex handles 6 formats.

### 7.2 ExperienceParser ([experience_parser.py](file:///home/swyra/Desktop/resume-ranking/experience_parser.py))

**Extracts**: `[{ role, company, start, end, description, achievements }]`

**Anchor**: Date ranges are the most reliable signal. The parser finds all `Month Year – Month Year` patterns first, then extracts surrounding context.

```
                    ┌── before: role + company ──┐   ┌── anchor ──┐
"Senior Engineer at Google                         Jan 2021 – Present"
                                                    ┌── after: bullets ──┐
"• Built microservices handling 10M requests/day"
```

**Challenges**:
- **Company before role** (some templates flip the order): Detected by checking if the line before the date contains commas separating role and company.
- **Pipe-separated** (`Role | Company`): Split on `|` or `/` delimiters.
- **No dates**: Fallback `_parse_year_only` looks for standalone 4-digit years as anchors.
- **DATE-tag patterns**: Pipeline also checks for `[DATE]...[/DATE]` tagged text from layout_extractor as an additional path.

### 7.3 EducationParser ([education_parser.py](file:///home/swyra/Desktop/resume-ranking/education_parser.py))

**Extracts**: `[{ degree, institution, start, end, grade }]`

**Anchor**: Degree keywords — `Bachelor`, `Master`, `PhD`, `B.Tech`, `M.Sc`, `Diploma`, `Certificate`, `Class 12`.

Two parsing strategies:

1. **Line-based structured parsing**: Detects institution lines (contain "University", "College", "Institute") followed by degree lines. Handles institution-first layouts (common in Indian resumes).
2. **Anchor-based fallback**: Uses `DEGREE_RE` matches as anchors, extracts surrounding context.

**Challenges**:
- **Degree/institution swap**: Some resumes put the institution where the degree should be. The parser detects this with regex and swaps.
- **Grade formats**: GPA (`3.8/4.0`), CGPA (`7.84`), Percentage (`84.4%`), "First Class", "Distinction". All captured by `GRADE_RE`.
- **Major/Minor lines**: Lines starting with `Major:` or `Minor:` are merged into the preceding entry, not treated as new entries.
- **False positives**: `"MA" matches "March"`, `"BA" matches "Baltimore"`. Fixed with word boundary anchors on **both sides** of degree keywords.

### 7.4 SkillsParser ([skills_parser.py](file:///home/swyra/Desktop/resume-ranking/skills_parser.py))

**Extracts**: `List[str]` — deduplicated skill names with canonical casing

**Strategy**: Dictionary-based matching against `skills_dictionary.json` (600+ skills).

**Two-pass extraction**:

1. **Skills section scan**: Parse comma/pipe/bullet-separated entries from the detected skills section.
2. **Full-text dictionary scan**: Scan entire resume text against skill patterns. Uses word-boundary-aware regex for each skill in the dictionary (sorted longest-first to prevent partial matches).

**Fuzzy matching**: For garbled PDF text, uses `difflib.SequenceMatcher` with threshold 0.85 to match corrupted skill names (e.g., `"Pythn"` → `"Python"`).

**Anti-false-positive measures**:
- Location name rejection: `_LOCATION_RE` and `_US_CITY_SET` prevent city names from being extracted as skills
- Single-char handling: Only `R` and `C` are valid single-char skills
- Non-skill blocklist: "hobbies", "interests", "activities", etc.

### 7.5 ProjectParser ([project_parser.py](file:///home/swyra/Desktop/resume-ranking/project_parser.py))

**Extracts**: `[{ name, technologies, description, github, demo }]`

**Strategy**: Block-based parsing. Splits project section into blocks (double-newline or project-header boundaries), then extracts structured fields from each block.

**Technology detection**: Reuses `SkillsParser` to scan project descriptions for technology mentions. Also detects `Technologies: ...` or `Built with: ...` header patterns.

**Hyperlink assignment**: PDF hyperlinks extracted by PyMuPDF are matched to projects by checking if GitHub URLs or demo links appear near project descriptions.

**Challenges**:
- **Project name detection**: Unreliable because there's no consistent marker. The parser uses the first non-bullet, non-technology line in each block.
- **Minimal project sections**: Many resumes list projects as a single paragraph. Block splitting may produce only 1 "project" with all content.

---

## 8. Unified Extraction Routing (Phase 4B)

### 8.1 Previous Architecture (Pre-4B)

```python
# Old: Assembler-first, Standalone-fallback
if asm_has_experience:
    experience = assembler_result['employment_history']
else:
    experience = experience_parser.parse(plain_text)
```

**Problem**: The assembler sometimes produced lower-quality results than the standalone parser, but won by default because it had *any* data. On resumes 1, 6, 7, 14, the assembler extracted roles without companies, or split entries incorrectly, while the standalone parser found cleaner entries.

### 8.2 SectionContent Dataclass

```python
@dataclass
class SectionContent:
    plain_text: str = ""       # For ExperienceParser, EducationParser (regex)
    tagged_text: str = ""      # For ResumeAssembler (token state machine)
    source: str = "unknown"    # "layout", "section_detector", "fallback"
```

**Why both texts are needed**: The `ResumeAssembler` requires `[JOB_TITLE]`, `[DATE]`, `[BULLET]` tokens to drive its state machine. Stripping tags for the assembler breaks it. The standalone `ExperienceParser` needs clean text without tags because its `DATE_RANGE_RE` regex can't parse through `[DATE]Jan 2021[/DATE]` tokens.

Storing both preserves full fidelity for each path.

### 8.3 UnifiedSections Builder

`_build_unified_sections()` merges three sources:

```
Priority 1: Layout-extracted tagged sections    → tagged_text + tag-stripped plain_text
Priority 2: Section detector plain text         → fills gaps OR upgrades with longer content
Priority 3: Fallback-detected sections          → fills remaining gaps
```

**Key design decision**: When the section detector finds **longer** `plain_text` than what was tag-stripped from the layout source, the longer version replaces the existing `plain_text`. This handles cases where the fallback detector incorrectly split a section (e.g., resume `souvik` where `CGPA: 7.84` was detected as a section header, cutting the education section short).

### 8.4 Run-Both-Score-Both

```python
# Run both extraction paths
exp_assembler = [assembler_result['employment_history']]
exp_standalone = experience_parser.parse(unified.plain_text)

# Score both
score_asm = _score_experience_entries(exp_assembler)
score_std = _score_experience_entries(exp_standalone)

# Quality wins
experience = exp_assembler if score_asm > score_std else exp_standalone
```

### 8.5 Quality Scoring

#### Experience Scoring

Per-entry:

| Factor | Points | Condition |
|---|---|---|
| Complete role | +2.0 | Non-empty, non-generic (`intern`, `trainee`, `employee` excluded) |
| Complete company | +2.0 | Non-empty company name |
| Complete dates | +1.0 | Has start date |
| Has description | +0.5 | Has description text or achievements list |

Plus `entry_count × 0.5` bonus.

**Why not "more entries wins"**: A standalone parser might produce 3 entries with only role names and no companies, while the assembler produces 1 entry with role, company, dates, and description. The 1 complete entry should win:

```
Assembler: score = (2+2+1+0.5) + 0.5 = 6.0    ← 1 complete entry
Standalone: score = (2+0+0+0)*3 + 1.5 = 7.5    ← 3 role-only entries
```

This scoring formula correctly picks the assembler in most real cases because the company (+2.0) and dates (+1.0) weights dominate the entry count bonus (+0.5 per entry).

#### Education Scoring

Same structure: degree (+2.0), institution (+2.0), dates (+1.0), grade (+0.5), plus entry_count × 0.5.

### 8.6 Benchmark Improvements

| Metric | Before 4B | After 4B | Δ |
|---|---|---|---|
| Summary | 90% | 90% | = |
| Experience | 90% | 90% | = |
| Education | 100% | 100% | = |
| Skills | 100% | 100% | = (3 resumes improved) |
| Certifications | 45% | **55%** | **+10pp** |
| Contact | 86% | 86% | = |

---

## 9. Data Schema

### 9.1 Complete Output Schema

```json
{
  "personal_info": {
    "name": "string | null",
    "email": "string | null",
    "phone": "string | null",
    "linkedin": "string | null",
    "github": "string | null",
    "location": "string | null"
  },

  "summary": "string | null",

  "skills": ["Python", "SQL", "Docker", "..."],

  "experience": [
    {
      "role": "Senior Software Engineer",
      "company": "Google",
      "start": "Jan 2021",
      "end": "Present",
      "location": "Mountain View, CA",
      "description": "Led backend team...",
      "achievements": [
        "Reduced latency by 40%",
        "Migrated 3 services to Kubernetes"
      ]
    }
  ],

  "education": [
    {
      "degree": "Bachelor of Science in Computer Science",
      "institution": "MIT",
      "start": "2015",
      "end": "2019",
      "grade": "3.8/4.0"
    }
  ],

  "projects": [
    {
      "name": "Real-time Chat App",
      "technologies": ["React", "Node.js", "WebSocket"],
      "description": "Built a scalable...",
      "github": "https://github.com/user/repo",
      "demo": null
    }
  ],

  "certifications": [
    {
      "name": "AWS Solutions Architect",
      "issuer": "Amazon",
      "date": "2023"
    }
  ],

  "languages": ["English", "Spanish"],

  "raw_text_sections": {
    "full_text": "...",
    "summary_text": "...",
    "skills_text": "..."
  },

  "extraction_quality": 0.85
}
```

### 9.2 ExtractionResult Wrapper

```python
@dataclass
class ExtractionResult:
    document_id: str              # "resume_1.pdf"
    domain: str                   # "resume"
    domain_confidence: float      # 0.0–1.0
    extraction_strategy: str      # "layout_first_v3"
    page_count: int               # from PyMuPDF
    layout_type: str              # "two_column", "single_column", etc.
    fields: Dict[str, Any]        # the JSON above
    warnings: List[str]           # extraction warnings
    metadata: Dict[str, Any]      # telemetry, quality scores, debug info
```

### 9.3 Metadata Fields (Telemetry)

```python
metadata = {
    "text_quality_score": 0.85,        # character-level quality
    "semantic_quality_score": 0.90,     # word-level quality
    "mark_for_ocr": False,              # True if text is garbled
    "extraction_engine": "pymupdf",
    "layout_type": "two_column",
    "section_count": 7,
    "sections_found": ["summary", "experience", "education", "skills", ...],
    "sections_missing": ["projects", "languages"],
    "section_sources": {"summary": "layout", "experience": "section_detector"},
    "fallback_detector_used": False,
    "summary_found": True,
    "skills_count": 12,
    "experience_count": 3,
    "education_count": 2,
    "certifications_count": 1,
}
```

---

## 10. Data Quality and Validation

### 10.1 Text Quality Scoring

```python
def _compute_text_quality(self, text: str) -> float:
    """
    Character-level quality: ratio of printable ASCII + common Unicode
    to total characters. Garbled text has low ratios.
    """
```

**Scores**: 0.0 (completely garbled) to 1.0 (clean text). Threshold: < 0.5 triggers `mark_for_ocr`.

### 10.2 Semantic Quality Scoring

```python
def _compute_semantic_quality(self, text: str) -> float:
    """
    Word-level quality: ratio of dictionary words to total words.
    Detects semantically garbled text that passes character-level checks.
    """
```

**Why both scores**: Resume 16's garbled text has high alphabetic ratio (the garbled characters are still letters), so `text_quality_score` is deceptively high. The semantic check catches it because the "words" aren't real English words.

### 10.3 Extraction Quality Score

```python
def _compute_quality(self, personal_info, skills, experience, education):
    """
    Field-level quality: weighted score based on how many fields were extracted.
      name found:     +0.25
      email found:    +0.15
      skills > 0:     +0.20
      experience > 0: +0.25
      education > 0:  +0.15
    """
```

This score is attached to the candidate data and used by the scorer's anomaly detection to flag low-quality extractions.

### 10.4 Benchmark Methodology

Every pipeline change is validated against the full 20-resume benchmark:

1. **Baseline capture**: `benchmark_before_{phase}.json` saved before any code change
2. **After capture**: `benchmark_after_{phase}.json` saved after changes
3. **Per-resume comparison**: Every field count compared. Improvements and regressions listed.
4. **Threshold check**: Each field must meet minimum accuracy. No change is merged if any threshold fails.

| Field | Threshold |
|---|---|
| Summary | ≥ 18/20 (90%) |
| Experience | ≥ 17/20 (85%) |
| Education | ≥ 20/20 (100%) |
| Skills | ≥ 20/20 (100%) |
| Certifications | ≥ 9/20 (45%) |
| Contact | ≥ 69/80 (86%) |

### 10.5 Regression Prevention

Every phase captures a before/after comparison. Per-resume regressions are **individually investigated** — the count drop is not sufficient; we need to know **why** the number changed and whether it represents an actual quality loss or a reclassification improvement.

Example: Resume 17 edu 3→1 was **not** a regression. The 2 "education" entries that disappeared were certificates ("Retail Sales Management Certificate", "Six Sigma Yellow Belt") that were previously parsed as education by the degree keyword fallback. Phase 4B correctly routed them to certifications.

---

## 11. Job Description Processing

### 11.1 JobDescription Schema

```python
@dataclass
class JobDescription:
    title: str                           # "Senior Backend Engineer"
    department: str = ""                 # "Engineering"
    description: str = ""                # Free-text JD body
    must_have_skills: List[str]          # Hard requirements ["Python", "SQL"]
    nice_to_have_skills: List[str]       # Soft requirements ["Docker", "K8s"]
    min_years: int = 0                   # Minimum experience years
    max_years: int = 99                  # Maximum (avoids overqualified)
    required_degree: str = "any"         # "bachelor", "master", "phd", "any"
    preferred_field: str = ""            # "Computer Science"
    keywords: List[str]                  # Domain keywords for text matching
    weights: Dict[str, float]            # Scoring weights per dimension
```

### 11.2 Configurable Weights

Default weights reflect typical technical hiring priorities:

```python
weights = {
    "skills":     0.40,    # Skill match is most important
    "experience": 0.25,    # Years + title similarity
    "keywords":   0.20,    # Domain keyword overlap
    "education":  0.15,    # Degree level + field match
}
```

These are **tunable per JD**. A fresher-friendly JD might set `experience: 0.10, skills: 0.50`. A senior management role might set `experience: 0.35, education: 0.05`.

### 11.3 JD Examples

The system is tested against 4 diverse JDs:

| JD | Domain | Must-Have | Min Years |
|---|---|---|---|
| Senior Backend Engineer | Engineering | Python, SQL | 3 |
| Digital Marketing Manager | Marketing | SEO, Marketing | 2 |
| Security Guard | Operations | Surveillance, Access Control | 1 |
| Junior Web Developer | Engineering | HTML, CSS, JavaScript | 0 |

This validates that the scoring system works across professions — not just IT.

---

## 12. Feature Engineering

### 12.1 Text Normalization

```python
def _normalize_skill(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'\.js$', 'js', s)      # "react.js" → "reactjs"
    s = re.sub(r'[.\-/]', '', s)       # "node.js" → "nodejs"
    s = s.replace(' ', '')             # "machine learning" → "machinelearning"
    return s
```

### 12.2 Skill Alias Resolution

70+ aliases handle abbreviations, typos, and alternate spellings:

```python
_SKILL_ALIASES = {
    'js': 'javascript', 'ts': 'typescript', 'py': 'python',
    'k8s': 'kubernetes', 'kubernates': 'kubernetes',  # common typo
    'tf': 'terraform', 'terrform': 'terraform',       # another typo
    'react': 'reactjs', 'node': 'nodejs',
    'postgres': 'postgresql', 'mongo': 'mongodb',
    'sklearn': 'scikitlearn',
    'seo': 'searchengineoptimization',
    ...
}
```

### 12.3 Tokenization

```python
def _tokenize(text: str) -> List[str]:
    return re.findall(r'[a-z0-9]+', text.lower())
```

Simple alphanumeric tokenization. No stemming or lemmatization — intentional. Stemming conflates "Managing" and "Management" which can cause false keyword matches in scoring.

### 12.4 Experience Year Calculation

```python
def _compute_total_experience_years(experience):
    """
    1. Parse all date ranges (start, end)
    2. Sort chronologically
    3. Merge overlapping ranges (avoids double-counting concurrent roles)
    4. Sum total days / 365.25
    """
```

**Why overlap merging matters**: A candidate with two concurrent part-time roles (Jan 2020–Dec 2022 and Jun 2021–Dec 2022) has 3.0 years of experience, not 4.5.

---

## 13. TF-IDF Scoring System

### 13.1 What TF-IDF Is

**Term Frequency–Inverse Document Frequency** measures how important a word is to a document relative to a corpus.

- **TF (Term Frequency)**: How often a term appears in a single document, normalized by document length.
- **IDF (Inverse Document Frequency)**: How rare a term is across all documents. Common words (the, and, is) get low IDF. Rare words (Kubernetes, GraphQL) get high IDF.

### 13.2 Why TF-IDF Was Selected

1. **Zero dependencies**: Implemented in ~30 lines of Python. No scikit-learn, no numpy.
2. **Interpretable**: Each term's contribution to the score is visible and explainable.
3. **Corpus-adaptive**: As more resumes are processed, IDF values naturally adjust. A skill that every candidate has (e.g., "Microsoft Office") contributes less to differentiation.
4. **Fast**: O(n) computation per document pair.

### 13.3 Mathematical Foundation

**Term Frequency** (normalized):

```
TF(t, d) = count(t in d) / |d|
```

Where `|d|` is the total number of tokens in document `d`.

**Cosine Similarity** between two TF vectors:

```
cos(A, B) = (A · B) / (||A|| × ||B||)

         Σ(A_i × B_i)
= ────────────────────────────
  √(Σ A_i²) × √(Σ B_i²)
```

### 13.4 BM25 Skill Scoring (Enhanced TF-IDF)

For skill matching, the system uses **BM25** instead of raw TF-IDF because BM25 handles binary skill presence (you either have Python or you don't) better than term frequency counts.

```python
def _bm25_skill_score(candidate_skills, jd_skills, all_candidates_skills,
                      k1=1.5, b=0.75):
    """
    IDF = log((N - df + 0.5) / (df + 0.5) + 1.0)
    
    Where:
      N  = total candidates
      df = candidates who have this skill
    
    Per-skill BM25 component:
      score += IDF * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl/avgdl))
    
    Normalized to 0-100 scale.
    """
```

**Why BM25 over raw count**: If 19/20 candidates have "Python", matching Python is not differentiating (low IDF). But if only 2/20 have "Kubernetes", matching Kubernetes is highly differentiating (high IDF). BM25 captures this.

### 13.5 Worked Example

**JD**: Senior Backend Engineer. Must-have: Python, SQL. Nice-to-have: Docker, Kubernetes, AWS.

**Candidate A**: Skills = [Python, SQL, Docker, React, JavaScript]
**Candidate B**: Skills = [Python, SQL, Kubernetes, AWS, Docker]

Assume 20 candidates total:
- Python: 15/20 have it → IDF = log((20-15+0.5)/(15+0.5)+1) = 0.36
- SQL: 12/20 have it → IDF = 0.56
- Docker: 8/20 have it → IDF = 1.06
- Kubernetes: 3/20 have it → IDF = 2.06
- AWS: 5/20 have it → IDF = 1.59

**Candidate A**: Matches Python (0.36) + SQL (0.56) + Docker (1.06) = 1.98
**Candidate B**: Matches Python (0.36) + SQL (0.56) + Docker (1.06) + Kubernetes (2.06) + AWS (1.59) = 5.63

Candidate B scores significantly higher because they match the **rare** skills (Kubernetes, AWS) that fewer candidates have.

---

## 14. Candidate Ranking Algorithm

### 14.1 Three-Phase Scoring

```
Phase 1: Hard Knockout
    ├── Missing must-have skills?         → KNOCKED OUT
    ├── Insufficient experience years?    → KNOCKED OUT (with leniency)
    └── Required degree not met?          → KNOCKED OUT

Phase 2: Multi-Signal Scoring (0–100 per dimension)
    ├── Skill Score (BM25)                × weight (default 0.40)
    ├── Experience Score                  × weight (default 0.25)
    │     └── Title similarity (40%) + Years in range (40%) + Recency (20%)
    ├── Keyword Score                     × weight (default 0.20)
    │     └── JD keyword presence in candidate text
    └── Education Score                   × weight (default 0.15)
          └── Degree level match (60%) + Field similarity (40%)

Phase 3: Rank & Explain
    ├── Add bonuses (capped at 100 total)
    │     ├── Project-skill bonus          (0–5.0 pts)
    │     ├── Prestigious company bonus    (0–4.0 pts)
    │     └── Certification bonus          (0–5.0 pts)
    ├── Sort by final_score descending (knocked-out → bottom)
    ├── Assign ranks (1-based)
    ├── Compute percentiles (among non-knocked-out)
    └── Flag anomalies (fresher, overqualified, employment gap, low quality)
```

### 14.2 Knockout Leniency

The knockout phase is intentionally lenient to avoid false disqualifications:

- **Must-have skills**: If a skill is missing from the structured `skills` list, the system does a **second-chance raw text search** across the entire resume. This catches skills mentioned in descriptions but not in the skills section.
- **Minimum years**: If the candidate has ≥2 job entries (suggesting experience even if dates are unparseable), they are **not** knocked out. Also checks raw text for "X years of experience" patterns.
- **Required degree**: Checks both structured education entries and raw text for degree mentions.

### 14.3 Bonus Scoring

**Project-skill bonus (0–5.0)**: Candidates who built real projects using JD-required technologies demonstrate practical ability beyond listing skills. `ratio = matched_project_skills / jd_skills; bonus = min(5.0, ratio * 6.0)`.

**Prestigious company bonus (0–4.0)**: Working at 100+ recognized companies (FAANG, Big4 consulting, Fortune 500, top-tier Indian IT) adds 2.0 points per match, capped at 4.0. Only matches against the structured `company` field to avoid false positives from URLs.

**Certification bonus (0–5.0)**: Relevant certifications (matched against JD domain keywords) add 0.15 per cert, or 0.25 if from a prestigious issuer (Google, AWS, Microsoft, CompTIA, etc.). Hackathon wins add 1.0, participation adds 0.5.

### 14.4 Ranking Example

```
JD: Senior Backend Engineer | Must-have: Python, SQL | Min: 3yr

  🏆 #1  Sarah Chen              72.3%  ████████████████░░░░
       Skills: 85×40%=34.0  |  Exp: 90×25%=22.5  |  KW: 60×20%=12.0  |  Edu: 80×15%=12.0
       ⭐ Bonus: Prestige:+2.0 | Cert:+0.3 = +2.3
       Exp: 5.2yr | Degree: Bachelor of Science in CS
       ✅ Must-have: Python, SQL
       ✅ Nice-to-have: Docker, Kubernetes, AWS
       🏢 Prestige: Google

  🥈 #2  James Park              58.1%  ████████████░░░░░░░░
       Skills: 70×40%=28.0  |  Exp: 75×25%=18.8  |  KW: 45×20%=9.0  |  Edu: 60×15%=9.0
       Exp: 3.8yr | Degree: Bachelor of Engineering
       ✅ Must-have: Python, SQL
       ⚠ Missing: Docker, Kubernetes

  ❌ #5  Alex Fresh              KNOCKED OUT
       → Missing must-have skills: SQL
       → Insufficient experience: 0.5yr vs 3yr required
```

---

## 15. Benchmarking and Evaluation

### 15.1 Benchmark Dataset

20 real-world resumes across multiple domains:

| Category | Resumes | Challenges |
|---|---|---|
| IT / Engineering | 8 | Two-column, projects, multiple roles |
| Marketing | 3 | Non-technical skills, campaign descriptions |
| Security / Operations | 2 | Non-standard sections, minimal education |
| Medical / Healthcare | 2 | Clinical experience aliases, certifications |
| Design | 2 | Creative layouts, portfolio links |
| Student / Fresher | 2 | No experience, projects as primary signal |
| Corrupted | 1 | Font encoding corruption (Resume 16) |

### 15.2 Phase-by-Phase Accuracy History

| Phase | Summary | Experience | Education | Skills | Certifications | Contact |
|---|---|---|---|---|---|---|
| Baseline (V2) | 90% | 75% | 100% | 100% | 25% | 86% |
| 4A.55 (PyMuPDF) | 90% | 70% | 100% | 100% | 30% | 86% |
| 4A.6 (Fallback) | 90% | **90%** | 100% | 100% | **45%** | 86% |
| **4B (Unified)** | 90% | 90% | 100% | 100% | **55%** | 86% |

### 15.3 Key Observations

1. **Experience was the hardest field**: Went through 4 phases to reach 90%. The remaining 10% are genuine edge cases (student resume with no experience, font-corrupted resume).
2. **Education was never broken**: 100% across all phases. Degree keywords are reliable anchors.
3. **Certifications improved most**: 25% → 55% across phases. Originally undercounted because many resumes list certs under "Courses" or "Training" — fixed by registry expansion and unified routing.
4. **Contact accuracy plateau at 86%**: The missing 14% is 3 resumes where location is ambiguous (embedded in title) or phone is in a non-standard format.

---

## 16. Known Limitations

### 16.1 OCR Not Implemented

2/20 resumes (10%) have font encoding corruption that **no text extraction library** can fix. These PDFs need OCR. The system flags them with `mark_for_ocr = True` but does not process them through OCR.

### 16.2 Font Corruption (Resume 16 Pattern)

Some PDF generators embed custom font subsets with broken `ToUnicode` CMaps. The garbled text is baked into the PDF structure. Character substitution is partially predictable per font (e.g., `@` → `m`, `C` → `n`) but building a per-font mapping table is fragile and not scalable.

### 16.3 Limited Certification Ground Truth

Only 55% of resumes have certifications extracted. Many certifications are mentioned in free text without a dedicated "Certifications" section, or are embedded in education descriptions. The system currently handles sections named "Courses", "Training", "Licenses", "Credentials", "Professional Development" but may miss certifications mentioned as bullet points under experience.

### 16.4 No Semantic Embeddings

The current scoring uses BM25 (term-level matching) and TF cosine similarity. It cannot understand that "built scalable microservices" is semantically related to a JD asking for "distributed systems experience." This requires sentence-level embeddings (SBERT, OpenAI embeddings, etc.).

### 16.5 Single-Language Only

The extraction pipeline is English-only. Multi-language resumes (e.g., French headers with English content) will have partially missing sections.

### 16.6 Photo-Heavy Resumes

Some creative resumes use large images for layout backgrounds, skill charts, or profile photos. PyMuPDF extracts text blocks but may miss text rendered as images (infographic-style skill bars, for example).

---

## 17. Future Roadmap

### Phase 5: Target Schema Completion

- Normalize all date formats to ISO 8601
- Validate experience year calculations against stated totals
- Add `years_of_experience` computed field

### Phase 6: Embedding-Based Scoring (Planned)

```
Candidate: "Built microservices handling 10M req/day using gRPC"
JD:        "Experience with distributed systems"
                                                    
TF-IDF: 0.0 (no shared terms)
Embedding: 0.82 (semantically similar)
```

Hybrid approach: `final = 0.6 * BM25_score + 0.4 * embedding_score`

### Phase 7: OCR Pipeline

For the 10% of resumes with font corruption:

```
PDF → Render page to image (300 DPI) → Tesseract OCR → Clean text
                                                            │
                                                            ▼
                                              Merge with PDF-extracted text
                                              (use OCR only for corrupted sections)
```

### Phase 8: Better Project Extraction

- Detect GitHub repository names and fetch README descriptions
- Parse hackathon projects from linked portfolios
- Extract technologies from project URLs

### Phase 9: Multi-Language Support

- Language detection per section
- Translation pipeline for non-English sections
- Multilingual skill dictionary

### Phase 10: Frontend Dashboard

- Candidate ranking table with sortable columns
- Per-candidate drill-down with section-by-section extraction view
- JD configuration UI with weight sliders
- Batch upload and processing queue

---

## 18. Key Architectural Lessons

### 18.1 What Worked

**Section Registry as single source of truth**: Before the registry, section aliases were scattered across `section_parser.py`, `section_detector.py`, and `pipeline.py`. Each file had its own subset of aliases, leading to inconsistent section detection. Centralizing to one file with one `resolve()` function eliminated an entire class of bugs.

**Run-both-score-both over primary/fallback**: The most impactful architectural decision. Instead of betting on one extraction path, running both and scoring the results always picks the better one. The key insight is that "which path is better" varies per resume — there is no globally correct primary path.

**Benchmark-driven development**: Every code change is gated on 20-resume benchmark comparison. This prevented 3 regressions that would have shipped without the check (resume 17 education, resume 7 education, souvik education).

**Quality scoring over entry counting**: The user's explicit instruction — "Don't use more entries wins" — prevented a subtle bug. Entry count is a poor proxy for extraction quality. Quality scoring (role completeness, company presence, date presence) is more robust.

### 18.2 What Failed

**Font-name-based header detection**: The original assumption that section headers are always in "Bold" fonts failed on 4/20 resumes. Fonts named `EBGaramond-Medium`, `Roboto-Black`, `Inter-Medium` are visually bold but their font names don't contain "Bold." The fix was fallback detection using registry matching + header scoring — but the real lesson is: never rely on a single signal for classification.

**pdfplumber as primary extractor**: Chosen for its Python-native simplicity, it was outperformed by PyMuPDF on 7/20 resumes and never outperformed it. The migration cost ~4 hours but the quality improvement was permanent.

**Eager refactoring**: An early attempt to rewrite extraction routing (Phase 4B) before stabilizing section detection (Phase 4A.6) would have made debugging impossible — changing inputs and processing simultaneously. The user's instruction to "fix extraction accuracy first, then refactor routing" saved significant debugging time.

### 18.3 What Was Unexpectedly Difficult

**Section detection in two-column layouts**: This was the system's #1 bottleneck for 3 phases. The problem wasn't missing headers — the headers were there, but classified as `sidebar_value` instead of `section_header` because they were in the left column with non-bold fonts. The fix required a completely new detection strategy (fallback detector) that bypasses font analysis entirely and relies on registry matching + positional scoring.

**Education vs certification classification**: "Retail Sales Management Certificate" — is this education or a certification? It contains "Certificate" (a degree keyword) but is really a professional certification. The resolution: map the COURSES section header to `certifications` canonical, and rely on degree keyword regex only as a last-resort fallback for education extraction.

**Tag stripping without losing structure**: The assembler needs `[JOB_TITLE]`, `[DATE]`, `[BULLET]` tags. The standalone parsers need clean text. Stripping tags eagerly breaks the assembler. Not stripping breaks regex parsers. The `SectionContent` dataclass (storing both tagged and plain text) was the solution — but it took 2 phases to arrive at.

### 18.4 What Should Never Be Rewritten

**Section Registry**: Modifying the alias map is safe (add new entries). Changing the resolution API or canonical names breaks every downstream module.

**Quality scoring formula**: The weights (role=2, company=2, dates=1, description=0.5) were calibrated against 20 resumes. Changing them without full benchmark validation will cause regressions.

**The fallback chain**: Experience has a 4-level fallback chain (assembler → standalone → sidebar → pattern-based). Each level exists because a specific resume needed it. Removing any level will regress that resume.

---

## Appendix A: File Map

| File | Purpose | Lines |
|---|---|---|
| [pipeline.py](file:///home/swyra/Desktop/resume-ranking/pipeline.py) | Core orchestrator. ExtractionResult, SectionContent, PDFPipelineV3 | ~2330 |
| [layout_extractor.py](file:///home/swyra/Desktop/resume-ranking/layout_extractor.py) | PyMuPDF extraction, column detection, line classification, DocumentStructure | ~883 |
| [section_registry.py](file:///home/swyra/Desktop/resume-ranking/section_registry.py) | Section alias map (140+ entries), resolve() API, assembler compatibility | ~278 |
| [section_detector.py](file:///home/swyra/Desktop/resume-ranking/section_detector.py) | Plain-text section boundary detection | ~70 |
| [section_parser.py](file:///home/swyra/Desktop/resume-ranking/section_parser.py) | Token state machine, ResumeAssembler, EmploymentParser, EducationParser | ~742 |
| [scorer.py](file:///home/swyra/Desktop/resume-ranking/scorer.py) | CandidateScorer, BM25, TF-IDF, knockout, bonuses, ranking | ~1225 |
| [contact_parser.py](file:///home/swyra/Desktop/resume-ranking/contact_parser.py) | Regex-only name/email/phone/linkedin/github extraction | ~361 |
| [experience_parser.py](file:///home/swyra/Desktop/resume-ranking/experience_parser.py) | Date-anchored experience extraction | ~112 |
| [education_parser.py](file:///home/swyra/Desktop/resume-ranking/education_parser.py) | Degree-anchored education extraction | ~352 |
| [skills_parser.py](file:///home/swyra/Desktop/resume-ranking/skills_parser.py) | Dictionary-based skill matching + fuzzy match | ~250 |
| [project_parser.py](file:///home/swyra/Desktop/resume-ranking/project_parser.py) | Block-based project extraction with technology detection | ~207 |
| [domain_detector.py](file:///home/swyra/Desktop/resume-ranking/domain_detector.py) | Document type classification (resume/finance/legal/medical) | ~97 |
| [block_detector.py](file:///home/swyra/Desktop/resume-ranking/block_detector.py) | Semantic block mapping (header/sidebar/main/footer) | ~39 |
| [main.py](file:///home/swyra/Desktop/resume-ranking/main.py) | CLI entry point | ~36 |
| [test_scorer.py](file:///home/swyra/Desktop/resume-ranking/test_scorer.py) | Ranking integration tests (4 JDs × 20 resumes) | ~146 |
| [skills_dictionary.json](file:///home/swyra/Desktop/resume-ranking/skills_dictionary.json) | 600+ skill names for dictionary matching | — |

## Appendix B: Dependencies

```toml
[project]
requires-python = ">=3.14"
dependencies = [
    "pymupdf>=1.27.2.3",        # Primary PDF extraction (dict-mode)
    "pymupdf4llm>=1.27.2.3",    # Markdown conversion (investigation only)
    "pdfplumber>=0.11.10",      # Legacy, not used in active pipeline
    "nltk>=3.9.4",              # Tokenization utilities
    "click>=8.4.1",             # CLI argument parsing
]
```

**Note**: The scorer has zero external NLP dependencies. TF-IDF, BM25, cosine similarity, and tokenization are all implemented in pure Python (~100 lines in `scorer.py`).
