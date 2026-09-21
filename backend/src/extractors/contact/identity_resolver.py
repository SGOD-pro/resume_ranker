"""
identity_resolver.py — Deterministic Candidate Identity Resolution
===================================================================
Replaces naive 'first plausible line' regex scanning with a multi-source,
evidence-weighted identity arbitration engine.

Architecture:
  1. Candidate Generation:
     - Tagged layout: [NAME] tokens from LayoutAwarePDFExtractor
     - Visual headers: Large/bold font lines in top header zone (page 1)
     - ODL structural headings: Heading AST elements physically in top 25% of page 1
     - Contact-adjacent lines: Text immediately preceding/following verified email/phone
     - Text fallback: Top 15 lines of raw text (lowest priority)

  2. Negative Evidence Filtering (Generic Linguistic & Structural Checks):
     - Sentence punctuation (periods, question marks, exclamation points)
     - Gerunds / action verbs ('Enhanced', 'Learning', 'Developing', 'Motivated')
     - Prepositions / relational words in non-particle positions ('towards', 'into', 'possible')
     - Section keywords, job title suffixes/prefixes, company suffixes, tech words
     - Character validity & length boundaries

  3. Positive Evidence Scoring:
     - Header zone geometry (top 20% of page 1)
     - Typography prominence (larger font size relative to body / bold)
     - Contact anchor adjacency (adjacent to email, phone, or LinkedIn)
     - Structural tag confidence
     - Explicit requirement: Must have at least ONE positive identity signal beyond text shape.

  4. Truthful Unresolved State:
     - If no candidate reaches the threshold, returns display_name = None and status = UNRESOLVED.
     - Never fabricates or guesses a candidate identity.
"""

import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class IdentityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PLAUSIBLE = "PLAUSIBLE"
    UNRESOLVED = "UNRESOLVED"
    REJECTED_CANDIDATE = "REJECTED_CANDIDATE"


class IdentitySource(str, Enum):
    TAGGED_LAYOUT = "tagged_layout"
    VISUAL_HEADER = "visual_header"
    TOP_ODL_HEADING = "top_odl_heading"
    CONTACT_ADJACENT = "contact_adjacent"
    TEXT_FALLBACK = "text_fallback"
    LLM_INFILL = "llm_infill"


@dataclass
class CandidateIdentityResult:
    """Strongly typed result representing candidate identity resolution."""
    display_name: Optional[str]
    normalized_name: Optional[str]
    confidence: float
    status: IdentityStatus
    source: IdentitySource
    page: Optional[int] = 1
    bounding_box: Optional[Dict[str, float]] = None  # {x0, y0, x1, y1}
    evidence_text: str = ""
    candidate_rejections: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["source"] = self.source.value
        return d


@dataclass
class IdentityCandidate:
    raw_text: str
    source: IdentitySource
    page: int = 1
    bounding_box: Optional[Dict[str, float]] = None
    font_size: float = 0.0
    is_bold: bool = False
    distance_to_contact: Optional[int] = None  # Line distance to email/phone (0 = same line, 1 = adjacent)
    notes: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Negative Evidence Vocabulary & Regexes
# ─────────────────────────────────────────────────────────────────────────────

# Canonical lowercase name particles (allowed in lower case e.g. "Vincent van Gogh", "Omar al-Bashir")
NAME_PARTICLES = {
    'de', 'van', 'von', 'al', 'el', 'la', 'le', 'du', 'da', 'di',
    'bin', 'binti', 'ibn', 'ben', 'mac', 'mc', 'der', 'den', 'ter'
}

# Verbs, participles, and gerunds that signal sentences, actions, or project descriptions
VERB_GERUND_RE = re.compile(
    r'\b(?:'
    r'enhanced|enhancing|engineered|engineering|developed|developing|managed|managing|'
    r'created|creating|led|leading|designed|designing|analyzed|analyzing|achieved|achieving|'
    r'implemented|implementing|delivered|delivering|supported|supporting|automated|automating|'
    r'optimized|optimizing|motivated|learning|insights|sub-space|subspace|performance|'
    r'experienced|results-driven|goal-oriented|demonstrated|seeking|passionate|dedicated|'
    r'utilizing|utilized|spearheaded|spearheading|facilitated|facilitating|coordinated|coordinating|'
    r'formulated|formulating|established|establishing|directed|directing|assisted|assisting'
    r')\b',
    re.IGNORECASE
)

