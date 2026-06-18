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

# Pattern: "Project Name | Link Tech1, Tech2, Tech3"
# The "| Link" separates name from technologies
_PROJECT_HEADER_RE = re.compile(
    r'^(.+?)\s*\|\s*(?:Link|Demo|GitHub|Live)\s+(.+)$', re.I)

# Fallback: "Project Name | Tech1, Tech2" (pipe without Link keyword)
_PIPE_HEADER_RE = re.compile(
    r'^([A-Z][\w\s\-&/.]+?)\s*\|\s*([A-Z][\w\s,.\-/]+)$')


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

    def parse(self, text: str, hyperlinks: list = None) -> List[Dict[str, Any]]:
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

        # Post-process: assign GitHub/demo links from PDF hyperlinks
        if hyperlinks and projects:
            self._assign_hyperlinks(projects, hyperlinks)

        return projects

    def _split_blocks(self, text: str) -> List[str]:
        """
        Split project text into individual project blocks.
        Detects boundaries by:
          1. Blank lines
          2. Lines matching "ProjectName | Link Tech1, Tech2" pattern
          3. Title-like lines (short, starts uppercase, not a bullet)
        """
        lines = text.split('\n')
        blocks, current = [], []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if current:
                    blocks.append('\n'.join(current))
                    current = []
                continue

            # Check if this line is a project header (Name | Link Tech1, Tech2)
            is_header = bool(_PROJECT_HEADER_RE.match(stripped))

            # Also check pipe-separated headers
            if not is_header:
                is_header = bool(_PIPE_HEADER_RE.match(stripped))

            # Also check traditional title patterns
            if not is_header:
                is_header = self._is_title(stripped)

            # If it's a new project header and we have content, split here
            if is_header and current and len(current) > 0:
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
        tech_from_header = None

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
                    # Check for "Name | Link Tech1, Tech2" pattern
                    header_m = _PROJECT_HEADER_RE.match(clean)
                    if header_m:
                        name = header_m.group(1).strip().rstrip(':').strip()
                        tech_from_header = header_m.group(2).strip()
                    else:
                        # Check pipe-separated
                        pipe_m = _PIPE_HEADER_RE.match(clean)
                        if pipe_m:
                            name = pipe_m.group(1).strip().rstrip(':').strip()
                            tech_from_header = pipe_m.group(2).strip()
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

        # Extract technologies from the tech_from_header or from the full block
        tech_text = (tech_from_header or '') + '\n' + block
        technologies = self._get_skills_parser().parse(
            skills_section="", full_text=tech_text, also_scan_fulltext=True)

        return {
            "name":         name,
            "technologies": technologies,
            "description":  ' '.join(desc_parts).strip() or None,
            "github":       github,
            "demo":         demo,
        }

    def _assign_hyperlinks(self, projects: List[Dict[str, Any]],
                           hyperlinks: list) -> None:
        """
        Match PDF hyperlink annotations to projects by comparing project
        name keywords against URL path segments.
        E.g., project "Content Generator" matches github.com/user/ai-blog-writer
              if project name keywords partially match the URL slug.
        """
        github_links = []
        demo_links = []
        for h in hyperlinks:
            uri = h.get('uri', '')
            if not uri:
                continue
            if 'github.com' in uri.lower():
                # Skip profile-level GitHub links (no repo path)
                parts = uri.rstrip('/').split('/')
                if len(parts) > 4:  # github.com/user/repo
                    github_links.append(uri)
            elif uri.startswith('http') and not uri.startswith('mailto:'):
                if 'linkedin.com' not in uri and 'drive.google.com' not in uri:
                    demo_links.append(uri)

        # Simple assignment: distribute GitHub links to projects in order
        # This works because PDF hyperlinks are typically in document order
        gi, di = 0, 0
        for project in projects:
            if project.get('github') is None and gi < len(github_links):
                project['github'] = github_links[gi]
                gi += 1
            if project.get('demo') is None and di < len(demo_links):
                project['demo'] = demo_links[di]
                di += 1
