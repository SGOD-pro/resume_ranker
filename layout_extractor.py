"""
Layout-Aware PDF Extractor v3
Font-aware + coordinate-aware. Sidebar section headers are Bold uppercase.
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import pdfplumber


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


@dataclass
class Line:
    words: List[Word]
    column: str  # "left" | "right"

    @property
    def text(self):
        if not self.words:
            return ""
        result = self.words[0].text
        for i in range(1, len(self.words)):
            prev, curr = self.words[i-1], self.words[i]
            gap = curr.x0 - prev.x1
            result += (" " if gap > 1 else "") + curr.text
        return result

    @property
    def is_bold(self):
        return all(w.is_bold for w in self.words) if self.words else False

    @property
    def avg_size(self):
        sizes = [w.size for w in self.words if w.size]
        return sum(sizes) / len(sizes) if sizes else 0.0


@dataclass
class DocumentStructure:
    layout: str
    full_width_text: str
    sidebar_text: str
    main_text: str


class LayoutAwarePDFExtractor:

    def extract(self, pdf_path: str) -> DocumentStructure:
        pages_data = []
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                raw = page.extract_words(
                    x_tolerance=3, y_tolerance=3,
                    keep_blank_chars=False,
                    extra_attrs=["fontname", "size"]
                )
                if not raw:
                    continue
                words = [
                    Word(w["text"], float(w["x0"]), float(w["x1"]),
                         float(w["top"]), float(w["bottom"]),
                         str(w.get("fontname") or ""), float(w.get("size") or 0))
                    for w in raw
                ]
                split_x = self._find_split(words, float(page.width))
                lines = self._to_lines(words, split_x)
                pages_data.append(lines)

        return self._build(pages_data)

    def _find_split(self, words, page_width):
        occupied = set()
        for w in words:
            for x in range(int(w.x0), int(w.x1)+1):
                occupied.add(x)
        best_start, best_len = None, 0
        cs, cl = None, 0
        for x in range(int(page_width*0.15), int(page_width*0.75)):
            if x not in occupied:
                if cs is None: cs = x
                cl += 1
            else:
                if cl > best_len:
                    best_len, best_start = cl, cs
                cs, cl = None, 0
        return (best_start + best_len/2) if best_len >= 15 and best_start else None

    def _to_lines(self, words, split_x):
        if not words:
            return []
        Y_TOL = 3.0
        sorted_w = sorted(words, key=lambda w: (round(w.top/Y_TOL)*Y_TOL, w.x0))
        raw_lines, current = [], [sorted_w[0]]
        cy = sorted_w[0].top
        for w in sorted_w[1:]:
            if abs(w.top - cy) <= Y_TOL:
                current.append(w)
            else:
                raw_lines.append(sorted(current, key=lambda x: x.x0))
                current, cy = [w], w.top
        if current:
            raw_lines.append(sorted(current, key=lambda x: x.x0))

        lines = []
        for lw in raw_lines:
            if not split_x:
                lines.append(Line(lw, "right"))
                continue
            left = [w for w in lw if w.x0 < split_x]
            right = [w for w in lw if w.x0 >= split_x]
            if left: lines.append(Line(left, "left"))
            if right: lines.append(Line(right, "right"))
        return lines

    def _build(self, pages_data):
        full_parts, sidebar_parts, main_parts = [], [], []

        for lines in pages_data:
            for line in lines:
                text = line.text.strip()
                if not text:
                    continue

                is_section_header = (
                    line.is_bold and text.isupper()
                    and 1 <= len(text.split()) <= 4
                    and not text.replace(" ", "").isdigit()
                    and len(text) >= 3
                )

                # Large bold = name/document title (full width)
                if line.is_bold and line.avg_size > 14 and line.column == "right":
                    full_parts.append(text)
                elif line.column == "left":
                    # Sidebar: tag section headers
                    if is_section_header:
                        sidebar_parts.append(f"\n[{text}]\n")
                    else:
                        sidebar_parts.append(text)
                else:
                    # Main column: tag section headers
                    if is_section_header:
                        main_parts.append(f"\n[{text}]\n")
                    else:
                        main_parts.append(text)

        has_left = any(
            line.column == "left"
            for lines in pages_data for line in lines
        )

        return DocumentStructure(
            layout="two_column" if has_left else "single_column",
            full_width_text="\n".join(full_parts).strip(),
            sidebar_text="\n".join(sidebar_parts).strip(),
            main_text="\n".join(main_parts).strip(),
        )

    def parse_sections(self, doc: DocumentStructure) -> Dict[str, str]:
        """Parse main_text into {SECTION_HEADER: content} dict."""
        return self._parse_tagged(doc.main_text)

    def parse_sidebar(self, doc: DocumentStructure) -> Dict[str, List[str]]:
        raw = self._parse_tagged(doc.sidebar_text)
        # Also capture untagged top lines as DETAILS
        result = {}
        for k, v in raw.items():
            result[k] = [l.strip() for l in v.split("\n") if l.strip()]
        return result

    def _parse_tagged(self, text: str) -> Dict[str, str]:
        sections, current = {}, "__PREAMBLE__"
        sections[current] = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^\[([A-Z][A-Z\s]+)\]$', line)
            if m:
                current = m.group(1).strip()
                sections[current] = []
            else:
                sections.setdefault(current, []).append(line)
        return {k: "\n".join(v).strip() for k, v in sections.items() if any(v)}
