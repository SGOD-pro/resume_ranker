"""
Layout-Aware PDF Extractor - Final Architecture
=============================================
Handles ALL real-world layout patterns found across CV/resume/finance/legal PDFs:

LAYOUT PATTERNS DETECTED:
  Zone A - FULL WIDTH HEADER BAND (top of page)
    - name: bold + large font (>14pt), centered
    - title: smaller font, same band
  
  Zone B - DUAL COLUMN BODY
    Case 1: Left sidebar always present (x < split)
            Right main content (x >= split)
    Case 2: Both columns have section headers on SAME Y
            → left header + right header, both processed independently
    Case 3: Mixed line - sidebar label (bold small) shares y with main content
            → split by x coordinate, NOT by content

  Zone C - SINGLE COLUMN (invoices, legal, research)
    - no persistent left cluster of words
    - full-width paragraphs, tables

FONT ROLES (from real PDF analysis):
  Bold >14pt  → document name/title (full width)
  Bold 8-10pt, ALL_CAPS, short → section headers
  Bold 9-10pt, not ALL_CAPS → job titles / edu degree lines  
  Regular 7-8pt → body text, contact info, locations
  Italic 8pt → profile summaries

LOCATION HANDLING (key insight):
  "Master of Science in Dietary Education, Golden Valley  [Regular 7.5pt] Golden Valley"
   ← bold 9.5pt ─────────────────────────────────────── → ← Regular 7.5pt (location) →
  Location is SMALLER font on SAME LINE at far right.
  Detected by font-size drop on same line.
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
import pdfplumber


# ─────────────────────────────────────────────────────────────
# Word token with full metadata
# ─────────────────────────────────────────────────────────────

@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    fontname: str = ""
    size: float = 0.0

    @property
    def is_bold(self):
        return "Bold" in self.fontname or "bold" in self.fontname

    @property
    def is_italic(self):
        return "Italic" in self.fontname or "italic" in self.fontname

    @property
    def is_regular(self):
        return not self.is_bold and not self.is_italic


# ─────────────────────────────────────────────────────────────
# Classified line — what role does this line play?
# ─────────────────────────────────────────────────────────────

@dataclass
class ClassifiedLine:
    """A line of text with its layout role assigned."""
    text: str           # cleaned text
    role: str           # see ROLES below
    column: str         # "left" | "right" | "full"
    top: float          # y position
    x0: float           # leftmost x
    font_size: float    # average font size
    inline_location: Optional[str] = None  # extracted trailing location/city


# Roles - what a line IS in the document structure
ROLE_DOC_NAME       = "doc_name"        # "JULIE MONROE" - large bold
ROLE_DOC_TITLE      = "doc_title"       # "NUTRITION CONSULTANT" - subtitle
ROLE_SECTION_HDR    = "section_header"  # "EMPLOYMENT HISTORY", "EDUCATION"
ROLE_JOB_TITLE      = "job_title"       # "Nutritional Consultant (Part-Time), WIC"
ROLE_EDU_LINE       = "edu_line"        # "Bachelor of Science in Food Sciences, Wisconsin"
ROLE_DATE_RANGE     = "date_range"      # "Jan 2021 — Present"
ROLE_BULLET         = "bullet"          # "• Provided nutrition education..."
ROLE_BODY           = "body"            # regular paragraph text
ROLE_SIDEBAR_HDR    = "sidebar_header"  # "ADDRESS", "SKILLS", "PHONE"
ROLE_SIDEBAR_VALUE  = "sidebar_value"   # "email@email.com", "3868683442"

DATE_RE = re.compile(
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}'
    r'\s*[–—\-]+\s*'
    r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now)',
    re.IGNORECASE
)
DEGREE_RE = re.compile(
    r'\b(Bachelors?|Masters?|Ph\.?D|MBA|M\.?S\.?|B\.?S\.?|B\.?A\.?|M\.?A\.?'
    r'|Associates?|Diploma|Certificate|Doctor)\b', re.IGNORECASE
)
BULLET_CHARS = set('•▪▸►✓✔*-')


# ─────────────────────────────────────────────────────────────
# Core extractor
# ─────────────────────────────────────────────────────────────

class LayoutAwarePDFExtractor:

    def extract(self, pdf_path: str) -> 'DocumentStructure':
        all_classified: List[ClassifiedLine] = []
        all_hyperlinks: List[Dict[str, str]] = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                words = self._get_words(page)
                if not words:
                    continue

                # Extract hyperlinks from PDF annotations
                all_hyperlinks.extend(self._get_hyperlinks(page))

                page_width = float(page.width)
                split_x = self._find_column_split(words, page_width)
                name_y_max = self._find_header_band_bottom(words)

                lines = self._group_lines(words, y_tol=3.5)
                classified = self._classify_lines(
                    lines, split_x, name_y_max, page_width, page_num
                )
                all_classified.extend(classified)

        doc = self._build_document(all_classified)
        doc.hyperlinks = all_hyperlinks
        return doc

    # ─────────────────────────────────────────────────────────
    # Step 1: Get words with metadata
    # ─────────────────────────────────────────────────────────

    def _get_words(self, page) -> List[Word]:
        raw = page.extract_words(
            x_tolerance=3, y_tolerance=3,
            keep_blank_chars=False,
            extra_attrs=["fontname", "size"]
        )
        return [
            Word(
                text=self._clean_cid(w["text"]),
                x0=float(w["x0"]), x1=float(w["x1"]),
                top=float(w["top"]), bottom=float(w["bottom"]),
                fontname=str(w.get("fontname") or ""),
                size=float(w.get("size") or 0),
            )
            for w in (raw or [])
        ]

    @staticmethod
    def _clean_cid(text: str) -> str:
        """Remove (cid:XX) artifacts from PDF text.
        Common patterns: (cid:28)ltering → filtering, speci(cid:28)c → specific"""
        return re.sub(r'\(cid:\d+\)', '', text)

    def _get_hyperlinks(self, page) -> List[Dict[str, str]]:
        """Extract hyperlinks from PDF page annotations."""
        links = []
        try:
            for annot in (page.hyperlinks or []):
                uri = annot.get('uri', '')
                if uri:
                    links.append({'uri': uri})
        except Exception:
            pass
        return links

    # ─────────────────────────────────────────────────────────
    # Step 2: Find column split x-coordinate
    # ─────────────────────────────────────────────────────────

    def _find_column_split(self, words: List[Word], page_width: float) -> Optional[float]:
        """
        Find the gap between sidebar and main column.
        Strategy: scan x-range 10%-75% of page, find longest gap with no word starts.
        """
        # Build set of occupied x positions (word starts only, more reliable than full spans)
        starts = set(int(w.x0) for w in words)

        best_start, best_len = None, 0
        cs, cl = None, 0

        lo, hi = int(page_width * 0.10), int(page_width * 0.75)
        for x in range(lo, hi):
            if x not in starts:
                if cs is None: cs = x
                cl += 1
            else:
                if cl > best_len:
                    best_len, best_start = cl, cs
                cs, cl = None, 0

        # Gap must be at least 20px to count as a real column separator
        if best_len >= 20 and best_start is not None:
            return best_start + best_len / 2
        return None

    # ─────────────────────────────────────────────────────────
    # Step 3: Find where header band ends (name + title zone)
    # ─────────────────────────────────────────────────────────

    def _find_header_band_bottom(self, words: List[Word]) -> float:
        """
        The header band is the top section with name/title.
        It ends where the first section headers appear (bold ALL_CAPS small text).
        Look for first bold ALL_CAPS word below the name.
        """
        large_bold_y = None
        for w in words:
            if w.is_bold and w.size > 14:
                large_bold_y = w.top
                break

        if large_bold_y is None:
            return 0.0

        # Header band = from name down to first section-header-looking line
        # Typically within 120px of the name
        return large_bold_y + 120.0

    # ─────────────────────────────────────────────────────────
    # Step 4: Group words into lines
    # ─────────────────────────────────────────────────────────

    def _group_lines(self, words: List[Word], y_tol: float) -> List[List[Word]]:
        if not words:
            return []

        sorted_w = sorted(words, key=lambda w: (round(w.top / y_tol) * y_tol, w.x0))
        lines, current = [], [sorted_w[0]]
        cy = sorted_w[0].top

        for w in sorted_w[1:]:
            if abs(w.top - cy) <= y_tol:
                current.append(w)
            else:
                lines.append(sorted(current, key=lambda x: x.x0))
                current, cy = [w], w.top
        if current:
            lines.append(sorted(current, key=lambda x: x.x0))

        return lines

    # ─────────────────────────────────────────────────────────
    # Step 5: Classify each line — the core logic
    # ─────────────────────────────────────────────────────────

    def _classify_lines(
        self,
        lines: List[List[Word]],
        split_x: Optional[float],
        header_band_bottom: float,
        page_width: float,
        page_num: int,
    ) -> List[ClassifiedLine]:

        result = []

        for line_words in lines:
            if not line_words:
                continue

            top = line_words[0].top

            if split_x:
                left_words  = [w for w in line_words if w.x0 < split_x]
                right_words = [w for w in line_words if w.x0 >= split_x]
            else:
                left_words  = []
                right_words = line_words

            # ── CASE 1: Line has words in BOTH columns ──────────────────────
            if left_words and right_words and split_x:

                # Sub-case: left = sidebar section header, right = main section header
                # e.g. y=172: left=[DETAILS], right=[PROFILE]
                # e.g. y=280: left=[EMAIL], right=[EMPLOYMENT HISTORY]
                left_is_hdr  = self._is_sidebar_header(left_words)
                right_is_hdr = self._is_main_header(right_words)

                if left_is_hdr:
                    cl = self._make_line(left_words, ROLE_SIDEBAR_HDR, "left")
                    if cl: result.append(cl)
                elif left_words:
                    # Sidebar content (contact values etc)
                    cl = self._make_line(left_words, ROLE_SIDEBAR_VALUE, "left")
                    if cl: result.append(cl)

                if right_is_hdr:
                    cl = self._make_line(right_words, ROLE_SECTION_HDR, "right")
                    if cl: result.append(cl)
                elif right_words:
                    # Main column content shares y with sidebar label
                    cl = self._classify_right_line(right_words, top, header_band_bottom)
                    if cl: result.append(cl)

            # ── CASE 2: Only left column words ──────────────────────────────
            elif left_words and not right_words:
                role = ROLE_SIDEBAR_HDR if self._is_sidebar_header(left_words) else ROLE_SIDEBAR_VALUE
                cl = self._make_line(left_words, role, "left")
                if cl: result.append(cl)

            # ── CASE 3: Only right column (or no split = single column) ─────
            elif right_words:
                # Header band: name / title
                if top <= header_band_bottom and page_num == 0:
                    all_bold = all(w.is_bold for w in right_words)
                    avg_size = self._avg_size(right_words)

                    if avg_size > 14 and all_bold:
                        cl = self._make_line(right_words, ROLE_DOC_NAME, "full")
                    elif avg_size >= 9:
                        cl = self._make_line(right_words, ROLE_DOC_TITLE, "full")
                    else:
                        cl = self._classify_right_line(right_words, top, header_band_bottom)
                    if cl: result.append(cl)
                else:
                    cl = self._classify_right_line(right_words, top, header_band_bottom)
                    if cl: result.append(cl)

        return result

    def _classify_right_line(self, words: List[Word], top: float, hdr_bottom: float) -> Optional['ClassifiedLine']:
        """Classify a line that's in the main (right) column."""
        if not words:
            return None

        text_full = self._join_words(words)
        avg_size = self._avg_size(words)
        all_bold = all(w.is_bold for w in words)
        any_bold = any(w.is_bold for w in words)

        # Section header: bold, ALL CAPS, short, no numbers
        text_stripped = text_full.strip()
        if (all_bold
                and text_stripped.isupper()
                and 1 <= len(text_stripped.split()) <= 4
                and not text_stripped.replace(" ", "").isdigit()
                and len(text_stripped) >= 3):
            return self._make_line(words, ROLE_SECTION_HDR, "right")

        # Date range line
        if DATE_RE.search(text_full):
            return self._make_line(words, ROLE_DATE_RANGE, "right")

        # Bullet line: first word is a bullet char
        if words[0].text.strip() in BULLET_CHARS:
            # Join bullet + content, skipping the bullet char itself
            return self._make_line(words, ROLE_BULLET, "right")

        # Job title line: bold ~9-10pt, not ALL_CAPS
        # May have MIXED fonts: bold for title + regular small for location
        bold_words   = [w for w in words if w.is_bold]
        regular_words = [w for w in words if not w.is_bold]

        if bold_words and avg_size >= 8.5 and not text_stripped.isupper():
            bold_avg = self._avg_size(bold_words)
            if bold_avg >= 9.0:
                # Education line: has degree keyword
                if DEGREE_RE.search(text_full):
                    # Extract inline location (regular small words at far right)
                    inline_loc = self._extract_inline_location(words)
                    cl = self._make_line(words, ROLE_EDU_LINE, "right")
                    if cl: cl.inline_location = inline_loc
                    return cl
                # Job title line
                inline_loc = self._extract_inline_location(words)
                cl = self._make_line(words, ROLE_JOB_TITLE, "right")
                if cl: cl.inline_location = inline_loc
                return cl

        # Default: body text (italic profile, regular description)
        return self._make_line(words, ROLE_BODY, "right")

    # ─────────────────────────────────────────────────────────
    # Step 6: Helpers
    # ─────────────────────────────────────────────────────────

    def _is_sidebar_header(self, words: List[Word]) -> bool:
        text = " ".join(w.text for w in words).strip()
        return (
            all(w.is_bold for w in words)
            and text.isupper()
            and 1 <= len(words) <= 4
            and not text.replace(" ", "").isdigit()
            and len(text) >= 2
        )

    def _is_main_header(self, words: List[Word]) -> bool:
        text = " ".join(w.text for w in words).strip()
        return (
            all(w.is_bold for w in words)
            and text.isupper()
            and 1 <= len(words) <= 5
            and not text.replace(" ", "").isdigit()
            and len(text) >= 3
        )

    def _extract_inline_location(self, words: List[Word]) -> Optional[str]:
        """
        On lines like:
          "Bachelor of Science in Food Sciences, Wisconsin  [bold 9.5]  Madisonville [regular 7.5]"
        Extract the trailing regular-small-font words as the location.
        """
        if not words:
            return None

        # Find the dominant (most common) font size among bold words
        bold_sizes = [w.size for w in words if w.is_bold and w.size]
        if not bold_sizes:
            return None
        dominant_size = max(set(bold_sizes), key=bold_sizes.count)

        # Location words: NOT bold AND significantly smaller than dominant size
        loc_words = [
            w for w in words
            if not w.is_bold and w.size > 0 and w.size < dominant_size - 0.5
        ]

        if loc_words:
            return " ".join(w.text for w in loc_words).strip()
        return None

    def _make_line(self, words: List[Word], role: str, column: str) -> Optional['ClassifiedLine']:
        if not words:
            return None
        text = self._join_words(words)
        if not text.strip():
            return None
        return ClassifiedLine(
            text=text.strip(),
            role=role,
            column=column,
            top=words[0].top,
            x0=words[0].x0,
            font_size=round(self._avg_size(words), 1),
        )

    def _join_words(self, words: List[Word]) -> str:
        if not words:
            return ""
        result = words[0].text
        for i in range(1, len(words)):
            gap = words[i].x0 - words[i-1].x1
            result += (" " if gap > 1 else "") + words[i].text
        return result

    def _avg_size(self, words: List[Word]) -> float:
        sizes = [w.size for w in words if w.size]
        return sum(sizes) / len(sizes) if sizes else 0.0

    # ─────────────────────────────────────────────────────────
    # Step 7: Build DocumentStructure from classified lines
    # ─────────────────────────────────────────────────────────

    def _build_document(self, lines: List[ClassifiedLine]) -> 'DocumentStructure':
        """
        Convert flat classified lines into structured text regions.
        Section headers become [SECTION NAME] tags.
        """
        full_parts    = []  # name + title
        sidebar_parts = []  # left column
        main_parts    = []  # right column

        for line in lines:
            text = line.text

            if line.role == ROLE_DOC_NAME:
                full_parts.append(f"[NAME]{text}[/NAME]")

            elif line.role == ROLE_DOC_TITLE:
                full_parts.append(f"[TITLE]{text}[/TITLE]")

            elif line.column == "left":
                if line.role == ROLE_SIDEBAR_HDR:
                    sidebar_parts.append(f"\n[{text}]\n")
                else:
                    sidebar_parts.append(text)

            else:  # right or full column — main content
                if line.role == ROLE_SECTION_HDR:
                    main_parts.append(f"\n[{text}]\n")

                elif line.role == ROLE_JOB_TITLE:
                    # Strip inline_location from text to avoid duplication
                    clean_text = self._strip_loc_from_text(text, line.inline_location)
                    loc = f"  ||LOC:{line.inline_location}" if line.inline_location else ""
                    main_parts.append(f"[JOB_TITLE]{clean_text}{loc}[/JOB_TITLE]")

                elif line.role == ROLE_EDU_LINE:
                    clean_text = self._strip_loc_from_text(text, line.inline_location)
                    loc = f"  ||LOC:{line.inline_location}" if line.inline_location else ""
                    main_parts.append(f"[EDU_LINE]{clean_text}{loc}[/EDU_LINE]")

                elif line.role == ROLE_DATE_RANGE:
                    main_parts.append(f"[DATE]{text}[/DATE]")

                elif line.role == ROLE_BULLET:
                    main_parts.append(f"[BULLET]{text}[/BULLET]")

                elif line.role == ROLE_BODY:
                    main_parts.append(text)

        return DocumentStructure(
            full_width_text="\n".join(full_parts).strip(),
            sidebar_text="\n".join(sidebar_parts).strip(),
            main_text="\n".join(main_parts).strip(),
            classified_lines=lines,
        )

    # ─────────────────────────────────────────────────────────
    # Public helpers — called by pipeline
    # ─────────────────────────────────────────────────────────

    def _strip_loc_from_text(self, text: str, location: Optional[str]) -> str:
        """Remove trailing inline location words from line text to avoid duplication."""
        if not location or not text:
            return text
        # Location appears at end of text (possibly with extra spaces)
        # Try removing each word of the location from the end
        loc_words = location.split()
        result = text.rstrip()
        for word in reversed(loc_words):
            if result.endswith(word):
                result = result[:-len(word)].rstrip()
        return result.rstrip(", ").strip()

    def parse_sections(self, doc: 'DocumentStructure') -> Dict[str, str]:
        return self._parse_tagged_text(doc.main_text)

    def parse_sidebar(self, doc: 'DocumentStructure') -> Dict[str, List[str]]:
        raw = self._parse_tagged_text(doc.sidebar_text)
        return {k: [l.strip() for l in v.split("\n") if l.strip()] for k, v in raw.items()}

    def _parse_tagged_text(self, text: str) -> Dict[str, str]:
        from section_registry import SECTION_ALIASES

        sections: Dict[str, List[str]] = {}
        current = "__PREAMBLE__"
        sections[current] = []

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Pattern 1: bare [SECTION NAME] tag
            m = re.match(r'^\[([A-Z][A-Z\s]+)\]$', line)
            if m:
                current = m.group(1).strip()
                sections[current] = []
                continue

            # Pattern 2: [JOB_TITLE]Section Name[/JOB_TITLE] — section header
            # disguised as a job title because of font size
            m2 = re.match(r'^\[JOB_TITLE\](.*?)\[/JOB_TITLE\]$', line)
            if m2:
                candidate = m2.group(1).strip()
                # Check if this is a known section header
                if candidate.upper() in SECTION_ALIASES:
                    current = candidate.upper()
                    sections.setdefault(current, [])
                    continue
                # Also try cleaning (e.g., "Employment History" → "EMPLOYMENT HISTORY")
                cleaned = candidate.upper()
                if cleaned in SECTION_ALIASES:
                    current = cleaned
                    sections.setdefault(current, [])
                    continue

            sections.setdefault(current, []).append(line)

        return {k: "\n".join(v).strip() for k, v in sections.items() if any(v)}


