# Project Report: AI Resume Screening & Candidate Ranking System

**Type:** Internship Project Submission Report  
**Author:** Candidate for Technical Review  
**Subject:** Resume Intelligence Platform — End-to-End Design, Implementation, and Benchmarking  
**Status:** **🔵 Production Ready (v9 Baseline)**

---

## Executive Summary

The **AI Resume Screening & Candidate Ranking System** is a complete, production-grade enterprise software application designed to automate the initial stages of high-volume recruiting. Screening resumes manually is a slow, error-prone, and expensive process. This system solves that problem by extracting, normalising, and scoring applicant resumes against a structured Job Description (JD). 

Unlike standard machine learning solutions that rely on heavy neural networks, GPU infrastructure, and opaque vector embeddings, this platform leverages a **deterministic rules-and-regex architecture**, a **graph-based skill inference engine**, and classic information retrieval algorithms (**BM25 and TF-IDF Cosine Similarity**). The system achieves a **97.8% domain classification accuracy** and maintains a **1.5% true false-positive rate** across a large multi-domain benchmark corpus of **3,856+ resumes**, making it highly accurate, explainable, and cheap to run.

---

## 1. Problem Analysis

### 1.1 The Recruitment Bottleneck
In modern recruitment, popular job postings routinely attract hundreds or thousands of applicants. HR teams and recruiters face the daunting task of reviewing every submission. Statistics show that:
*   An average corporate job opening receives **250+ resumes**.
*   Recruiters spend an average of **6–7 seconds** on their first-pass screening of a resume.
*   Up to **75–80% of applicants** are unqualified or belong to entirely mismatched professional domains (e.g., healthcare workers applying to engineering positions).

This manual screening process is a massive bottleneck. It delays hiring, increases the Cost-Per-Hire (CPH), and introduces human fatigue, leading to missed talent or biased screening decisions.

### 1.2 Inefficiencies of Existing Automated Solutions
To address this, Applicant Tracking Systems (ATS) have introduced automated keyword matching. However, these systems suffer from key limitations:
1.  **Keyword Stuffing**: Candidates exploit simple keyword-matching systems by pasting lists of technologies into their resumes (often in white font) to inflate relevance scores.
2.  **Lack of Semantic Context**: If a JD asks for "React" and a candidate's resume lists "Next.js" or "ReactJS" (aliases/implications), simple keyword matchers fail to bridge the semantic gap, rejecting qualified candidates.
3.  **Cross-Domain Pollution (False Positives)**: Basic search-index platforms rank candidates from unrelated fields highly because of generic terms (e.g., a nurse who lists "managed data quality and project compliance" getting matched to a database administrator role).
4.  **Lack of Explainability**: Modern Large Language Model (LLM) or Named Entity Recognition (NER) screeners are black boxes. They provide score values without explaining *why* a candidate was ranked first or *why* another was disqualified, creating legal and compliance risks for hiring managers.

### 1.3 Expected Business Impact
By deploying a deterministic, layout-aware pipeline, the business benefits from:
*   **Time-to-Screen Reduction**: From hours/days down to seconds for an entire applicant pool.
*   **Cost Efficiency**: Eliminating expensive GPU/LLM API calls.
*   **Explainable Matching**: Providing recruiters with a clear breakdown (matched/missing skills, experience metrics, knockout reasons, and anomaly flags).
*   **Quality of Hire**: Surfacing candidates who meet all must-have qualifications and possess domain-relevant experience.

---

## 2. Data Collection & Preprocessing

The system processes unstructured PDF documents and converts them into structured JSON schemas.

### 2.1 PDF Extraction Pipeline (PDFPipelineV3)
The extraction pipeline uses a **Dual-Path Arbitration** mechanism called *"Run Both, Score Both, Pick Best"* to handle different formatting styles (single-column vs. multi-column layouts):

