"""
Section-to-Fields Parser v2
Receives CLEAN section text. Parses each section independently.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

DATE_RANGE = re.compile(
    r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})'
    r'\s*[–—\-]+\s*'
    r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now)',
    re.IGNORECASE
)
DEGREE = re.compile(
    r'\b(Bachelor|Master|Ph\.?D|MBA|M\.?S\.?|B\.?S\.?|B\.?A\.?|M\.?A\.?'
    r'|Associate|Diploma|Certificate|Doctor)\b', re.IGNORECASE
)
BULLET = re.compile(r'^[•\-\*▪▸►✓✔]\s*')

def strip_bullet(s): return BULLET.sub("", s).strip()
def split_lines(t): return [l.strip() for l in t.split("\n") if l.strip()]
def find_date(t):
    m = DATE_RANGE.search(t)
    return (m.group("start"), m.group("end")) if m else None


class SidebarExtractor:
    def extract(self, sections: Dict[str, List[str]]) -> Dict[str, Any]:
        # Sections come in as {NAME: [lines]}
        # DETAILS / untagged top area contains ADDRESS, PHONE, EMAIL
        # because those subheadings may not be tagged as [SECTION]
        # Parse them from raw sidebar text

        def get(keys):
            for k in keys:
                v = sections.get(k, [])
                if v: return " ".join(v)
            return None

        def get_list(keys):
            for k in keys:
                v = sections.get(k, [])
                if v:
                    result = []
                    for line in v:
                        result.extend(x.strip() for x in re.split(r'[,;]', line) if x.strip())
                    return result
            return []

        # Email and phone may be in __PREAMBLE__ or DETAILS section
        all_lines = []
        for v in sections.values():
            all_lines.extend(v)

        email_m = re.search(r'\b[\w._%+\-]+@[\w.\-]+\.[a-z]{2,}\b', "\n".join(all_lines), re.I)
        phone_m = re.search(r'\b\d{7,15}\b', "\n".join(all_lines))

        # Address: lines that look like address (digits + words, or city/state)
        address_lines = []
        for line in all_lines:
            if re.match(r'^\d{3,5}\s+\w', line):  # street address
                address_lines.append(line)
            elif re.search(r'\b(CA|NY|TX|FL|IL|WA|PA|OH|GA|NC|AZ)\b', line):
                address_lines.append(line)
            elif line in ("United States", "United Kingdom", "Canada", "India"):
                address_lines.append(line)

        links = sections.get("LINKS", [])
        skip = {"resume templates", "build this template", "pinterest"}
        links = [l for l in links if l.lower() not in skip and "resumeviking" not in l.lower()]

        return {
            "address": ", ".join(address_lines) if address_lines else get(["ADDRESS"]),
            "phone": phone_m.group(0) if phone_m else None,
            "email": email_m.group(0) if email_m else None,
            "place_of_birth": get(["PLACE OF BIRTH"]),
            "driving_license": get(["DRIVING LICENSE"]),
            "links": links,
            "skills": get_list(["SKILLS"]),
            "hobbies": get_list(["HOBBIES"]),
            "languages": get_list(["LANGUAGES"]),
        }


class EmploymentParser:
    """
    Parses employment section text into job entries.
    Anchor: date ranges. Role/company are the line(s) immediately before.
    Bullets follow the date line until the next role starts.
    """
    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        lines = split_lines(text)
        jobs = []
        i = 0

        while i < len(lines):
            date_match = DATE_RANGE.search(lines[i])
            if date_match and i > 0:
                start = date_match.group("start")
                end = date_match.group("end")

                # Role line is immediately before the date
                role_line = lines[i - 1]

                # Check if role_line itself looks like a header / previous section bleed
                # A valid role line contains at least one alpha word and is not ALL CAPS section name
                if re.match(r'^[A-Z\s]+$', role_line) and len(role_line) < 40:
                    i += 1
                    continue

                role, company = self._split_role_company(role_line)

                # Collect description + bullets until next date anchor or section header
                description_lines = []
                bullet_lines = []
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    # Stop at next date range (new job) or section marker
                    if DATE_RANGE.search(nxt):
                        break
                    if re.match(r'^[A-Z\s]{4,}$', nxt) and len(nxt.split()) <= 3:
                        break  # looks like a section header
                    if BULLET.match(nxt):
                        bullet_lines.append(strip_bullet(nxt))
                    else:
                        description_lines.append(nxt)
                    j += 1

                # Merge multi-line bullets (continuation lines after a bullet)
                merged_bullets = self._merge_continuations(bullet_lines, description_lines, lines, i+1, j)

                jobs.append({
                    "role": role.strip() if role else None,
                    "company": company.strip() if company else None,
                    "start_date": start,
                    "end_date": end,
                    "description": " ".join(
                        l for l in description_lines if not BULLET.match(l)
                    ).strip() or None,
                    "achievements": merged_bullets,
                })
                i = j
                continue
            i += 1

        return jobs

    def _split_role_company(self, line: str) -> Tuple[Optional[str], Optional[str]]:
        if not line:
            return None, None
        # "Role (qualifier) , Company  Location" → split on comma
        parts = re.split(r'\s*,\s*', line, maxsplit=1)
        if len(parts) == 2:
            role = parts[0].strip()
            # Company may have location with 2+ spaces separator
            company = re.split(r'\s{2,}', parts[1])[0].strip()
            return role, company
        m = re.split(r'\s+(?:at|@|–|—)\s+', line, maxsplit=1, flags=re.IGNORECASE)
        if len(m) == 2:
            return m[0].strip(), m[1].strip()
        return line.strip(), None

    def _merge_continuations(self, bullets, desc, all_lines, start, end):
        """Re-parse the raw lines to merge multi-line bullets properly."""
        result = []
        current = None
        for line in all_lines[start:end]:
            if BULLET.match(line):
                if current:
                    result.append(current.strip())
                current = strip_bullet(line)
            elif current:
                # Continuation of previous bullet
                current += " " + line.strip()
            # Non-bullet non-continuation: skip (it's description)
        if current:
            result.append(current.strip())
        return result


class EducationParser:
    def parse(self, text: str) -> List[Dict[str, Any]]:
        if not text:
            return []
        lines = split_lines(text)
        edu_list = []
        i = 0

        while i < len(lines):
            line = lines[i]
            date = find_date(line)

            if date and i > 0:
                # Entry is on line(s) above the date
                entry_line = lines[i - 1]

                # If entry_line looks like continuation (University name alone), merge with line above
                if i > 1 and not DEGREE.search(entry_line):
                    candidate = lines[i - 2] + " " + entry_line
                    if DEGREE.search(candidate):
                        entry_line = candidate

                degree_m = DEGREE.search(entry_line)
                if not degree_m:
                    i += 1
                    continue

                # Field of study: "in X"
                field_m = re.search(r'\bin\s+([A-Za-z][A-Za-z\s&]+?)(?:,|\s{2,}|$)', entry_line)
                field = field_m.group(1).strip() if field_m else None

                # Institution: after comma
                inst_m = re.search(
                    r',\s*([A-Za-z][A-Za-z\s&\.]+(?:University|College|School|Institute|Academy)[A-Za-z\s]*)',
                    entry_line
                )
                institution = inst_m.group(1).strip() if inst_m else None

                # Location: trailing part after 2+ spaces
                loc_parts = re.split(r'\s{2,}', entry_line)
                location = loc_parts[-1].strip() if len(loc_parts) > 1 else None

                edu_list.append({
                    "degree_type": degree_m.group(0),
                    "field_of_study": field,
                    "institution": institution,
                    "location": location,
                    "start_date": date[0],
                    "end_date": date[1],
                    "gpa": None,
                })

            i += 1
        return edu_list


class AccomplishmentsParser:
    def parse(self, text: str) -> List[str]:
        if not text:
            return []
        lines = split_lines(text)
        result, current = [], ""
        for line in lines:
            if BULLET.match(line):
                if current: result.append(current.strip())
                current = strip_bullet(line)
            elif current:
                current += " " + line
            else:
                current = line
        if current:
            result.append(current.strip())
        return result


class CoursesParser:
    def parse(self, text: str) -> List[Dict]:
        if not text:
            return []
        lines = split_lines(text)
        courses, i = [], 0
        while i < len(lines):
            date = find_date(lines[i])
            if date and i > 0:
                name_parts = []
                j = i - 1
                while j >= 0 and not find_date(lines[j]):
                    name_parts.insert(0, lines[j])
                    j -= 1
                    if len(name_parts) >= 3:
                        break
                name = " ".join(name_parts).strip()
                if name:
                    courses.append({
                        "name": name,
                        "start_date": date[0],
                        "end_date": date[1],
                    })
            i += 1
        return courses


class ResumeAssembler:
    def __init__(self):
        self.sidebar_extractor = SidebarExtractor()
        self.employment_parser = EmploymentParser()
        self.education_parser = EducationParser()
        self.accomplishments_parser = AccomplishmentsParser()
        self.courses_parser = CoursesParser()

    def _find_section(self, sections, keys):
        for k in keys:
            if k in sections:
                return sections[k]
        return ""

    def assemble(self, full_width_text, sidebar_sections, main_sections) -> Dict[str, Any]:
        lines = [l.strip() for l in full_width_text.split("\n") if l.strip()]
        name = lines[0] if lines else None
        title = self._find_section(main_sections, ["NUTRITION CONSULTANT", "__PREAMBLE__"])
        # Title: first non-section-header line in main if not found
        if not title:
            preamble = main_sections.get("__PREAMBLE__", "")
            title_lines = [l.strip() for l in preamble.split("\n") if l.strip()]
            title = title_lines[0] if title_lines else None

        contact = self.sidebar_extractor.extract(sidebar_sections)

        employment_text = self._find_section(main_sections,
            ["EMPLOYMENT HISTORY", "EXPERIENCE", "WORK EXPERIENCE", "PROFESSIONAL EXPERIENCE"])
        education_text = self._find_section(main_sections,
            ["EDUCATION", "ACADEMIC BACKGROUND"])
        profile_text = self._find_section(main_sections,
            ["PROFILE", "SUMMARY", "OBJECTIVE", "ABOUT ME"])
        accomplishments_text = self._find_section(main_sections,
            ["ACCOMPLISHMENTS", "ACHIEVEMENTS"])
        courses_text = self._find_section(main_sections,
            ["COURSES", "CERTIFICATIONS", "CERTIFICATES"])

        return {
            "personal_info": {
                "name": name,
                "title": title,
                "address": contact.get("address"),
                "phone": contact.get("phone"),
                "email": contact.get("email"),
                "place_of_birth": contact.get("place_of_birth"),
                "driving_license": contact.get("driving_license"),
                "links": contact.get("links", []),
            },
            "profile": profile_text or None,
            "skills": contact.get("skills", []),
            "hobbies": contact.get("hobbies", []),
            "languages": contact.get("languages", []),
            "employment_history": self.employment_parser.parse(employment_text),
            "education": self.education_parser.parse(education_text),
            "courses": self.courses_parser.parse(courses_text),
            "accomplishments": self.accomplishments_parser.parse(accomplishments_text),
        }
