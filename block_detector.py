"""
block_detector.py — Phase 2: Semantic block classification
============================================================
Maps layout_extractor spatial regions to semantic blocks:
  { header, sidebar, main, footer }
"""

import re
from typing import Dict


class BlockDetector:
    """Thin semantic layer on top of layout_extractor's spatial split."""

    def detect(self, doc) -> Dict[str, str]:
        """
        doc: DocumentStructure from layout_extractor.extract()
        Returns: { header, sidebar, main, footer }
        """
        footer = ""
        for line in reversed(doc.main_text.split('\n')[-5:]):
            if re.search(r'\b(references?\s+available|references?\s+on\s+request)\b',
                         line, re.I):
                footer = line.strip()
                break

        return {
            "header":  doc.full_width_text.strip(),
            "sidebar": doc.sidebar_text.strip(),
            "main":    doc.main_text.strip(),
            "footer":  footer,
        }


def detect_blocks(doc) -> Dict[str, str]:
    """Convenience wrapper."""
    return BlockDetector().detect(doc)
