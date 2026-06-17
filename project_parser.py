"""
project_parser.py — Phase 8: Project extraction
=================================================
Developer resumes lose significant ranking without project parsing.
Uses skills_dictionary.json for technology detection. No NER.

Output: [{ name, technologies, description, github, demo }]
"""

import re
from typing import List, Dict, Any, Optional


_GITHUB_RE = re.compile(
    r'(?:https?://)?(?:www\.)?github\.com/[\w\-_%]+(?:/[\w\-_%\.]+)?', re.I)
_URL_RE = re.compile(r'https?://\S+|(?:www\.)\S+', re.I)
_BULLET_RE = re.compile(r'^[•·▪▸►✓✔\*\-]\s+(.+)')
_TECH_RE = re.compile(
    r'(?i)(?:tech(?:nologies)?|stack|tools?|built\s+(?:with|using)|'
    r'technologies\s+used)[:\s]+([^\n]+)')


class ProjectParser:
    """Parse project entries from projects section text."""

    def __init__(self):
        # Lazy import to avoid circular deps at module level
        self._skills_parser = None

    def _get_skills_parser(self):
        if self._skills_parser is None:
            from skills_parser import SkillsParser
            self._skills_parser = SkillsParser()
        return self._skills_parser

    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text or not text.strip():
            return []
        blocks = self._split_blocks(text)
        projects = []
        for block in blocks:
            if not block.strip():
                continue
            p = self._parse_block(block)
            if p.get('name') or p.get('description'):
                projects.append(p)
        return projects

    def _split_blocks(self, text: str) -> List[str]:
        """Split by blank lines or title-like lines."""
        lines = text.split('\n')
        blocks, current = [], []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current:
                    blocks.append('\n'.join(current))
                    current = []
                continue
            # New project title: non-bullet, 1-7 words, starts uppercase
            if (current and self._is_title(stripped)
                    and len(current) > 1):
                blocks.append('\n'.join(current))
                current = []
            current.append(line)
        if current:
            blocks.append('\n'.join(current))
        return [b for b in blocks if b.strip() and len(b.strip().split()) > 2]

    def _is_title(self, line: str) -> bool:
        if not line or _BULLET_RE.match(line):
            return False
        words = line.split()
        if not (1 <= len(words) <= 7):
            return False
        if not words[0][0].isupper():
            return False
        if line.isupper() and len(words) <= 2:
            return False
        return True

    def _parse_block(self, block: str) -> Dict[str, Any]:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        name, desc_parts, github, demo = None, [], None, None

        for i, line in enumerate(lines):
            # GitHub URL
            gh_m = _GITHUB_RE.search(line)
            if gh_m:
                github = gh_m.group(0)
            # Other URL = demo
            elif not gh_m:
                for url in _URL_RE.findall(line):
                    if 'github.com' not in url.lower():
                        demo = url.strip()
                        break

            clean = _URL_RE.sub('', line).strip()

            if i == 0 and clean:
                bullet_m = _BULLET_RE.match(clean)
                if bullet_m:
                    desc_parts.append(bullet_m.group(1).strip())
                else:
                    name = clean.rstrip(':').strip()
                continue

            bullet_m = _BULLET_RE.match(clean)
            if bullet_m:
                desc_parts.append(bullet_m.group(1).strip())
            elif _TECH_RE.search(clean):
                pass  # tech info — will be extracted below
            elif clean:
                desc_parts.append(clean)

        tech_text = (name or '') + '\n' + block
        technologies = self._get_skills_parser().parse(
            skills_section="", full_text=tech_text, also_scan_fulltext=True)

        return {
            "name":         name,
            "technologies": technologies,
            "description":  ' '.join(desc_parts).strip() or None,
            "github":       github,
            "demo":         demo,
        }