```
                       [PDF Upload]
                            │
                      ┌─────┴─────┐
                      ▼           ▼
                  [Path A]    [Path B]
                 Assembler  Standalone
                  Parsers    Parsers
                      │           │
                      └─────┬─────┘
                            ▼
                    [Arbitrator] ──► (Heuristic Scoring)
                            │
                            ▼
                    [Best Candidate Profile]
                            │
                            ▼
                    [Tag Stripping & Clean]
```

### 2.2 Extraction Stages

#### Stage 1: Layout-Aware PDF Text Parsing
We use `PyMuPDF` (`fitz`) to extract text blocks along with their spatial coordinates `(x0, y0, x1, y1)`. This allows the pipeline to:
*   Identify multi-column documents and read them in natural reading order (left column, then right column) instead of parsing straight across the page.
*   Clean font encoding artifacts such as `(cid:XX)` glyphs.

#### Stage 2: Block Detection & Merging
The `BlockDetector` parses text lines and groups them into logical paragraphs. It removes headers, footers, page numbers, and formatting noise, normalising bulleted list structures.

#### Stage 3: Section Boundary Identification
The `SectionDetector` identifies section boundaries (e.g., Experience, Education, Skills) using font-size heuristics, alignment, and a regex registry (`SectionRegistry.SECTION_ALIASES`) containing **200+ raw headers** mapping to **11 canonical sections**:
*   *Canonical Sections:* `personal_info`, `summary`, `skills`, `experience`, `education`, `projects`, `certifications`, `languages`, `interests`, `awards`, `publications`.

#### Stage 4: Dual-Path Parsing & Arbitration
*   **Path A (Assembler-Based)**: Parses content within tagged section blocks (`[EXPERIENCE]...[/EXPERIENCE]`).
*   **Path B (Standalone Parsers)**: Scans the entire raw document text using pattern matchers for fields like name, email, phone, location, and LinkedIn.
*   **Arbitration**: For structured fields (like `experience` and `education`), the system scores both paths based on count, completeness (e.g., role, company, and dates present), and date parsability, then selects the higher-scoring path.

#### Stage 5: Normalization and Cleaning
The selected path undergoes post-extraction cleaning:
*   **Tag Stripping**: Removes all custom block tags (`[TAG]...[/TAG]`) recursively from nested lists and strings.
*   **Deduplication**: Merges duplicate experience entries (comparing role, company, and date ranges).
*   **Quality Scoring**: The `quality_scoring` module evaluates the output across three dimensions:
    1.  `compute_quality()`: Checks structured field completeness.
    2.  `compute_text_quality()`: Detects text corruption (ratio of alphabetic characters, average word length, and garbled character runs).
    3.  `compute_semantic_quality()`: Assesses linguistic validity (vowel/consonant distribution and case switches).

---

## 3. Model Development

### 3.1 Skill Registry & Graph-Based Inference
To address semantic gaps, we modeled a **Skill Inference Graph** stored in `skill_graph.json` containing **200+ nodes**. This graph defines three edge types:
1.  `aliases`: Canonical groupings of equivalent terms (e.g., "ReactJS", "React.js", "React" -> `reactjs`).
2.  `implies` (Forward/Reverse): Hierarchical knowledge representation indicating that proficiency in A implies knowledge of B (e.g., `nextjs` implies `reactjs`, `django` implies `python`).
3.  `related` (Bidirectional): Sideways associations in the same technology family (e.g., `angular` is related to `vuejs`).

When matching candidate skills against the JD, the engine calculates a **relevance weight** based on the relationship path:

| Match Type | Score Weight | Explanation / Example |
| :--- | :--- | :--- |
| **Explicit** | `1.00` | Direct string match (e.g., Candidate: "Python", JD: "Python") |
| **Alias** | `1.00` | Canonical match (e.g., Candidate: "ReactJS", JD: "React") |
| **Inferred** | `0.75` | Graph implication path (e.g., Candidate has "Next.js", which implies JD's "React") |
| **Related** | `0.50` | Tech family proximity (e.g., Candidate has "Angular", JD wants "React") |
| **Missing** | `0.00` | No semantic path found in graph or text |

### 3.2 Professional Domain Classification
To prevent false-positive matches (cross-domain pollution), we built a **weighted keyword-voting classifier** supporting **13 domains** and **10 engineering subdomains**:

```
                       [Candidate / JD text]
                                 │
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
           [Experience]      [Projects]      [Skills List]
            (weight 3.0     (weight 2.0)     (weight 1.0)
             for title)
                 │               │               │
                 └───────────────┼───────────────┘
                                 ▼
                    [Weighted Voting Tallies]
                                 │
                                 ▼
                     [Primary Domain Assigned]
                                 │
                   (If Engineering) ──► [Subdomain voting]
```

*   **Supported Domains:** `engineering`, `healthcare`, `hr`, `marketing`, `finance`, `accounting`, `legal`, `education`, `hospitality`, `construction`, `admin`, `sales`, `unknown`.
*   **Engineering Subdomains:** `software`, `civil`, `mechanical`, `electrical`, `data`, `ml`, `frontend`, `backend`, `devops`, `embedded`.

#### Proximity & Penalty Matrix (`domain_proximity.json`)
We defined a penalty matrix that quantifies the mismatch between a job description domain and a candidate domain:
*   Engineering JD vs. Healthcare Candidate: `-80` penalty.
*   Engineering JD vs. Legal Candidate: `-80` penalty.
*   Engineering JD vs. Construction Candidate: `0` penalty (marked as related).
*   Subdomain (e.g., Software Engineering JD vs. Civil Engineering Candidate): `-30` penalty.

---

## 4. Technical Implementation (From Scratch)

The system is implemented in Python and TypeScript, with no external ML dependencies (no PyTorch, TensorFlow, or transformers).

### 4.1 System Structure & Flow
*   `backend/src/core/pipeline.py`: Orchestrates layout parsing, section splitting, and entity extraction.
*   `backend/src/ranking/scorer.py`: Coordinates the three-phase scoring and ranking engine.
*   `backend/src/ranking/bm25_scorer.py`: Custom implementation of the BM25 probabilistic matching algorithm.
*   `backend/src/ranking/similarity.py`: Calculates experience years, cosine similarities of roles, and degree matching.
*   `backend/src/ranking/skill_inference.py`: Implements DFS/reverse-indexing traversals over the skill graph.

### 4.2 Candidate Scorer: 3-Phase Ranking Engine

```
 [JD Input] + [Candidates Pool]
              │
              ▼
   ┌─────────────────────┐
   │ Phase 1: Knockouts  │ ──► (Must-haves, Min years, Degrees)
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │ Phase 2: Scoring    │ ──► (BM25 Skills, Exp Sim, Keywords, Edu)
   └──────────┬──────────┘
              ▼
   ┌─────────────────────┐
   │ Phase 3: Rank & Expl│ ──► (Percentiles, Anomalies, Breakdowns)
   └─────────────────────┘
```

#### Phase 1: Hard Knockout Filtering
Disqualifies candidates who fail to meet core requirements:
1.  **Must-Have Skills**: Checks the candidate's skills list and text sections for required skills (accepting inferred matches with weight $\ge 0.75$).
2.  **Minimum Experience Years**: Computes total experience using parsed date ranges. Applied with a safety buffer (only knocks out if parsed years $< 50\%$ of the minimum and text analysis does not suggest high seniority).
3.  **Maximum Experience Years**: Disqualifies overqualified candidates (e.g., senior applicants for an entry-level position).
4.  **Required Degree Level**: Verifies degree requirements using a 0–5 numeric scale:
    $$\text{PhD (5)} > \text{Master (4)} > \text{Bachelor (3)} > \text{Associate (2)} > \text{High School (1)} > \text{None (0)}$$

#### Phase 2: Multi-Signal Scoring Formulas

##### A. BM25 Skill Score ($S_{\text{skills}}$)
Treats the candidate's skill list as a document and the JD's required skills as a search query. The Inverse Document Frequency (IDF) of a skill $q$ is computed dynamically across the current applicant pool:

$$\text{IDF}(q) = \ln \left( \frac{N - n(q) + 0.5}{n(q) + 0.5} + 1 \right)$$

Where:
*   $N$ is the total number of candidates in the pool.
*   $n(q)$ is the number of candidates who possess skill $q$.

The BM25 score for skill $q$ on a candidate $d$ is:

$$\text{BM25}(q, d) = \text{IDF}(q) \times \frac{\text{tf}(q, d) \times (k_1 + 1)}{\text{tf}(q, d) + k_1 \times \left(1 - b + b \times \frac{|d|}{\text{avgdl}}\right)}$$

Where:
*   $\text{tf}(q, d)$ is the inference weight of skill $q$ in candidate $d$ ($1.0$, $0.75$, $0.50$, or $0.0$).
*   $k_1 = 1.5$ (term frequency saturation control).
*   $b = 0.75$ (document length normalisation control).
*   $|d|$ is the count of skills on candidate $d$.
*   $\text{avgdl}}$ is the average count of skills across all candidates.