# Relational words, prepositions, or connectives that never begin/end human names
RELATIONAL_WORDS = {
    'towards', 'toward', 'into', 'through', 'between', 'among', 'within',
    'without', 'against', 'upon', 'possible', 'potential', 'various', 'several',
    'including', 'such', 'like', 'via', 'with', 'from', 'about', 'over', 'under',
    'during', 'before', 'after', 'above', 'below', 'underneath', 'across'
}

# Generic words that commonly appear in resume subtitles, objectives, and headers
GENERIC_SUBTITLE_WORDS = {
    'summary', 'overview', 'profile', 'objective', 'curriculum', 'vitae', 'resume',
    'education', 'experience', 'skills', 'projects', 'certifications', 'interests',
    'strengths', 'competencies', 'qualification', 'qualifications', 'background',
    'achievements', 'responsibilities', 'duties', 'references', 'publications',
    'activities', 'honors', 'awards', 'contact', 'details', 'information', 'portfolio'
}

# Job title nouns that indicate a role rather than a personal name
TITLE_INDICATOR_WORDS = {
    'developer', 'engineer', 'manager', 'lead', 'architect', 'consultant',
    'analyst', 'specialist', 'technician', 'officer', 'coordinator', 'supervisor',
    'director', 'head', 'vp', 'executive', 'assistant', 'associate', 'intern',
    'designer', 'instructor', 'teacher', 'professor', 'nurse', 'physician',
    'attorney', 'counsel', 'accountant', 'auditor', 'administrator', 'operator',
    'scientist', 'researcher', 'programmer', 'strategist', 'representative'
}

# Corporate legal entities
COMPANY_SUFFIXES = {
    'inc', 'inc.', 'ltd', 'ltd.', 'llc', 'llc.', 'corp', 'corp.', 'corporation',
    'gmbh', 'co.', 'company', 'services', 'technologies', 'solutions', 'labs',
    'group', 'holdings', 'partners', 'associates', 'university', 'college', 'school',
    'hospital', 'institute', 'foundation'
}

# Noise and non-name patterns
OCR_NOISE_RE = re.compile(
    r'[\xc2\xc3\xc4\xc5][\x80-\xbf]'
    r'|[\u00c2\u00c3\u00e2]'
    r'|\(cid:\d+\)'
    r'|[\ue000-\uf8ff]'
    r'|[\u2022\u25cf\u25a0\u25aa]'
)


TECH_SKILL_WORDS = {
    'python', 'react', 'docker', 'kubernetes', 'java', 'javascript', 'typescript',
    'angular', 'vue', 'node', 'nodejs', 'aws', 'azure', 'gcp', 'sql', 'nosql',
    'mysql', 'postgresql', 'redis', 'mongodb', 'linux', 'unix', 'html', 'css',
    'sass', 'git', 'github', 'ci/cd', 'devops', 'terraform', 'ansible', 'jenkins',
    'django', 'flask', 'fastapi', 'spring', 'springboot', 'graphql', 'rest',
    'c++', 'c#', 'golang', 'rust', 'ruby', 'php', 'swift', 'kotlin', 'scala',
    'hadoop', 'spark', 'kafka', 'elasticsearch', 'pandas', 'numpy', 'pytorch',
    'tensorflow', 'keras', 'tableau', 'powerbi', 'figma', 'jira', 'scrum'
}


