"""
section_assembly.py — Section content model and assembly utilities
===================================================================
Contains the SectionContent dataclass and section merging logic
used by the pipeline to combine multiple extraction paths.
"""

from dataclasses import dataclass


@dataclass
class SectionContent:
    """Section content preserving both tagged and plain text.

    tagged_text: text with [JOB_TITLE], [DATE], [BULLET] tags (for assembler)
    plain_text:  raw text stripped of tags (for standalone parsers)
    source:      which extraction path found this section
    """
    plain_text: str = ""
    tagged_text: str = ""
    source: str = "unknown"
