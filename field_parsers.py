"""
Domain-specific field parsers.
Given raw text + detected domain → extract structured fields.
Each parser uses regex + heuristics, no LLM.
"""
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


# ------------------------------------------------------------------ #
# Shared utilities
# ------------------------------------------------------------------ #

def find_section(text: str, headers: List[str], next_headers: Optional[List[str]] = None) -> str:
    """Extract text between a section header and the next section."""
    pattern = r'(?i)(?:^|\n)\s*(?:' + '|'.join(re.escape(h) for h in headers) + r')\s*:?\s*\n'
    match = re.search(pattern, text)
    if not match:
        return ""

    start = match.end()
    if next_headers:
        end_pattern = r'(?i)(?:^|\n)\s*(?:' + '|'.join(re.escape(h) for h in next_headers) + r')\s*:?\s*\n'
        end_match = re.search(end_pattern, text[start:])
        end = start + end_match.start() if end_match else len(text)
    else:
        end = len(text)

    return text[start:end].strip()


def extract_date_ranges(text: str) -> List[Dict[str, str]]:
    """Extract date ranges like 'Jan 2019 – Dec 2021' or 'Jan 2019 – Present'."""
    pattern = (
        r'(?P<start>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4})'
        r'\s*[-–—to]+\s*'
        r'(?P<end>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now)'
    )
    ranges = []
    for m in re.finditer(pattern, text, re.IGNORECASE):
        ranges.append({"start": m.group("start").strip(), "end": m.group("end").strip()})
    return ranges


def extract_bullets(text: str) -> List[str]:
    """Extract bullet points or numbered list items."""
    bullets = []
    for line in text.split('\n'):
        line = line.strip()
        # Match bullet symbols or numbers
        m = re.match(r'^(?:[-•·▪▸►✓✔*]|\d+[.):])\s+(.+)', line)
        if m:
            bullets.append(m.group(1).strip())
        elif line and len(line) > 20:
            bullets.append(line)
    return [b for b in bullets if len(b) > 5]


# ------------------------------------------------------------------ #
# Resume / CV Parser
# ------------------------------------------------------------------ #

class ResumeParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "personal_info": self._personal_info(text, entities),
            "work_experience": self._work_experience(text),
            "education": self._education(text),
            "skills": self._skills(text),
            "certifications": self._certifications(text),
            "languages": self._languages(text, entities),
            "summary": self._summary(text),
        }

    def _personal_info(self, text: str, entities: list) -> Dict[str, Any]:
        # Name: first PERSON entity (usually top of resume)
        persons = [e for e in entities if e.label == "PERSON"]
        name = persons[0].text if persons else self._guess_name(text)

        # Email
        email_m = re.search(r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b', text)
        email = email_m.group(0) if email_m else None

        # Phone
        phone_m = re.search(
            r'(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}(?!\d)', text
        )
        phone = phone_m.group(0).strip() if phone_m else None

        # Location (city, state)
        locations = [e for e in entities if e.label == "LOCATION"]
        location = locations[0].text if locations else None

        # LinkedIn
        linkedin_m = re.search(r'linkedin\.com/in/[A-Za-z0-9\-_%]+', text, re.IGNORECASE)
        linkedin = linkedin_m.group(0) if linkedin_m else None

        return {
            "name": name,
            "email": email,
            "phone": phone,
            "location": location,
            "linkedin": linkedin,
        }

    def _guess_name(self, text: str) -> Optional[str]:
        """Heuristic: first non-empty line is often the name."""
        for line in text.split('\n'):
            line = line.strip()
            # Name: 2-4 words, all alpha/hyphen, no numbers
            if re.match(r'^[A-Z][a-zA-Z\-]+(?:\s+[A-Z][a-zA-Z\-]+){1,3}$', line):
                return line
        return None

    def _work_experience(self, text: str) -> List[Dict[str, Any]]:
        section = find_section(
            text,
            ["work experience", "experience", "employment history", "professional experience"],
            ["education", "skills", "certifications", "languages", "awards", "projects"]
        )
        if not section:
            section = text  # fallback: scan full text

        jobs = []
        # Pattern: Job Title at/@ Company | Date range
        # Common formats:
        # "Software Engineer\nAcme Corp | Jan 2020 – Present"
        # "Jan 2020 – Present | Software Engineer | Acme Corp"

        # Split by date ranges as anchors
        date_pattern = (
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}'
            r'\s*[-–—to]+\s*'
            r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|Present|Current|Now)'
        )

        # Find all date ranges and their positions
        date_matches = list(re.finditer(date_pattern, section, re.IGNORECASE))

        for i, dm in enumerate(date_matches):
            date_range = dm.group(0).strip()

            # Context: few lines around the date
            ctx_start = max(0, dm.start() - 200)
            ctx_end = min(len(section), dm.end() + 400)
            context = section[ctx_start:ctx_end]

            # Extract role: line before date
            before = section[ctx_start:dm.start()].strip()
            lines_before = [l.strip() for l in before.split('\n') if l.strip()]

            # Extract company: line after date or same line
            after = section[dm.end():ctx_end].strip()
            lines_after = [l.strip() for l in after.split('\n') if l.strip()]

            role = lines_before[-1] if lines_before else None
            company = lines_after[0] if lines_after else None

            # Bullets: subsequent lines
            bullets = []
            for line in lines_after[1:]:
                m = re.match(r'^[-•·*]\s+(.+)', line)
                if m:
                    bullets.append(m.group(1))
                elif re.match(r'^[A-Z]', line) and len(line) > 15:
                    bullets.append(line)

            if date_range and (role or company):
                jobs.append({
                    "role": role,
                    "company": company,
                    "date_range": date_range,
                    "responsibilities": bullets[:5],  # cap at 5
                })

        return jobs

    def _education(self, text: str) -> List[Dict[str, Any]]:
        section = find_section(
            text,
            ["education", "academic background", "qualifications"],
            ["skills", "certifications", "experience", "languages", "awards"]
        )
        if not section:
            return []

        edu_list = []
        # Degree patterns
        degree_pattern = r'\b(Bachelor|Master|Ph\.?D|MBA|M\.?S\.?|B\.?S\.?|B\.?A\.?|M\.?A\.?|Associate|Diploma|Certificate)[s\.]?\b'

        degree_matches = list(re.finditer(degree_pattern, section, re.IGNORECASE))
        for dm in degree_matches:
            ctx_start = max(0, dm.start() - 50)
            ctx_end = min(len(section), dm.end() + 300)
            context = section[ctx_start:ctx_end]
            lines = [l.strip() for l in context.split('\n') if l.strip()]

            # Find institution (line with "University", "College", "School", "Institute")
            institution = None
            for line in lines:
                if re.search(r'\b(university|college|school|institute|academy)\b', line, re.IGNORECASE):
                    institution = line
                    break

            # Find date
            date_m = re.search(
                r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
                r'\d{4})\w*\.?\s*\d{0,4}', context
            )
            grad_date = date_m.group(0).strip() if date_m else None

            # Field of study: after "in" or "of"
            field_m = re.search(
                r'\b(?:in|of)\s+([A-Z][a-zA-Z\s&,]+?)(?:\n|,|\.|$)', context
            )
            field = field_m.group(1).strip() if field_m else None

            # GPA
            gpa_m = re.search(r'\bGPA\s*:?\s*([\d.]+)', context, re.IGNORECASE)
            gpa = gpa_m.group(1) if gpa_m else None

            edu_list.append({
                "degree": dm.group(0),
                "institution": institution,
                "field_of_study": field,
                "graduation_date": grad_date,
                "gpa": gpa,
            })

        return edu_list

    def _skills(self, text: str) -> List[str]:
        section = find_section(
            text,
            ["skills", "technical skills", "core competencies", "competencies", "expertise"],
            ["experience", "education", "certifications", "languages", "references"]
        )
        if not section:
            return []

        skills = []
        # Parse comma/bullet/pipe-separated skills
        for line in section.split('\n'):
            line = line.strip()
            if ',' in line:
                skills.extend([s.strip() for s in line.split(',') if s.strip()])
            elif '|' in line:
                skills.extend([s.strip() for s in line.split('|') if s.strip()])
            elif '•' in line or '-' in line:
                skills.extend([
                    re.sub(r'^[-•]\s*', '', s).strip()
                    for s in re.split(r'[•\-]', line) if s.strip()
                ])
            elif line:
                skills.append(line)

        # Deduplicate, cap length
        seen = set()
        clean = []
        for s in skills:
            s_lower = s.lower()
            if s_lower not in seen and 2 < len(s) < 60:
                seen.add(s_lower)
                clean.append(s)
        return clean[:30]  # cap

    def _certifications(self, text: str) -> List[Dict[str, str]]:
        section = find_section(
            text,
            ["certifications", "certificates", "licenses", "credentials"],
            ["skills", "experience", "education", "languages", "awards"]
        )
        if not section:
            # Try to find certifications inline
            section = text

        certs = []
        cert_pattern = r'\b(?:Certified|Certificate|Certification|License|Licensed|CPA|PMP|AWS|GCP|Azure|CFA|CMA|PHR|SHRM)\b.{0,80}?(?:\d{4}|$)'
        for m in re.finditer(cert_pattern, section, re.IGNORECASE | re.MULTILINE):
            text_val = m.group(0).strip()
            # Find issuing date
            date_m = re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}\b|\b\d{4}\b', text_val)
            certs.append({
                "name": text_val,
                "date": date_m.group(0) if date_m else None,
            })

        return certs[:10]

    def _languages(self, text: str, entities: list) -> List[str]:
        section = find_section(
            text,
            ["languages", "language skills"],
            ["skills", "experience", "education", "certifications"]
        )
        check_text = section if section else text

        # Known languages list
        known_languages = [
            "english", "french", "spanish", "german", "mandarin", "chinese",
            "arabic", "hindi", "portuguese", "russian", "japanese", "italian",
            "korean", "dutch", "swedish", "norwegian", "danish", "polish",
            "turkish", "ukrainian", "bengali", "urdu", "tagalog", "vietnamese"
        ]
        found = []
        for lang in known_languages:
            if re.search(r'\b' + lang + r'\b', check_text, re.IGNORECASE):
                found.append(lang.title())

        # Also from entities
        lang_entities = [e.text for e in entities if e.label == "LANGUAGE"]
        for le in lang_entities:
            if le.title() not in found:
                found.append(le.title())

        return found

    def _summary(self, text: str) -> Optional[str]:
        section = find_section(
            text,
            ["summary", "objective", "profile", "about me", "professional summary", "career objective"],
            ["experience", "education", "skills", "certifications", "employment"]
        )
        if section:
            return section[:500]  # limit length
        return None