The raw skill score is normalized against the maximum possible score:

$$S_{\text{skills}} = \left( \frac{\sum_{q \in Q} \text{BM25}(q, d)}{\sum_{q \in Q} \text{BM25}_{\text{max}}(q, d)} \right) \times 100$$

*Domain Penalty Application:* If a domain mismatch is detected, the skill score is adjusted:
$$S_{\text{skills, adjusted}} = \max\left(0, S_{\text{skills}} \times \left(1 + \frac{\text{Penalty}}{100}\right)\right)$$

##### B. Experience Score ($S_{\text{exp}}$)
Formulated from three weighted sub-signals:
1.  **Title Similarity (40%)**: Cosine similarity between the TF-IDF vectors of candidate job titles and the target JD title:
    $$\text{Title Score} = \min(1.0, \text{CosineSim}(\vec{T}_{\text{cand}}, \vec{T}_{\text{jd}}) \times 1.5) \times 100$$
2.  **Years in Range (40%)**:
    $$\text{Years Score} = \begin{cases} 100 & \text{if } \text{Min} \le \text{Years} \le \text{Max} \\ \max\left(0, \frac{\text{Years}}{\text{Min}} \times 80\right) & \text{if } \text{Years} < \text{Min} \\ 80 & \text{if } \text{Years} > \text{Max} \end{cases}$$
3.  **Recency (20%)**: Evaluates time since last active employment:
    $$\text{Recency Score} = \begin{cases} 100 & \text{if current or } \le 0.5 \text{ years ago} \\ 85 & \text{if } \le 2.0 \text{ years ago} \\ 60 & \text{if } \le 5.0 \text{ years ago} \\ 30 & \text{if } > 5.0 \text{ years ago} \end{cases}$$

$$S_{\text{exp}} = 0.40 \times \text{Title Score} + 0.40 \times \text{Years Score} + 0.20 \times \text{Recency Score}$$

##### C. Keyword Score ($S_{\text{keyword}}$)
Measures occurrences of key terms in the resume text:
$$S_{\text{keyword}} = \frac{\text{Matched Keywords}}{\text{Total Keywords}} \times 100$$

##### D. Education Score ($S_{\text{edu}}$)
Combines degree levels and field of study:
1.  **Degree Match (60%)**:
    $$\text{Degree Match} = \begin{cases} 100 & \text{if best\_level } \ge \text{ required\_level} \\ 60 & \text{if best\_level } = \text{ required\_level } - 1 \\ 30 & \text{if best\_level } > 0 \\ 0 & \text{otherwise} \end{cases}$$
2.  **Field Similarity (40%)**: Cosine similarity between candidate degree descriptions and the JD's preferred field:
    $$\text{Field Score} = \min(100, \text{CosineSim}(\vec{F}_{\text{cand}}, \vec{F}_{\text{jd}}) \times 130)$$

$$S_{\text{edu}} = 0.60 \times \text{Degree Match} + 0.40 \times \text{Field Score}$$

