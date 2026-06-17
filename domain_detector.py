"""
Domain Detector
Classifies document type before NER so field rules apply correctly.
Supported: resume/cv, finance, legal, medical, invoice, research, general
"""
import re
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass
class DomainResult:
    domain: str          # primary domain
    confidence: float    # 0.0 - 1.0
    signals: list        # which keywords triggered


# Each domain: list of (pattern, weight) tuples
DOMAIN_SIGNALS: Dict[str, list] = {
    "resume": [
        (r'\b(work experience|employment|education|skills|objective|summary|references)\b', 3),
        (r'\b(bachelor|master|phd|mba|degree|university|college|gpa)\b', 3),
        (r'\b(resume|curriculum vitae|cv)\b', 5),
        (r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}\b', 2),
        (r'\b(intern|developer|engineer|analyst|manager|consultant|coordinator)\b', 2),
        (r'\b(linkedin|github|portfolio)\b', 2),
        (r'\b(proficient|experienced|familiar with|knowledge of)\b', 1),
    ],
    "finance": [
        (r'\b(balance sheet|income statement|cash flow|profit|loss|revenue|ebitda)\b', 4),
        (r'\b(assets|liabilities|equity|dividend|earnings per share|eps)\b', 4),
        (r'\b(fiscal year|q1|q2|q3|q4|quarterly|annual report)\b', 3),
        (r'\b(audit|cpa|gaap|ifrs|sox|sec filing|10-k|10-q)\b', 4),
        (r'\b(accounts receivable|accounts payable|depreciation|amortization)\b', 3),
        (r'\$[\d,]+|\b(million|billion|usd|eur|gbp)\b', 2),
    ],
    "legal": [
        (r'\b(whereas|hereinafter|indemnification|jurisdiction|plaintiff|defendant)\b', 4),
        (r'\b(agreement|contract|clause|covenant|warranty|liability|breach)\b', 3),
        (r'\b(party|parties|executed|witness|notary|affidavit|deposition)\b', 3),
        (r'\b(court|attorney|counsel|judge|legal|law firm|statute|regulation)\b', 3),
        (r'\b(section \d+|article \d+|exhibit [a-z])\b', 2),
    ],
    "medical": [
        (r'\b(patient|diagnosis|prescription|physician|treatment|symptoms|clinical)\b', 4),
        (r'\b(icd-?10|cpt code|medication|dosage|mg|ml|pharmacy|hospital|clinic)\b', 4),
        (r'\b(blood pressure|heart rate|bmi|cholesterol|glucose|hemoglobin)\b', 3),
        (r'\b(surgery|procedure|medical history|allergy|referral|discharge)\b', 3),
        (r'\b(nurse|doctor|specialist|pathology|radiology|oncology)\b', 2),
    ],
    "invoice": [
        (r'\b(invoice|bill to|ship to|purchase order|po number)\b', 5),
        (r'\b(subtotal|total due|amount due|tax|vat|gst|discount)\b', 4),
        (r'\b(qty|quantity|unit price|item description|line item)\b', 3),
        (r'\b(payment terms|net 30|net 60|due date|overdue)\b', 3),
        (r'\b(vendor|supplier|buyer|seller|client|customer)\b', 2),
    ],
    "research": [
        (r'\b(abstract|introduction|methodology|results|conclusion|references)\b', 4),
        (r'\b(hypothesis|experiment|dataset|analysis|findings|literature review)\b', 4),
        (r'\b(figure \d+|table \d+|et al\.?|doi:|arxiv|journal|conference)\b', 3),
        (r'\b(statistical|regression|correlation|p-value|sample size|control group)\b', 3),
        (r'\b(published|submitted|peer.review|citation|bibliography)\b', 2),
    ],
}


class DomainDetector:

    def detect(self, text: str) -> DomainResult:
        text_lower = text.lower()
        scores: Dict[str, float] = {}
        all_signals: Dict[str, list] = {}

        for domain, patterns in DOMAIN_SIGNALS.items():
            score = 0.0
            triggered = []
            for pattern, weight in patterns:
                matches = re.findall(pattern, text_lower)
                if matches:
                    score += weight * min(len(matches), 3)  # cap at 3x to avoid keyword stuffing
                    triggered.extend(matches[:2])
            scores[domain] = score
            all_signals[domain] = triggered

        if not scores or max(scores.values()) == 0:
            return DomainResult(domain="general", confidence=0.0, signals=[])

        best_domain = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = scores[best_domain] / total if total > 0 else 0.0

        return DomainResult(
            domain=best_domain,
            confidence=round(confidence, 3),
            signals=all_signals[best_domain]
        )