# ------------------------------------------------------------------ #
# Finance Parser
# ------------------------------------------------------------------ #

class FinanceParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "document_type": self._doc_type(text),
            "company_name": self._company(text, entities),
            "period": self._period(text),
            "monetary_values": self._money_values(text),
            "key_metrics": self._key_metrics(text),
            "line_items": self._line_items(text),
        }

    def _doc_type(self, text: str) -> str:
        for dtype in ["Invoice", "Balance Sheet", "Income Statement", "Cash Flow",
                      "Annual Report", "Quarterly Report", "Profit & Loss", "Budget"]:
            if re.search(re.escape(dtype), text, re.IGNORECASE):
                return dtype
        return "Financial Document"

    def _company(self, text: str, entities: list) -> Optional[str]:
        orgs = [e for e in entities if e.label == "ORG"]
        return orgs[0].text if orgs else None

    def _period(self, text: str) -> Optional[str]:
        m = re.search(
            r'(?:for the|period|year|quarter)\s+(?:ended?|ending)?\s*'
            r'(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{4}|\d{4})',
            text, re.IGNORECASE
        )
        return m.group(0).strip() if m else None

    def _money_values(self, text: str) -> List[Dict[str, str]]:
        values = []
        pattern = r'([A-Za-z\s&,\(\)]+?)\s*[\$£€]?\s*([\d,]+(?:\.\d{2})?)\s*(?:USD|EUR|GBP|M|K|B)?'
        for m in re.finditer(pattern, text):
            label = m.group(1).strip()
            amount = m.group(2).replace(',', '')
            if label and amount and 3 < len(label) < 60:
                try:
                    float(amount)
                    values.append({"label": label, "amount": amount})
                except ValueError:
                    pass
        return values[:20]

    def _key_metrics(self, text: str) -> Dict[str, str]:
        metrics = {}
        patterns = {
            "revenue": r'(?:total\s+)?revenue[:\s]+[\$£€]?\s*([\d,\.]+)',
            "net_income": r'net\s+(?:income|profit|loss)[:\s]+[\$£€]?\s*([\d,\.]+)',
            "ebitda": r'ebitda[:\s]+[\$£€]?\s*([\d,\.]+)',
            "gross_profit": r'gross\s+profit[:\s]+[\$£€]?\s*([\d,\.]+)',
            "total_assets": r'total\s+assets[:\s]+[\$£€]?\s*([\d,\.]+)',
            "total_debt": r'total\s+(?:liabilities|debt)[:\s]+[\$£€]?\s*([\d,\.]+)',
        }
        for key, pattern in patterns.items():
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                metrics[key] = m.group(1).replace(',', '')
        return metrics

    def _line_items(self, text: str) -> List[Dict[str, str]]:
        """Extract table-like line items: description | amount."""
        items = []
        line_pattern = r'^([A-Za-z\s&\(\),\-]+?)\s{2,}([\$£€]?\s*[\d,\.]+)\s*$'
        for line in text.split('\n'):
            m = re.match(line_pattern, line.strip())
            if m:
                items.append({
                    "description": m.group(1).strip(),
                    "amount": m.group(2).strip()
                })
        return items[:30]


