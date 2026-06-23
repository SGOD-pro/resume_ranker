# 12 — Data Flow Diagrams

## Overview

This document provides visual data flow diagrams for every major subsystem, showing how data transforms as it moves through the pipeline.

---

## 1. End-to-End System Flow

```mermaid
flowchart LR
    subgraph Input
        PDF["Resume PDFs"]
        JD["Job Description\n(form data)"]
    end

    subgraph Backend
        subgraph Extraction
            PIPE["PDFPipelineV3"]
        end

        subgraph Scoring
            SCORER["CandidateScorer"]
        end
    end

    subgraph Output
        RANKED["Ranked\nCandidates"]
    end

    PDF --> PIPE
    PIPE --> |"ExtractionResult\n(fields dict)"| SCORER
    JD --> |"JobDescription"| SCORER
    SCORER --> |"List[ScoredCandidate]"| RANKED
```

---

## 2. PDF Extraction Pipeline (Detailed)

```mermaid
flowchart TD
    PDF["📄 PDF File"]

    subgraph S1["Stage 1: PDF Parsing"]
        FITZ["PyMuPDF (fitz)\npage.get_text('dict')"]
        BLOCKS["Raw Blocks\n{x0, y0, x1, y1, text}"]
        RAWTEXT["Full Raw Text\npage.get_text()"]
    end

    subgraph S2["Stage 2: Layout Analysis"]
        LE["LayoutAwarePDFExtractor"]
        BD["BlockDetector\n• Merge paragraphs\n• Filter headers/footers\n• Detect columns"]
    end

    subgraph S3["Stage 3: Section Detection"]
        SD["SectionDetector\n• Font-size heuristic\n• Header matching\n• Tag generation"]
        SR["SectionRegistry\n200+ header aliases"]
    end

    subgraph S4["Stage 4: Dual Extraction"]
        direction LR
        PA["Path A: Assembler\nResumeAssembler\n→ tagged text parsing"]
        PB["Path B: Standalone\nDirect regex/heuristic\nparsers per field"]
    end

    subgraph S5["Stage 5: Field Extractors"]
        C["Contact\nParser"]
        ED["Education\nParser"]
        EX["Experience\nParser"]
        SK["Skills\nParser"]
        PR["Projects\nParser"]
        CE["Certifications\nParser"]
    end

    subgraph S6["Stage 6: Arbitration"]
        ARB["Score Both Paths\nPick Best Per Field"]
    end

    subgraph S7["Stage 7: Normalization"]
        CLEAN["Tag Stripping\nDedup Experience\nFix Education\nFix Certifications"]
        QUAL["Quality Scoring\n0.0 – 1.0"]
    end

    PDF --> FITZ
    FITZ --> BLOCKS
    FITZ --> RAWTEXT
    BLOCKS --> LE
    LE --> BD
    BD --> SD
    SD --> SR
    SD --> PA
    RAWTEXT --> PB

    PA --> S5
    PB --> S5
    S5 --> ARB
    ARB --> CLEAN
    CLEAN --> QUAL
    QUAL --> ER["ExtractionResult"]
```

---

## 3. Scoring Pipeline Data Flow

