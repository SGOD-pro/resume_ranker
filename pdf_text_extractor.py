"""
PDF Text Extractor
Handles: scanned-style, columnar, table-heavy, multi-section PDFs
Priority: pdfplumber (layout-aware) > pymupdf (fast) > pdfminer (fallback)
"""
import re
import fitz  # pymupdf
import pdfplumber
from pdfminer.high_level import extract_text as pdfminer_extract
from typing import Optional

class PDFTextExtractor:
    """
    Multi-strategy PDF text extractor.
    """
    def extract(self, pdf_path: str) -> dict:
        result = self._try_pdfplumber(pdf_path)
        if result and self._is_usable(result["raw_text"]):
            result["metadata"]["strategy"] = "pdfplumber"
            return result

        result = self._try_pymupdf(pdf_path)
        if result and self._is_usable(result["raw_text"]):
            result["metadata"]["strategy"] = "pymupdf"
            return result

        result = self._try_pdfminer(pdf_path)
        result["metadata"]["strategy"] = "pdfminer"
        return result

    def _try_pdfplumber(self, pdf_path: str) -> Optional[dict]:
        try:
            pages = []
            all_text_parts = []

            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    # Use layout=True to preserve spatial structure and prevent column merging
                    page_text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3) or ""
                    
                    tables = page.extract_tables()
                    table_texts = []
                    for table in tables:
                        for row in table:
                            if row:
                                clean_row = [cell.strip() if cell else "" for cell in row]
                                table_texts.append(" | ".join(filter(None, clean_row)))

                    combined = page_text
                    if table_texts:
                        combined += "\n" + "\n".join(table_texts)

                    pages.append({
                        "page_num": i + 1,
                        "text": combined,
                        "tables": tables
                    })
                    all_text_parts.append(combined)

            raw = "\n\n".join(all_text_parts)
            return {
                "raw_text": self._clean_text(raw),
                "pages": pages,
                "metadata": {"page_count": len(pages), "strategy": "pdfplumber"}
            }
        except Exception:
            return None

    def _try_pymupdf(self, pdf_path: str) -> Optional[dict]:
        try:
            doc = fitz.open(pdf_path)
            pages = []
            all_text_parts = []

            for i, page in enumerate(doc):
                text = page.get_text("text")
                pages.append({"page_num": i + 1, "text": text, "tables": []})
                all_text_parts.append(text)

            doc.close()
            raw = "\n\n".join(all_text_parts)
            return {
                "raw_text": self._clean_text(raw),
                "pages": pages,
                "metadata": {"page_count": len(pages), "strategy": "pymupdf"}
            }
        except Exception:
            return None

    def _try_pdfminer(self, pdf_path: str) -> dict:
        try:
            raw = pdfminer_extract(pdf_path)
        except Exception:
            raw = ""
        return {
            "raw_text": self._clean_text(raw),
            "pages": [],
            "metadata": {"page_count": 0, "strategy": "pdfminer"}
        }

    def _clean_text(self, text: str) -> str:
        """
        Fix common PDF artifacts aggressively.
        """
        if not text:
            return ""

        # 1. Fix spaced out words like "J ULIE" -> "JULIE"
        text = re.sub(r'\b([A-Z])\s+([A-Z][a-z]+)\b', r'\1\2', text)
        
        # 2. Fix split words like "Pacif ic" -> "Pacific" (heuristic: short second part)
        text = re.sub(r'\b([A-Za-z]+)\s+([a-z]{1,2})\b', r'\1\2', text)
        
        # 3. Fix fully spaced out words like "D E T A I L S" -> "DETAILS"
        text = re.sub(r'\b([A-Z](?:\s+[A-Z]){2,})\b', lambda m: m.group(0).replace(" ", ""), text)

        # 4. Fix ligatures and special characters
        ligatures = {
            '\ufb01': 'fi', '\ufb02': 'fl', '\ufb00': 'ff',
            '\ufb03': 'ffi', '\ufb04': 'ffl', '\u2019': "'",
            '\u201c': '"', '\u201d': '"', '\u2013': '-', '\u2014': '-',
            '\xa0': ' ', '\u2022': '-', '\u2023': '-', '\u25e6': '-',
            '\u25aa': '-', '\u25ab': '-', '\u25cf': '-', '\u25cb': '-',
            '\u2018': "'", '\u201b': "'"
        }
        for char, replacement in ligatures.items():
            text = text.replace(char, replacement)

        # 5. Normalize whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = '\n'.join(line.rstrip() for line in text.split('\n'))

        return text.strip()

    def _is_usable(self, text: str) -> bool:
        if not text:
            return False
        alpha_chars = sum(1 for c in text if c.isalpha())
        return len(text) > 100 and alpha_chars > 50