# ------------------------------------------------------------------ #
# Legal Parser
# ------------------------------------------------------------------ #

class LegalParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "document_type": self._doc_type(text),
            "parties": self._parties(text, entities),
            "dates": self._dates(text),
            "case_numbers": self._case_numbers(text),
            "key_clauses": self._clauses(text),
            "governing_law": self._governing_law(text),
        }

    def _doc_type(self, text: str) -> str:
        for dtype in ["Agreement", "Contract", "Affidavit", "Complaint", "Deposition",
                      "Motion", "Order", "Judgment", "Subpoena", "Will", "Trust"]:
            if re.search(r'\b' + re.escape(dtype) + r'\b', text, re.IGNORECASE):
                return dtype
        return "Legal Document"

    def _parties(self, text: str, entities: list) -> Dict[str, List[str]]:
        persons = list(set(e.text for e in entities if e.label == "PERSON"))
        orgs = list(set(e.text for e in entities if e.label == "ORG"))

        # Try to identify plaintiff/defendant
        plaintiff_m = re.search(r'(?:plaintiff|complainant)[:\s]+([A-Z][A-Za-z\s,\.]+?)(?:\n|,)', text)
        defendant_m = re.search(r'(?:defendant|respondent)[:\s]+([A-Z][A-Za-z\s,\.]+?)(?:\n|,)', text)

        return {
            "all_persons": persons[:10],
            "organizations": orgs[:10],
            "plaintiff": plaintiff_m.group(1).strip() if plaintiff_m else None,
            "defendant": defendant_m.group(1).strip() if defendant_m else None,
        }

    def _dates(self, text: str) -> List[str]:
        pattern = (
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\.?\s+\d{1,2},?\s+\d{4}'
            r'|\b\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}\b'
        )
        return list(set(re.findall(pattern, text, re.IGNORECASE)))[:10]

    def _case_numbers(self, text: str) -> List[str]:
        patterns = [
            r'\bCase\s+No\.?\s*[\w\-:]+',
            r'\bDocket\s+No\.?\s*[\w\-:]+',
            r'\b\d{1,2}[-:]\w{2,5}[-:]\d{4,6}\b',
        ]
        found = []
        for p in patterns:
            found.extend(re.findall(p, text, re.IGNORECASE))
        return list(set(found))[:5]

    def _clauses(self, text: str) -> List[str]:
        """Find section headings that represent key clauses."""
        pattern = r'\b(?:Section|Article|Clause|Paragraph)\s+\d+[\.:]?\s+([A-Z][A-Za-z\s]+)'
        return list(set(re.findall(pattern, text)))[:10]

    def _governing_law(self, text: str) -> Optional[str]:
        m = re.search(
            r'(?:governed by|laws of|jurisdiction of)\s+(?:the\s+)?([A-Z][a-zA-Z\s]+?)(?:\.|,|\n)',
            text, re.IGNORECASE
        )
        return m.group(1).strip() if m else None