class CandidateIdentityResolver:

    """
    Deterministic candidate identity arbitration engine.
    Scores multiple candidate names against layout, typography, contact adjacency,
    and negative linguistic evidence.
    """

    def resolve(
        self,
        tagged_name: Optional[str] = None,
        visual_header_lines: Optional[List[Dict[str, Any]]] = None,
        odl_headings: Optional[List[Dict[str, Any]]] = None,
        adjacent_lines: Optional[List[str]] = None,
        text_lines: Optional[List[str]] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> CandidateIdentityResult:
        """
        Arbitrate candidate identity from all available structural sources.
        """
        candidates: List[IdentityCandidate] = []
        rejections: List[Dict[str, Any]] = []

        # ── 1. Candidate Generation ──────────────────────────────────────────
        # Source A: Explicit layout tag from LayoutAwarePDFExtractor
        if tagged_name and tagged_name.strip():
            candidates.append(IdentityCandidate(
                raw_text=tagged_name.strip(),
                source=IdentitySource.TAGGED_LAYOUT,
                page=1,
                font_size=16.0,
                is_bold=True,
                distance_to_contact=1 if (email or phone) else None,
                notes="Layout tag [NAME]"
            ))

        # Source B: Visual Header Lines (large/bold lines in top header band)
        if visual_header_lines:
            for item in visual_header_lines:
                txt = item.get("text", "").strip()
                if txt:
                    candidates.append(IdentityCandidate(
                        raw_text=txt,
                        source=IdentitySource.VISUAL_HEADER,
                        page=item.get("page", 1),
                        bounding_box=item.get("bounding_box"),
                        font_size=float(item.get("font_size", 12.0)),
                        is_bold=bool(item.get("is_bold", False)),
                        distance_to_contact=item.get("distance_to_contact"),
                        notes="Visual header element"
                    ))

        # Source C: Top ODL Headings (elements in top 25% of page 1)
        if odl_headings:
            for item in odl_headings:
                txt = item.get("text", "").strip()
                if txt:
                    candidates.append(IdentityCandidate(
                        raw_text=txt,
                        source=IdentitySource.TOP_ODL_HEADING,
                        page=item.get("page", 1),
                        bounding_box=item.get("bounding_box"),
                        font_size=float(item.get("font_size", 14.0)),
                        is_bold=True,
                        notes="ODL heading AST"
                    ))

        # Source D: Contact-Adjacent Lines
        if adjacent_lines:
            for idx, txt in enumerate(adjacent_lines[:5]):
                if txt and txt.strip():
                    candidates.append(IdentityCandidate(
                        raw_text=txt.strip(),
                        source=IdentitySource.CONTACT_ADJACENT,
                        page=1,
                        distance_to_contact=idx,
                        notes=f"Line adjacent to contact anchor (offset {idx})"
                    ))

        # Source E: Text Fallback (top 15 lines of raw text)
        if text_lines:
            for idx, txt in enumerate(text_lines[:15]):
                if txt and txt.strip():
                    candidates.append(IdentityCandidate(
                        raw_text=txt.strip(),
                        source=IdentitySource.TEXT_FALLBACK,
                        page=1,
                        distance_to_contact=idx + 2,
                        notes=f"Top-of-document line {idx}"
                    ))

        if not candidates:
            return CandidateIdentityResult(
                display_name=None,
                normalized_name=None,
                confidence=0.0,
                status=IdentityStatus.UNRESOLVED,
                source=IdentitySource.TEXT_FALLBACK,
                evidence_text="",
                candidate_rejections=rejections,
                warnings=["No candidate text available in document header"]
            )

        # ── 2. Candidate Evaluation & Evidence Scoring ───────────────────────
        scored_candidates: List[Tuple[float, str, IdentityCandidate, List[str]]] = []

        seen_cleaned_texts = set()

        for cand in candidates:
            cleaned, clean_err = self._clean_and_validate(cand.raw_text)
            if not cleaned:
                rejections.append({
                    "text": cand.raw_text,
                    "reason": clean_err or "Failed basic syntactic validation",
                    "source": cand.source.value
                })
                continue

            if cleaned.lower() in seen_cleaned_texts:
                continue
            seen_cleaned_texts.add(cleaned.lower())

            # Evaluate negative evidence
            is_valid, neg_reason = self._evaluate_negative_evidence(cleaned)
            if not is_valid:
                rejections.append({
                    "text": cleaned,
                    "reason": neg_reason,
                    "source": cand.source.value
                })
                continue

            # Evaluate positive evidence score
            score, positive_signals, warnings = self._score_positive_evidence(cleaned, cand)

            # Rule 3: Must possess at least ONE positive identity signal beyond basic title case text shape
            if not positive_signals:
                rejections.append({
                    "text": cleaned,
                    "reason": "Text lacks positive identity signals (bare text shape without header prominence or contact adjacency)",
                    "source": cand.source.value
                })
                continue

            scored_candidates.append((score, cleaned, cand, warnings))

        if not scored_candidates:
            return CandidateIdentityResult(
                display_name=None,
                normalized_name=None,
                confidence=0.0,
                status=IdentityStatus.UNRESOLVED,
                source=IdentitySource.TEXT_FALLBACK,
                evidence_text="",
                candidate_rejections=rejections,
                warnings=["No candidate reached verified identity threshold; all candidates rejected"]
            )

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_name, best_cand, best_warnings = scored_candidates[0]

        # Categorize resolution status
        if best_score >= 0.70:
            status = IdentityStatus.VERIFIED
        elif best_score >= 0.50:
            status = IdentityStatus.PLAUSIBLE
        else:
            status = IdentityStatus.UNRESOLVED

        # Rule 6: If candidate does not reach verified or plausible threshold, return display_name = None
        display_name = self._normalize_name(best_name) if status in (IdentityStatus.VERIFIED, IdentityStatus.PLAUSIBLE) else None
        norm_name = display_name


        return CandidateIdentityResult(
            display_name=display_name,
            normalized_name=norm_name,
            confidence=round(best_score, 2),
            status=status,
            source=best_cand.source,
            page=best_cand.page,
            bounding_box=best_cand.bounding_box,
            evidence_text=best_cand.raw_text,
            candidate_rejections=rejections,
            warnings=best_warnings
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Helper Validation & Cleaning
    # ─────────────────────────────────────────────────────────────────────────

    def _clean_and_validate(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """Clean string and verify basic typographical boundaries."""
        if not text:
            return None, "Empty string"

        # Strip structural markup and markdown headers
        s = re.sub(r'\[/?[A-Z_]+\]', '', text).strip()
        s = re.sub(r'^#+\s*', '', s).strip()

        # Handle 'Lastname, Firstname' format
        lf_match = re.match(r'^([A-Z][a-zA-Z\'-]+),\s*([A-Z][a-zA-Z\'-]+)$', s)
        if lf_match:
            return f"{lf_match.group(2)} {lf_match.group(1)}", None

        # Discard trailing titles / subtitles separated by comma, pipe, or dash
        parts = re.split(r'[,|]|\s+-\s+', s)
        candidate = parts[0].strip()

        # Punctuation check: Real candidate names do NOT end with full stops, exclamation marks, or colons
        if candidate.endswith('.') or candidate.endswith('!') or candidate.endswith('?') or candidate.endswith(':'):
            return None, "Ends with sentence or section punctuation (period, colon, or question mark)"

        # Check for invalid internal punctuation (slashes, parentheses, brackets, numbers, emails)
        if re.search(r'[\d@/\\()[\]{}<>=+*_$#%^~`|;]', candidate):
            return None, "Contains digits, symbols, or contact delimiters"

        # Check OCR artifacts
        if OCR_NOISE_RE.search(candidate):
            return None, "Contains OCR noise / encoding corruption"

        # Split words
        words = candidate.split()
        if not (2 <= len(words) <= 4):
            # Allow single word ONLY if in all-caps or verified single-name particle
            if len(words) == 1:
                return None, "Single word is insufficient for candidate identity"
            return None, f"Word count {len(words)} is outside allowable range [2, 4]"

        # Verify character validity and length
        for w in words:
            clean_w = re.sub(r"[.\-']", '', w)
            if not clean_w.isalpha():
                return None, f"Word '{w}' contains non-alphabetical characters"
            if len(clean_w) < 2 and w.lower() not in NAME_PARTICLES:
                return None, f"Word '{w}' is too short"

        return candidate, None

    def _evaluate_negative_evidence(self, name: str) -> Tuple[bool, str]:
        """
        Generic negative evidence checks.
        Evaluates linguistic markers, syntax, verbs, prepositions, titles, and company names.
        """
        words = name.split()
        lower_name = name.lower()

        # 1. Action verbs, gerunds, or descriptive participles
        # Catches: "Insights possible sub-space", "Enhanced Application Performance", "Motivated towards learning"
        if VERB_GERUND_RE.search(name):
            return False, f"Contains verb, gerund, or performance descriptor ('{VERB_GERUND_RE.search(name).group(0)}')"

        # 2. Relational prepositions or connective words
        for w in words:
            if w.lower() in RELATIONAL_WORDS:
                return False, f"Contains relational preposition or non-name connective word '{w}'"

        # 3. Section or subtitle vocabulary
        for w in words:
            if w.lower() in GENERIC_SUBTITLE_WORDS:
                return False, f"Contains section or resume header word '{w}'"

        # 4. Job title indicators
        for w in words:
            clean_w = w.lower().rstrip('s')
            if clean_w in TITLE_INDICATOR_WORDS:
                return False, f"Contains job title indicator '{w}'"

        # 5. Corporate entities
        for w in words:
            if w.lower().rstrip('.') in COMPANY_SUFFIXES:
                return False, f"Contains corporate/institutional suffix '{w}'"

        # 6. Technical skill or technology words
        tech_matches = [w for w in words if w.lower() in TECH_SKILL_WORDS]
        if tech_matches:
            if len(tech_matches) == len(words):
                return False, f"All words are technical skill terms ({', '.join(tech_matches)})"
            if len(tech_matches) >= 2:
                return False, f"Contains multiple technical skill terms ({', '.join(tech_matches)})"


        # 7. Capitalization Quality:
        # Require ALL words to start with an uppercase letter UNLESS they are recognized name particles.
        # This permanently closes the 'Insights possible sub-space' lowercase loophole.
        for idx, w in enumerate(words):
            if w.lower() in NAME_PARTICLES:
                continue
            if not w[0].isupper():
                return False, f"Word '{w}' is not capitalized and is not a recognized name particle"

        return True, ""

    def _score_positive_evidence(
        self,
        name: str,
        cand: IdentityCandidate
    ) -> Tuple[float, List[str], List[str]]:
        """
        Score candidate identity based on structural and typographical signals.
        """
        score = 0.0
        signals = []
        warnings = []
        words = name.split()

        # 1. Structural Source & Tag Prominence
        if cand.source == IdentitySource.TAGGED_LAYOUT:
            score += 0.40
            signals.append("Explicit [NAME] layout tag")
        elif cand.source == IdentitySource.VISUAL_HEADER:
            score += 0.35
            signals.append("Top-of-page visual header element")
        elif cand.source == IdentitySource.TOP_ODL_HEADING:
            score += 0.30
            signals.append("ODL document heading AST")
        elif cand.source == IdentitySource.CONTACT_ADJACENT:
            score += 0.25
            signals.append("Immediately adjacent to verified contact anchor")
        elif cand.source == IdentitySource.TEXT_FALLBACK:
            score += 0.10
            # text fallback alone gets minimal structural weight

        # 2. Typography Prominence
        if cand.font_size >= 16.0:
            score += 0.25
            signals.append(f"Hero font size ({cand.font_size:.1f}pt)")
        elif cand.font_size >= 13.0:
            score += 0.15
            signals.append(f"Header font size ({cand.font_size:.1f}pt)")

        if cand.is_bold:
            score += 0.15
            signals.append("Bold typography weight")

        # 3. Contact Adjacency Proximity
        if cand.distance_to_contact is not None:
            if cand.distance_to_contact == 0:
                score += 0.20
                signals.append("Shares line with contact anchor")
            elif cand.distance_to_contact <= 2:
                score += 0.15
                signals.append(f"Directly adjacent to contact info (line offset {cand.distance_to_contact})")

        # 4. Canonical Name Typography
        if all(w[0].isupper() for w in words):
            score += 0.10
            signals.append("Clean title-casing across all components")
        elif name.isupper() and len(words) in (2, 3):
            score += 0.10
            signals.append("Standard all-caps header styling")

        # 5. Page constraint
        if cand.page != 1:
            score -= 0.50
            warnings.append(f"Candidate appears on page {cand.page} (expected page 1)")

        # Cap score at [0.0, 1.0]
        final_score = max(0.0, min(1.0, score))
        return final_score, signals, warnings

    def _normalize_name(self, name: str) -> str:
        """Standardize name capitalization to Title Case preserving particles, hyphens, and apostrophes."""
        words = name.split()
        normalized = []
        for w in words:
            if w.lower() in NAME_PARTICLES:
                normalized.append(w.lower())
            else:
                # Handle sub-segments with hyphens and apostrophes (e.g. O'Connor, Jean-Luc, McDonald)
                parts = re.split(r"([-'])", w)
                norm_parts = [p.capitalize() if p not in ("-", "'") else p for p in parts]
                normalized.append("".join(norm_parts))
        return " ".join(normalized)

