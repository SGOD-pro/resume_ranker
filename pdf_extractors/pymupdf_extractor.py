"""
PyMuPDF-based PDF Extraction Layer
====================================
Pure extraction — opens PDF, extracts page structure, hyperlinks,
and raw layout data. No parsing, no field extraction.

Uses `pymupdf` (not `fitz`) per the modern PyMuPDF API.
"""

import pymupdf
from typing import List, Dict, Any


class PyMuPDFExtractor:
    """Extract raw page structure from PDF using PyMuPDF.

    Returns structured data suitable for LayoutExtractor consumption:
    - pages: list of PyMuPDF dict-mode page outputs
    - hyperlinks: list of {uri: str} dicts
    - page_count: actual page count from PDF
    - page_dimensions: list of (width, height) tuples
    """

    def extract(self, pdf_path: str) -> Dict[str, Any]:
        """Extract raw page data from PDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            {
                'pages': [page_dict, ...],
                'hyperlinks': [{'uri': '...'}, ...],
                'page_count': int,
                'page_dimensions': [(width, height), ...],
            }
        """
        pages: List[dict] = []
        hyperlinks: List[Dict[str, str]] = []
        page_dimensions: list = []

        doc = pymupdf.open(pdf_path)
        try:
            for page in doc:
                # Primary extraction: dict mode with reading-order sort
                page_dict = page.get_text("dict", sort=True)
                pages.append(page_dict)
                page_dimensions.append(
                    (page_dict["width"], page_dict["height"])
                )

                # Extract hyperlinks from page
                for link in page.get_links():
                    uri = link.get("uri", "")
                    if uri:
                        hyperlinks.append({"uri": uri})

            return {
                "pages": pages,
                "hyperlinks": hyperlinks,
                "page_count": doc.page_count,
                "page_dimensions": page_dimensions,
            }
        finally:
            doc.close()
