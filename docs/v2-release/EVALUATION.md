# Evaluation & Benchmark Specification (v2 Release)

## Important Notice
> [!WARNING]
> Previous claims of 97.8% domain accuracy and 86/100 production readiness are UNVALIDATED and must not be cited as proven metrics. Any unsupported metrics must be marked as UNVALIDATED.

## 1. Gold-Set Format
All evaluations must run against a versioned gold-set. This dataset consists of human-reviewed ground truth data.

- **Format:** JSON lines (`.jsonl`), versioned via git tags (e.g., `gold-set-v2.1`).
- **Fields:** `document_id`, `raw_text`, `expected_extraction` (dict), `expected_score` (float), `human_reviewer_id`, `review_date`.

## 2. Test Categories
We categorize our evaluations to isolate component performance:
- **Extraction:** Accuracy of parsing entities (names, dates, skills, roles).
- **Ranking:** Correlation between system scores and human-reviewed ground truth scores (e.g., NDCG, Kendall's Tau).
- **Latency:** End-to-end processing time per document and batch throughput.
- **Fallback:** System behavior when LLM parsing fails (graceful degradation to regex/heuristic methods).
- **Security:** Prompt injection and adversarial text resilience.
- **Fairness:** Parity in scoring across demographic groups. **Never train or tune against protected attributes.**

## 3. Curated Test Resumes
The evaluation corpus must include a minimum of 25+ curated test resumes covering the following edge cases:
- Standard one-column layouts
- Complex two-column layouts
- Sparse/minimalist resumes
- Malformed/corrupted PDFs
- Scanned documents (OCR required)
- Inconsistent or non-standard date formats
- Missing mandatory fields (e.g., no education history)
- Adversarial text (e.g., hidden white text, prompt injection attempts)

## 4. Benchmark Execution
The benchmark suite is executed via a unified CLI command.

### Command Structure
```bash
python -m benchmark run --gold-set=v2.1 --env=staging --seed=42
```

### Output Requirements
The benchmark command must output a consolidated report containing:
- **Raw per-document results:** JSON/CSV of expected vs actual.
- **Summary metrics:** Aggregate precision, recall, F1, and ranking metrics.
- **Corpus composition:** Breakdown of document types evaluated.
- **Random seed:** For reproducibility.
- **Environment tag:** (e.g., `local`, `staging`, `prod`).
- **Score deltas:** Changes compared to the previous run.

## 5. Regression Tests
Automated regression tests must use fixed input fixtures and assert against expected outputs. This ensures core extraction and scoring logic does not silently drift.

- **Fixtures:** Stored in `tests/fixtures/regression/`.
- **Execution:** Run as part of the standard CI pipeline.