# ------------------------------------------------------------------ #
# Medical Parser
# ------------------------------------------------------------------ #

class MedicalParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "document_type": self._doc_type(text),
            "patient_info": self._patient_info(text, entities),
            "diagnoses": self._diagnoses(text),
            "medications": self._medications(text),
            "procedures": self._procedures(text),
            "dates": self._dates(text),
            "provider": self._provider(text, entities),
        }

    def _doc_type(self, text: str) -> str:
        for dtype in ["Discharge Summary", "Progress Note", "Prescription",
                      "Lab Report", "Radiology Report", "Consultation", "Medical Record"]:
            if re.search(re.escape(dtype), text, re.IGNORECASE):
                return dtype
        return "Medical Document"

    def _patient_info(self, text: str, entities: list) -> Dict[str, Any]:
        persons = [e for e in entities if e.label == "PERSON"]
        name = persons[0].text if persons else None

        dob_m = re.search(r'(?:DOB|Date of Birth|Born)[:\s]+(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', text, re.IGNORECASE)
        age_m = re.search(r'\b(?:Age|aged?)[:\s]+(\d{1,3})\b', text, re.IGNORECASE)
        gender_m = re.search(r'\b(Male|Female|M|F)\b', text[:200])
        mrn_m = re.search(r'\b(?:MRN|Patient ID|Chart)[:\s#]?\s*(\w{4,12})\b', text, re.IGNORECASE)

        return {
            "name": name,
            "dob": dob_m.group(1) if dob_m else None,
            "age": age_m.group(1) if age_m else None,
            "gender": gender_m.group(1) if gender_m else None,
            "mrn": mrn_m.group(1) if mrn_m else None,
        }

    def _diagnoses(self, text: str) -> List[Dict[str, str]]:
        diag_section = find_section(text, ["diagnosis", "diagnoses", "assessment", "impression"])
        check = diag_section if diag_section else text

        diagnoses = []
        icd_pattern = r'([A-Z]\d{2}(?:\.\d{1,4})?)\s*[-:]?\s*([A-Za-z\s,\(\)\-]+?)(?:\n|;|$)'
        for m in re.finditer(icd_pattern, check, re.MULTILINE):
            diagnoses.append({
                "icd_code": m.group(1),
                "description": m.group(2).strip()[:100]
            })
        return diagnoses[:10]

    def _medications(self, text: str) -> List[Dict[str, str]]:
        med_section = find_section(text, ["medications", "prescriptions", "rx", "drugs", "medication list"])
        check = med_section if med_section else text

        meds = []
        # Drug + dosage pattern
        med_pattern = r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(\d+(?:\.\d+)?\s*mg|\d+\s*ml|\d+\s*mcg)[^\n]*'
        for m in re.finditer(med_pattern, check):
            meds.append({
                "drug": m.group(1).strip(),
                "dosage": m.group(2).strip(),
            })
        return meds[:15]

    def _procedures(self, text: str) -> List[str]:
        proc_section = find_section(text, ["procedures", "treatments", "interventions"])
        check = proc_section if proc_section else text

        cpt_pattern = r'(\d{5}(?:-\d{2})?)\s*[-:]?\s*([A-Za-z\s,\(\)\-]+?)(?:\n|;|$)'
        procs = []
        for m in re.finditer(cpt_pattern, check, re.MULTILINE):
            procs.append(f"{m.group(1)}: {m.group(2).strip()}")
        return procs[:10]

    def _dates(self, text: str) -> Dict[str, Optional[str]]:
        admit_m = re.search(r'(?:Admission|Admitted|Admit)\s+(?:Date)?[:\s]+(\S+)', text, re.IGNORECASE)
        discharge_m = re.search(r'(?:Discharge|Discharged)\s+(?:Date)?[:\s]+(\S+)', text, re.IGNORECASE)
        visit_m = re.search(r'(?:Visit|Encounter)\s+(?:Date)?[:\s]+(\S+)', text, re.IGNORECASE)
        return {
            "admission": admit_m.group(1) if admit_m else None,
            "discharge": discharge_m.group(1) if discharge_m else None,
            "visit": visit_m.group(1) if visit_m else None,
        }

    def _provider(self, text: str, entities: list) -> Optional[str]:
        provider_m = re.search(r'(?:Dr\.?|Doctor|Physician|Provider)[:\s]+([A-Z][a-zA-Z\s\.]+?)(?:\n|,|MD|DO)', text)
        if provider_m:
            return provider_m.group(1).strip()
        persons = [e for e in entities if e.label == "PERSON"]
        return persons[-1].text if persons else None


