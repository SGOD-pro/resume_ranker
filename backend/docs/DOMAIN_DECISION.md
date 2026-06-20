# Domain Detector Decision

## Status: KEEP

## Summary

`domain_detector.py` is **actively used** in the extraction pipeline and is NOT dead code.

## Evidence

### Active Usage

- **`pipeline.py` L100**: `DomainDetector` is instantiated as `self.domain_detector`
- **`pipeline.py` L132-151**: `domain_result = self.domain_detector.detect(combined_text)` is called during every extraction
- The domain result determines:
  - `ExtractionResult.domain` (e.g., "resume", "finance", "legal")
  - `ExtractionResult.domain_confidence` (0.0–1.0)
  - Warning generation (domain-specific warnings)

### What It Does

Classifies document type before field extraction by scoring regex pattern matches against weighted domain signals:

| Domain | Signal Count | Example Patterns |
|--------|-------------|-----------------|
| resume | 7 | "work experience", "education", "resume", "linkedin" |
| finance | 6 | "balance sheet", "ebitda", "gaap", "10-k" |
| legal | 5 | "whereas", "plaintiff", "jurisdiction" |
| medical | 5 | "patient", "icd-10", "diagnosis" |
| invoice | 5 | "invoice", "purchase order", "amount due" |
| research | 5 | "abstract", "methodology", "et al." |

### Why It Matters

1. **Safety gate**: Prevents non-resume documents from being processed through the resume extraction pipeline
2. **Metadata**: Provides domain classification and confidence score in the output
3. **Future extensibility**: Will route different document types to different extraction strategies (e.g., invoice → invoice parser)

## Decision

Keep `domain_detector.py` at root level. It is a core pipeline dependency.

## Future Considerations

- May move to `src/core/domain_detector.py` in a future phase
- Could be extended with more granular domain-specific extraction routing
- ML-based classification could replace regex patterns for higher accuracy
