# benchmark_methodology.md — How "the benchmark passed" is actually verified

## Why this file exists

`tests/benchmark_v4/report.md` and `report.json` currently represent **one run, on one corpus, at one point in time** (3856 PDFs, generated 2026-06-24). That run is real and the numbers in it are internally consistent — but "internally consistent" and "statistically reliable" are different claims. A single run tells you what happened once. It does not tell you what happens on a different random sample of resumes, on a corpus with different noise characteristics, or after the next code change.

You (the project owner) noted you've re-verified correctness "many times" with large sets of random resume PDFs. That's good instinct, but if it isn't written down anywhere, it doesn't exist for the next person (or agent) touching this code. This file is where it goes from now on.

## Rules for any benchmark claim to count as evidence

1. **N ≥ 3 independent runs**, not 3 runs on the same 200 PDFs — at minimum, 3 different random samples drawn from the full resume pool (currently ~3856+ PDFs per `report.json`'s `total_pdfs`), OR 3 runs on the full corpus if sample size ≥ 1000.
2. **Report the spread, not just the mean.** If Extraction Quality composite score is 72.4 on one run, what's the min/max across the 3 runs? A ±0.5 spread is a real number. A ±8 spread means the corpus sampling matters and the single-run number in `report.md` is misleading on its own.
3. **State corpus composition alongside the score.** The existing corpus is heavily engineering/software-skewed (47.5% `engineering` domain per `report.json`'s `domain_distribution`). A benchmark claim of "97.8% domain accuracy" is a claim about THIS corpus's composition, not a general claim about the classifier. If someone asks "does this generalize to a legal-heavy resume set," the honest answer today is: unknown, untested.
4. **Any regression claim ("V6→V7 improved ranking quality by +19") must show the same-corpus-same-seed comparison.** The existing V6→V7 comparison table in `report.md` is good practice — keep doing exactly that, and extend it to Phase 6/7/8 changes below.
5. **Timing/performance claims (Phase 6) require same-machine, same-corpus, cold vs warm state labeled.** "603ms avg/PDF" from the V3 report you pasted is meaningless without knowing if that's a warm Lambda, a local dev box, disk-cached PDFs, etc. Every timing number going forward gets a one-line environment tag: `[local-warm]`, `[lambda-cold]`, `[lambda-warm]`.

## What "passed" means going forward

A phase gate in `phases.md` is marked passed only when:
- The raw per-document output (CSV or JSON, not just the summary table) is attached or linked.
- The run was repeated per rule #1 above, OR the change is a pure refactor with no logic difference (in which case a single run + a diff showing byte-identical `final_score`/`rank` output for a fixed candidate set is sufficient — this is the standard already used in Phase 7's gate above).
- Any score that moved from the previous baseline has an explanation grounded in a document-level diff (which specific PDFs changed and why), not a hypothesis.
- **For extraction accuracy claims specifically (name/email/phone/skills/experience/education presence rates), the ground-truth PDF audit in the section below has been run and its output is attached. A benchmark report that only cites the pipeline's own per-document JSON as evidence is NOT sufficient for extraction-accuracy gates — see rationale below.**

## Ground-truth PDF audit — mandatory for any extraction-accuracy claim

### Why the existing per-document CSV/JSON is not enough on its own

The per-document CSV/JSON (`report.json`'s `name_audit`, `fields`, etc.) is produced by `PDFPipelineV3` describing its own output. If the pipeline fails to find a name and correctly logs `name: null, missing_name_reason: "NO_NAME_FOUND"`, that row is **internally consistent** — the JSON accurately reflects what the pipeline did. But it says nothing about whether the PDF actually *contains* a name the pipeline missed. Checking the pipeline's claims against the pipeline's own log of its claims is not independent verification; it's a pipeline auditing itself. This is the same failure mode already documented in `userMemories` regarding coding agents fabricating summary tables — except here the risk isn't fabrication, it's silent, self-consistent blindness to a whole failure class (e.g. a name-extraction regex that never matches names formatted as "SURNAME, Firstname").

### The audit procedure

This targets the four specific weaknesses called out from the V3 report: name (74.5%), email (68%), phone (70%), and the n=1 Nova/LLM fallback path.

1. **Draw a random sample of N=50 PDFs** from the full corpus (not the same 200 already used in prior runs — use a fresh random seed, record the seed and the file list).
2. **For each of the 50 PDFs, the agent must open and actually read the raw PDF** (via the `view` tool on a rendered page image, or `pdf-reading` skill / equivalent text extraction independent of `PDFPipelineV3`) and manually record:
   - Does the resume contain a name a human would recognize as the candidate's name? What is it verbatim, and where on the page (header, footer, sidebar, table cell)?
   - Does it contain an email address? Verbatim.
   - Does it contain a phone number? Verbatim.
   - Is the PDF text-based (selectable text) or a scanned image requiring OCR? This distinction matters — a scanned-image PDF failing name extraction is a different problem than a text-based PDF failing it.
3. **Run the same 50 PDFs through the actual pipeline** and record what `PDFPipelineV3` extracted for the same four fields.
4. **Diff the two lists.** For every mismatch, classify it:
   - `TRUE_MISS` — the PDF clearly contains the field (readable by a human) and the pipeline returned null or wrong. This is a real bug.
   - `TRUE_ABSENT` — the PDF genuinely does not contain the field (e.g. no phone number listed at all). The pipeline correctly returned null. Not a bug — but it means the 74.5%/68%/70% numbers include some PDFs that can never reach 100% no matter how good extraction gets, and that ceiling should be reported separately from the extractable-but-missed rate.
   - `SCANNED_UNREADABLE` — PDF is a scanned image with no OCR layer; extraction failure here is an OCR-pipeline problem, not a regex/parsing problem, and should not be lumped into the same fix bucket.
5. **Report all four counts** (TRUE_MISS, TRUE_ABSENT, SCANNED_UNREADABLE, and matches) per field, not just a single "accuracy %." The current 74.5% name rate conflates all of these into one number and that's exactly the imprecision this audit exists to remove.

### Nova/LLM fallback path — separate, stricter audit

Because the existing evidence is n=1 (one fallback trigger out of 200 PDFs, scoring 28.6%), this path gets its own audit requirement before anyone can claim it "works":

1. Identify or construct at least 15 PDFs that are expected to trigger the Nova fallback (i.e., PDFs where the deterministic PyMuPDF/ODL stages would leave `UnresolvedChunk`s — garbled text, unusual layouts, non-standard section headers, or the adversarial/malformed PDFs noted as a current gap above).
2. Run each through the pipeline, confirm the fallback actually triggered (check `extraction_strategy` / domain_signals in the metadata, don't assume from the score alone).
3. For each, apply the same ground-truth read-the-PDF audit as above.
4. Report the Nova fallback's own accuracy on this adversarial set separately from the main corpus number. A "92% success rate" that includes only 1 Nova-fallback document is not a claim about Nova's accuracy — it's a claim about the deterministic path's accuracy, which is a different thing.

### Who does this and how often

- Required once before any Phase 6/7/8 gate that touches extraction paths is marked passed (Phase 6 is concurrency-only and instrumentation-only per `phases.md`, so it does NOT require this audit — Phase 7's ATS scoring reuses existing `DocumentStructure`/quality signals rather than adding new extraction, so it also does not require a fresh audit, but should cite the most recent one).
- Required again any time a parser file under `src/extractors/` or `src/core/pipeline.py` changes, regardless of which phase that change nominally belongs to.
- The 50-PDF sample size is a floor, not a target — if time allows, larger samples reduce the chance the audit itself got unlucky on a non-representative draw. Report sample size explicitly either way.

## Known current gaps (as of this doc's creation)

- The 3856-PDF benchmark run in `tests/benchmark_v4/report.json` is a single run. Nothing in the repo currently re-runs it on a different sample to check variance. **Action item, not yet done:** before trusting the 86/100 "PRODUCTION READY" verdict for anything beyond directional guidance, run it 2 more times on different 1000-PDF random subsamples and record the spread here.
- Nova/LLM fallback path (`extraction_strategy` / Bedrock Nova Micro/Lite per `userMemories`) has essentially n=1 real-world validation from the pasted V3 report (1 fallback triggered out of 200). This path is functionally unverified at any real sample size. Do not treat "it worked once" as "it works." **See "Ground-truth PDF audit" section above — Phase 9 in `phases.md` is the gated milestone that closes this gap.**
- No adversarial corpus exists yet (deliberately malformed PDFs, password-protected, scanned-image-only, non-English). All current benchmark numbers are on a corpus of real-but-unfiltered resumes, which is a different thing from a stress-test corpus.
- **Name/email/phone extraction rates (74.5% / 68% / 70% in the pasted V3 report) have never been checked against actual PDF content by a human or an independent reader — only against the pipeline's own self-reported log.** This is the single biggest unverified assumption in the current benchmark story and is the primary reason Phase 9 exists.