# ------------------------------------------------------------------ #
# Invoice Parser
# ------------------------------------------------------------------ #

class InvoiceParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "invoice_number": self._invoice_num(text),
            "vendor": self._vendor(text, entities),
            "bill_to": self._bill_to(text, entities),
            "invoice_date": self._date(text, "invoice"),
            "due_date": self._date(text, "due"),
            "line_items": self._line_items(text),
            "totals": self._totals(text),
            "payment_terms": self._payment_terms(text),
        }

    def _invoice_num(self, text: str) -> Optional[str]:
        m = re.search(r'(?:Invoice|INV|Bill)\s*(?:No\.?|#|Number)?[:\s]+([A-Z0-9\-]+)', text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _vendor(self, text: str, entities: list) -> Optional[str]:
        m = re.search(r'(?:From|Vendor|Seller|Company)[:\s]+([A-Za-z\s&\.,]+?)(?:\n|Email|Tel|Phone)', text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        orgs = [e for e in entities if e.label == "ORG"]
        return orgs[0].text if orgs else None

    def _bill_to(self, text: str, entities: list) -> Optional[str]:
        m = re.search(r'(?:Bill To|Billed To|To)[:\s]+([A-Za-z\s&\.,]+?)(?:\n)', text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _date(self, text: str, dtype: str) -> Optional[str]:
        patterns = {
            "invoice": r'(?:Invoice|Bill)\s*Date[:\s]+(\S+)',
            "due": r'(?:Due|Payment)\s*Date[:\s]+(\S+)',
        }
        m = re.search(patterns.get(dtype, ""), text, re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _line_items(self, text: str) -> List[Dict[str, Any]]:
        items = []
        pattern = r'^(.{5,50}?)\s{2,}(\d+(?:\.\d+)?)\s{2,}[\$£€]?\s*([\d,\.]+)\s{2,}[\$£€]?\s*([\d,\.]+)\s*$'
        for line in text.split('\n'):
            m = re.match(pattern, line.strip())
            if m:
                items.append({
                    "description": m.group(1).strip(),
                    "quantity": m.group(2),
                    "unit_price": m.group(3),
                    "total": m.group(4),
                })
        return items[:25]

    def _totals(self, text: str) -> Dict[str, Optional[str]]:
        def find_amount(label: str) -> Optional[str]:
            m = re.search(label + r'[:\s]+[\$£€]?\s*([\d,\.]+)', text, re.IGNORECASE)
            return m.group(1).replace(',', '') if m else None

        return {
            "subtotal": find_amount(r'subtotal'),
            "tax": find_amount(r'(?:tax|vat|gst)'),
            "discount": find_amount(r'discount'),
            "total": find_amount(r'(?:total|amount due|total due)'),
        }

    def _payment_terms(self, text: str) -> Optional[str]:
        m = re.search(r'(?:Payment\s+Terms?|Terms?)[:\s]+(.{5,60}?)(?:\n|$)', text, re.IGNORECASE)
        return m.group(1).strip() if m else None


# ------------------------------------------------------------------ #
# Research Parser
# ------------------------------------------------------------------ #

class ResearchParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "title": self._title(text),
            "authors": self._authors(text, entities),
            "abstract": self._abstract(text),
            "keywords": self._keywords(text),
            "sections": self._sections(text),
            "references_count": self._ref_count(text),
            "doi": self._doi(text),
            "publication": self._publication(text),
        }

    def _title(self, text: str) -> Optional[str]:
        # Usually first substantial line
        for line in text.split('\n')[:10]:
            line = line.strip()
            if 20 < len(line) < 200 and not line.lower().startswith(("abstract", "doi", "http")):
                return line
        return None

    def _authors(self, text: str, entities: list) -> List[str]:
        persons = [e.text for e in entities if e.label == "PERSON"]
        # Also look for "Author(s):" pattern
        m = re.search(r'(?:Authors?|By)[:\s]+([A-Za-z\s,\.]+?)(?:\n|Abstract|Keywords)', text, re.IGNORECASE)
        if m:
            authors = [a.strip() for a in m.group(1).split(',')]
            return authors[:10]
        return persons[:5]

    def _abstract(self, text: str) -> Optional[str]:
        section = find_section(text, ["abstract"], ["keywords", "introduction", "1\.", "background"])
        return section[:800] if section else None

    def _keywords(self, text: str) -> List[str]:
        m = re.search(r'(?:Keywords?|Index Terms?)[:\s]+(.+?)(?:\n\n|\n[A-Z])', text, re.IGNORECASE | re.DOTALL)
        if m:
            raw = m.group(1).replace('\n', ' ')
            keywords = re.split(r'[;,·•]', raw)
            return [k.strip() for k in keywords if 2 < len(k.strip()) < 50][:15]
        return []

    def _sections(self, text: str) -> List[str]:
        # Numbered or titled sections
        sections = re.findall(r'(?:^|\n)(?:\d+\.?\s+)?([A-Z][A-Za-z\s&]+)(?:\n)', text)
        known = {"Introduction", "Methodology", "Methods", "Results", "Discussion",
                 "Conclusion", "Related Work", "Background", "Evaluation", "Experiments"}
        return [s.strip() for s in sections if s.strip() in known]

    def _ref_count(self, text: str) -> int:
        refs = re.findall(r'\[\d+\]', text)
        return len(set(refs))

    def _doi(self, text: str) -> Optional[str]:
        m = re.search(r'doi[:\s]+10\.\d{4,}/\S+', text, re.IGNORECASE)
        return m.group(0).strip() if m else None

    def _publication(self, text: str) -> Optional[str]:
        m = re.search(
            r'(?:published in|proceedings of|journal of|conference on)\s+([A-Za-z\s&\-]+?)(?:\n|,|\d)',
            text, re.IGNORECASE
        )
        return m.group(1).strip() if m else None


# ------------------------------------------------------------------ #
# General Parser (fallback)
# ------------------------------------------------------------------ #

class GeneralParser:

    def parse(self, text: str, entities: list) -> Dict[str, Any]:
        return {
            "persons": list(set(e.text for e in entities if e.label == "PERSON")),
            "organizations": list(set(e.text for e in entities if e.label == "ORG")),
            "locations": list(set(e.text for e in entities if e.label == "LOCATION")),
            "dates": list(set(e.text for e in entities if e.label == "DATE")),
            "emails": list(set(e.text for e in entities if e.label == "EMAIL")),
            "phones": list(set(e.text for e in entities if e.label == "PHONE")),
            "money": list(set(e.text for e in entities if e.label == "MONEY")),
            "percentages": list(set(e.text for e in entities if e.label == "PERCENTAGE")),
            "text_preview": text[:500],
        }


# ------------------------------------------------------------------ #
# Parser registry
# ------------------------------------------------------------------ #

DOMAIN_PARSERS = {
    "resume": ResumeParser,
    "finance": FinanceParser,
    "legal": LegalParser,
    "medical": MedicalParser,
    "invoice": InvoiceParser,
    "research": ResearchParser,
    "general": GeneralParser,
}


def get_parser(domain: str):
    cls = DOMAIN_PARSERS.get(domain, GeneralParser)
    return cls()