##### E. Scoring Adjustments & Bonuses
Three independent bonuses are added to the weighted score:
1.  **Project-Skill Match Bonus** ($B_{\text{proj}}$, 0–5 points): Awarded based on the overlap between project technologies and JD requirements.
2.  **Prestige Bonus** ($B_{\text{prestige}}$, 0–4 points): $+2.0$ points per recognised employer (e.g., FAANG, top-tier consulting firms).
3.  **Certification Bonus** ($B_{\text{cert}}$, 0–5 points): $+0.25$ points for elite certifications, $+0.15$ for standard certifications, and $+1.0$ for hackathon wins.

##### F. Final Weighted Score
The final candidate score is computed using the following weights:
*   $\text{Skills}(w_s) = 0.40$, $\text{Experience}(w_e) = 0.25$, $\text{Keywords}(w_k) = 0.20$, $\text{Education}(w_d) = 0.15$.

$$\text{Final Score} = \min\left(100.0, w_s S_{\text{skills, adj}} + w_e S_{\text{exp}} + w_k S_{\text{keyword}} + w_d S_{\text{edu}} + B_{\text{proj}} + B_{\text{prestige}} + B_{\text{cert}}\right)$$

*Keyword Weight Redistribution:* If a JD has no keywords, its weight ($w_k = 0.20$) is redistributed proportionally among the remaining dimensions:
*   $w_s' = \frac{0.40}{0.80} = 0.50$, $w_e' = \frac{0.25}{0.80} = 0.3125$, $w_d' = \frac{0.15}{0.80} = 0.1875$.

#### Phase 3: Rank, Percentiles, and Anomaly Detection
The final step calculates percentiles relative to the highest-scoring candidate:

$$\text{Percentile} = \frac{\text{Score}}{\text{Max Active Score}} \times 100$$

It also flags anomalies:
*   `FRESHER`: No experience entries found.
*   `OVERQUALIFIED`: Experience exceeds maximum requirements by $1.5\times$ or more.
*   `GAP`: Employment gaps of more than 6 months.
*   `LOW_QUALITY`: Extraction quality score below 0.5.

---

## 5. Training & Evaluation

Because the system is deterministic, "training" refers to the iterative refinement of the keyword dictionaries, skill implication weights, and domain boundary thresholds against a ground-truth dataset.

### 5.1 Benchmarking Metrics
We measure system performance using information retrieval metrics:
*   **Precision @ K (P@K)**: The proportion of relevant candidates in the top $K$ results.
*   **Mean Reciprocal Rank (MRR)**: Evaluates how high the first relevant candidate is ranked:
    $$\text{MRR} = \frac{1}{|Q|} \sum_{i=1}^{|Q|} \frac{1}{\text{rank}_i}$$
*   **Normalized Discounted Cumulative Gain (NDCG)**: Measures ranking quality based on graded relevance:
    $$\text{DCG}_p = \sum_{i=1}^p \frac{rel_i}{\log_2(i + 1)}, \quad \text{NDCG}_p = \frac{\text{DCG}_p}{\text{IDCG}_p}$$
*   **False Positive (FP) Rate**: The percentage of candidates from unrelated domains mistakenly placed in the top results.

### 5.2 Benchmark Datasets
We maintain two benchmark configurations to evaluate modifications:
1.  **V3 Benchmark (Superseded)**: ~100 PDFs, 5 Job Descriptions. Used for initial proof of concept.
2.  **V4 Benchmark (Active Production)**: **3,856 PDF resumes** matched against **20 Job Descriptions** representing 13 industries.

---

## 6. Testing & Validation

### 6.1 Systematic Benchmark Progress (v6 to v9)
We evaluated the pipeline across successive versions using the V4 benchmark:

*   **V6 Baseline**: Achieved an overall score of `65/100`. The primary issue was high cross-domain pollution. Healthcare keywords like "compliance", "monitoring", and "sourcing" triggered false matches for engineering and legal profiles, leading to a high false-positive rate.
*   **V8 Refinements**: Raised the overall score to `78/100` by adding the domain pre-filter, which skips candidates with severe domain mismatches (penalty $\le -60$).
*   **V9 Production Release (Current)**: Achieved a score of `86/100` through the following changes:
    *   Removed generic terms ("monitoring", "compliance", "research") from the healthcare dictionary.
    *   Added 30+ domain-specific civil, mechanical, and electrical engineering terms to prevent engineers from being misclassified.
    *   Lowered weights for generic cross-domain terms.