```mermaid
flowchart TD
    subgraph Inputs
        CAND["Candidate Fields\n(extracted dict)"]
        JD["JobDescription\n(from frontend)"]
    end

    subgraph PreProcess["Pre-Processing"]
        DC["DomainClassifier\nclassify JD + each candidate"]
        FILT["Domain Pre-Filter\n(skip penalty ≤ -60)"]
        IDF["BM25 IDF\npre-computation"]
    end

    subgraph Phase1["Phase 1: Knockout"]
        KO_SKILL["Must-have skills?\n(inference-aware)"]
        KO_YEARS["Min/max years?"]
        KO_DEGREE["Required degree?"]
    end

    subgraph Phase2["Phase 2: Multi-Signal"]
        direction LR
        BM25["BM25 Skill\nScore (0-100)"]
        EXP["Experience\nScore (0-100)"]
        KW["Keyword\nScore (0-100)"]
        EDU["Education\nScore (0-100)"]
    end

    subgraph Bonuses
        direction LR
        PROJ["Project-Skill\nBonus (0-5)"]
        PREST["Prestige\nBonus (0-4)"]
        CERT["Cert/Hack\nBonus (0-5)"]
    end

    subgraph Phase3["Phase 3: Rank & Explain"]
        WEIGHT["Weighted Sum\n+ Bonuses"]
        SORT["Sort + Rank"]
        PCT["Percentiles"]
        ANOM["Anomaly Flags"]
    end

    CAND --> DC
    JD --> DC
    DC --> FILT
    FILT --> IDF

    IDF --> KO_SKILL
    KO_SKILL --> KO_YEARS
    KO_YEARS --> KO_DEGREE

    KO_DEGREE --> BM25
    KO_DEGREE --> EXP
    KO_DEGREE --> KW
    KO_DEGREE --> EDU

    KO_DEGREE --> PROJ
    KO_DEGREE --> PREST
    KO_DEGREE --> CERT

    BM25 --> WEIGHT
    EXP --> WEIGHT
    KW --> WEIGHT
    EDU --> WEIGHT
    PROJ --> WEIGHT
    PREST --> WEIGHT
    CERT --> WEIGHT

    WEIGHT --> SORT
    SORT --> PCT
    PCT --> ANOM
    ANOM --> SC["ScoredCandidate"]
```

---

## 4. Skill Inference Flow

```mermaid
flowchart TD
    CS["Candidate Skills\n['Next.js', 'TypeScript']"]
    JS["JD Skills\n['React', 'Node.js', 'Python']"]

    subgraph Resolve["Resolve to Graph Keys"]
        CS --> CSK["Candidate Keys\nnextjs, typescript"]
        JS --> JSK["JD Keys\nreactjs, nodejs, python"]
    end

    subgraph Match["Match Each JD Skill"]
        JSK --> M1{"1. Explicit?\nDirect alias match"}
        M1 -->|No| M2{"2. Graph Alias?\nSame graph key"}
        M2 -->|No| M3{"3. Inference?\nCandidate implies JD"}
        M3 -->|No| M4{"4. Related?\nShared edge"}
        M4 -->|No| MISS["Missing\nweight = 0.0"]

        M1 -->|Yes| W1["weight = 1.00"]
        M2 -->|Yes| W2["weight = 1.00"]
        M3 -->|Yes| W3["weight = 0.75"]
        M4 -->|Yes| W4["weight = 0.50"]
    end

    W1 --> IR["InferenceResult\nskill_weights dict"]
    W2 --> IR
    W3 --> IR
    W4 --> IR
    MISS --> IR
```

---

## 5. Frontend-Backend Communication

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend

    Note over FE,BE: Phase 1: Job Setup
    FE->>BE: POST /jobs {title, skills, ...}
    BE-->>FE: {id: "uuid-1"}

    Note over FE,BE: Phase 2: Upload
    FE->>BE: POST /jobs/uuid-1/resumes [files]
    BE-->>FE: {accepted: [...], rejected: [...]}

    Note over FE,BE: Phase 3: Sync Config
    FE->>BE: PATCH /jobs/uuid-1 {latest JD form}
    BE-->>FE: {status: "updated"}

    Note over FE,BE: Phase 4: Extraction (SSE)
    FE->>BE: GET /jobs/uuid-1/extract
    loop For each PDF
        BE-->>FE: event: progress {current, total, filename}
    end
    BE-->>FE: event: complete {total, succeeded, failed}

    Note over FE,BE: Phase 5: Scoring
    FE->>BE: POST /jobs/uuid-1/score {weights}
    BE-->>FE: {candidates: [...ScoredCandidate]}
```

---

## 6. State Flow in Frontend

```mermaid
stateDiagram-v2
    [*] --> checking: App loads

    checking --> ready: /health 200 OK
    checking --> waking_up: /health timeout
    waking_up --> ready: /health 200 OK
    waking_up --> unreachable: 5 failures

    state ready {
        [*] --> idle
        idle --> uploading: Click Analyze
        uploading --> extracting: Upload complete
        extracting --> scoring: Extraction complete
        scoring --> complete: Scoring complete
        complete --> idle: New analysis
    }
```