# ─────────────────────────────────────────────────────────────
# Section block — arbitrary layout support
# ─────────────────────────────────────────────────────────────

@dataclass
class SectionBlock:
    """A detected section block with its content and metadata.

    Represents a single section found during layout analysis.
    Multiple SectionBlocks compose the full document structure,
    replacing the rigid header/sidebar/main model for complex layouts.
    """
    text: str                    # Cleaned text content
    section_type: Optional[str]  # Canonical section name (from registry) or None
    bbox: Optional[Tuple[float, float, float, float]] = None  # (x0, y0, x1, y1)
    confidence: float = 1.0      # Detection confidence
    source_column: str = "main"  # "left", "right", "full"
    parser_source: str = "layout"  # "layout", "section_detector", "fallback"


# ─────────────────────────────────────────────────────────────
# Document structure output
# ─────────────────────────────────────────────────────────────

@dataclass
class DocumentStructure:
    full_width_text: str
    sidebar_text: str
    main_text: str
    classified_lines: List[ClassifiedLine] = field(default_factory=list)
    hyperlinks: List[Dict[str, str]] = field(default_factory=list)
    section_blocks: List[SectionBlock] = field(default_factory=list)

    @property
    def layout(self) -> str:
        """
        Returns one of:
          single_column       — ATS-style, name/summary/experience/education stacked
          two_column          — Left sidebar (skills/contact) + right main
          header_sidebar_main — Wide header band + two-column body below
          table_based         — Resume formatted as a table (company|role|date rows)
        """
        has_left  = any(l.column == "left" for l in self.classified_lines)
        has_full  = any(l.column == "full" for l in self.classified_lines)
        has_table = self._detect_table_layout()

        if has_table:
            return "table_based"
        if has_full and has_left:
            return "header_sidebar_main"
        if has_left:
            return "two_column"
        return "single_column"

    def _detect_table_layout(self) -> bool:
        """Heuristic: if 30%+ of right-column lines look like table rows (pipe-separated)."""
        right_lines = [l for l in self.classified_lines if l.column in ('right', 'full')]
        if not right_lines:
            return False
        pipe_count = sum(1 for l in right_lines if '|' in l.text or '\t' in l.text)
        return pipe_count / len(right_lines) > 0.3

    @property
    def layout_type(self) -> str:
        """Alias for layout — explicit Phase 1 output key."""
        return self.layout

    @property
    def regions(self) -> Dict[str, str]:
        """
        Phase 1 output: named text regions.

        Returns:
          {
            "header":  name + contact band (full_width_text)
            "sidebar": left column text
            "main":    right / single column text
            "footer":  last paragraph if it looks like references
          }
        """
        footer = ""
        main_lines = self.main_text.split('\n')
        for line in reversed(main_lines[-5:]):
            if re.search(r'\b(references?\s+available|references?\s+on\s+request)\b',
                         line, re.IGNORECASE):
                footer = line.strip()
                break

        return {
            "header":  self.full_width_text,
            "sidebar": self.sidebar_text,
            "main":    self.main_text,
            "footer":  footer,
        }

    def build_section_blocks(self) -> None:
        """Populate section_blocks by scanning tagged text for section boundaries.

        Uses the section_registry to map detected section headers to canonical
        names. Each block gets parser_source='layout' since it comes from
        layout_extractor's tagged text analysis.

        Called after _build_document() in the extraction pipeline.
        """
        from section_registry import resolve

        blocks: List[SectionBlock] = []

        # Process main_text sections
        for source_text, column_label in [
            (self.main_text, "main"),
            (self.sidebar_text, "left"),
        ]:
            if not source_text.strip():
                continue
            current_section: Optional[str] = None
            current_lines: List[str] = []

            for line in source_text.split('\n'):
                stripped = line.strip()
                if not stripped:
                    continue

                # Check for bare [SECTION] tag
                m = re.match(r'^\[([A-Z][A-Z\s]+)\]$', stripped)
                if m:
                    # Flush previous block
                    if current_lines:
                        blocks.append(SectionBlock(
                            text='\n'.join(current_lines).strip(),
                            section_type=current_section,
                            source_column=column_label,
                            parser_source="layout",
                        ))
                        current_lines = []
                    header = m.group(1).strip()
                    current_section = resolve(header)
                    continue

                # Check for JOB_TITLE-wrapped section header
                m2 = re.match(r'^\[JOB_TITLE\](.*?)\[/JOB_TITLE\]$', stripped)
                if m2:
                    resolved = resolve(m2.group(1).strip())
                    if resolved:
                        if current_lines:
                            blocks.append(SectionBlock(
                                text='\n'.join(current_lines).strip(),
                                section_type=current_section,
                                source_column=column_label,
                                parser_source="layout",
                            ))
                            current_lines = []
                        current_section = resolved
                        continue

                current_lines.append(line)

            # Flush final block
            if current_lines:
                blocks.append(SectionBlock(
                    text='\n'.join(current_lines).strip(),
                    section_type=current_section,
                    source_column=column_label,
                    parser_source="layout",
                ))

        self.section_blocks = blocks