#### V9 Quality Metrics Dashboard

| Metric | Score / Value | Status |
| :--- | :--- | :--- |
| **Overall Score** | `86/100` | 🔵 **PRODUCTION READY** |
| **Domain Classification Accuracy** | **97.8%** | Passed |
| **True False Positive Rate** | **1.5%** (only 3 edge cases in 3,856 candidates) | Passed |
| **Knockout Reliability** | **100/100** | Passed |
| **Ranking Quality** | **86/100** | Passed |
| **Extraction Quality** | **72/100** | Passed |

### 6.2 Regression Testing & Guardrails
We established domain classification guardrails in `tests/test_domain_guardrails.py`. These tests run on every pull request to protect dictionary logic:
1.  `test_civil_engineer_not_healthcare`: Assures civil engineers with AutoCAD + STAAD terms are not classified as healthcare.
2.  `test_nurse_must_be_healthcare`: Verifies that a nurse with ICU + GNM credentials maps to healthcare.
3.  `test_procurement_engineer_not_legal`: Confirms that contract-negotiation terms on engineering resumes do not trigger a legal classification.

---

## 7. Deployment

The system uses a decoupled, serverless deployment pattern that is cost-effective and scalable:

```
[Client App] ──► [AWS API Gateway] ──► [FastAPI Lambda (ECR Container)]
                                               │
                                       ┌───────┴───────┐
                                       ▼               ▼
                                  [AWS S3]      [AWS DynamoDB]
                               (Resume PDFs)    (Jobs & Scores)
```

### 7.1 Serverless Cloud Infrastructure
*   **AWS Lambda**: Runs the FastAPI backend server as a containerised function. The container image is stored in **AWS ECR**. This provides automatic scaling and zero-idle cost.
*   **AWS API Gateway**: Exposes API endpoints and handles CORS, rate limiting, and SSE connections.
*   **Amazon S3**: Stores uploaded resume PDFs.
*   **Amazon DynamoDB**: Stores job requirements, candidate profiles, and scoring metrics. This database is key-value based and scales to handle high traffic.

### 7.2 Docker Compose local deployment
The local container setup in `docker-compose.yml` runs the complete stack on a local machine:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - ENV=development
      - DATA_DIR=/app/data
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - VITE_API_URL=http://localhost:8000
    depends_on:
      - backend
```

---

## 8. Final Insights & Future Work

### 8.1 Key Engineering Insights
1.  **Rules vs. ML Trade-offs**: While transformer-based models are effective for parsing unstructured text, they require expensive hardware (GPUs) and can introduce hallucinations. This deterministic layout and graph approach parses resumes at a fraction of the cost, runs on standard CPU servers, and is fully explainable.
2.  **Clean Data is Key**: Preprocessing (including dual-path arbitration, layout-aware reading order, and tag stripping) proved more critical to accuracy than the scoring formulas themselves. Accurate scoring depends on clean extraction.
3.  **Explainability Builds Trust**: Recruiter testing showed that providing detailed explanations for candidate rankings (e.g., showing which skills matched or explaining a knockout decision) is key to user adoption.

### 8.2 Future Roadmap
*   **Hybrid Vector Search**: Integrate local vector embeddings (using a lightweight model like `all-MiniLM-L6-v2` running on CPU) to handle semantic queries alongside the BM25 scorer.
*   **Retrieval-Augmented Generation (RAG)**: Use an LLM to generate interview questions and recruiter summary notes based on a candidate's scored profile.
*   **ATS Integrations**: Create plugins to sync candidate profiles with platforms like Workday, Greenhouse, or Lever.
*   **Multilingual Parsing**: Expand the section registry and dictionaries to support multi-language resume processing.
