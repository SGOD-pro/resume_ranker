"""
extraction_audit.py — Deep extraction accuracy audit
=====================================================
Runs the full pipeline on every resume and produces a detailed report
showing what was extracted vs what's missing, with specific attention to:
  - Experience entries (role, company, dates)
  - Education entries (degree, institution)
  - Projects
  - Name extraction
  - Section detection accuracy
"""

import json
import glob
import os
import sys
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).resolve().parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR


def audit_all():
    pipe = PDFPipelineV3()
    pdfs = sorted(glob.glob(str(RESUME_DIR / '*.pdf')))

    audit = {}
    issues = {
        "no_experience": [],
        "low_experience": [],  # exp_count < 2 (suspicious)
        "no_education": [],
        "no_projects": [],
        "no_name": [],
        "no_email": [],
        "no_sections_found": [],
        "bad_location": [],   # location looks like a skill list
        "low_skills": [],     # < 5 skills
    }

    print(f"\n{'='*90}")
    print(f"  EXTRACTION ACCURACY AUDIT — {len(pdfs)} PDFs")
    print(f"{'='*90}\n")

    for pdf in pdfs:
        filename = os.path.basename(pdf)
        stem = Path(filename).stem
        print(f"  Processing {filename}...", end=" ", flush=True)

        try:
            r = pipe.extract(pdf)
            fields = json.loads(json.dumps(
                r.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o),
            ))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            audit[stem] = {"error": str(e)}
            continue

        pi = fields.get('personal_info', {}) or {}
        name = pi.get('name')
        email = pi.get('email')
        phone = pi.get('phone')
        location = pi.get('location')
        summary = fields.get('summary')
        skills = fields.get('skills', [])
        experience = fields.get('experience', [])
        education = fields.get('education', [])
        projects = fields.get('projects', [])
        certs = fields.get('certifications', [])
        langs = fields.get('languages', [])

        entry = {
            "name": name,
            "email": email,
            "phone": phone,
            "location": location,
            "has_summary": bool(summary),
            "summary_len": len(summary) if summary else 0,
            "skills_count": len(skills),
            "skills_sample": skills[:8],
            "exp_count": len(experience),
            "experience_details": [],
            "edu_count": len(education),
            "education_details": [],
            "project_count": len(projects),
            "project_details": [],
            "cert_count": len(certs),
            "lang_count": len(langs),
            "layout_type": r.layout_type,
            "page_count": r.page_count,
            "sections_found": r.metadata.get("sections_found", []),
            "sections_missing": r.metadata.get("sections_missing", []),
            "section_sources": r.metadata.get("section_sources", {}),
            "fallback_used": r.metadata.get("fallback_detector_used", False),
            "warnings": r.warnings,
            "extraction_quality": fields.get('extraction_quality', 0),
        }

        # Experience details
        for exp in experience:
            entry["experience_details"].append({
                "role": exp.get("role"),
                "company": exp.get("company"),
                "start": exp.get("start"),
                "end": exp.get("end"),
                "has_description": bool(exp.get("description")),
                "desc_len": len(exp.get("description", "") or ""),
            })

        # Education details
        for edu in education:
            entry["education_details"].append({
                "degree": edu.get("degree"),
                "institution": edu.get("institution"),
                "start": edu.get("start"),
                "end": edu.get("end"),
            })

        # Project details
        for proj in projects:
            entry["project_details"].append({
                "name": proj.get("name"),
                "has_description": bool(proj.get("description")),
                "tech_count": len(proj.get("technologies", []) or []),
                "has_link": bool(proj.get("link") or proj.get("url")),
            })

        audit[stem] = entry

        # Track issues
        if len(experience) == 0:
            issues["no_experience"].append(stem)
        elif len(experience) < 2:
            issues["low_experience"].append(stem)
        if len(education) == 0:
            issues["no_education"].append(stem)
        if len(projects) == 0:
            issues["no_projects"].append(stem)
        if not name:
            issues["no_name"].append(stem)
        if not email:
            issues["no_email"].append(stem)
        if not entry["sections_found"]:
            issues["no_sections_found"].append(stem)
        if location and any(kw in location.lower() for kw in
                           ['python', 'java', 'react', 'photoshop', 'illustrator',
                            'html', 'css', 'javascript', 'node']):
            issues["bad_location"].append(f"{stem}: '{location}'")
        if len(skills) < 5:
            issues["low_skills"].append(f"{stem}: {len(skills)} skills")

        status = "✓" if len(experience) > 0 and len(education) > 0 and name else "⚠"
        print(f"{status}  {name or '???'} | exp:{len(experience)} edu:{len(education)} "
              f"proj:{len(projects)} skills:{len(skills)}")

    # Print summary
    print(f"\n{'='*90}")
    print(f"  ISSUE SUMMARY")
    print(f"{'='*90}")
    total = len(audit)
    for category, items in issues.items():
        pct = len(items) / total * 100 if total else 0
        icon = "🔴" if pct > 30 else ("🟡" if pct > 10 else "🟢")
        print(f"\n  {icon} {category}: {len(items)}/{total} ({pct:.0f}%)")
        for item in items:
            print(f"      - {item}")

    # Write detailed audit
    output_path = Path(PROJECT_ROOT) / "benchmarks" / "outputs" / "extraction_accuracy_audit.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(audit, f, indent=2, default=str)
    print(f"\n  📄 Detailed audit saved to: {output_path}")

    # Write issue summary
    summary_path = Path(PROJECT_ROOT) / "benchmarks" / "outputs" / "extraction_issues.json"
    with open(summary_path, 'w') as f:
        json.dump(issues, f, indent=2)
    print(f"  📄 Issue summary saved to: {summary_path}")

    print(f"\n{'='*90}\n")
    return audit, issues


if __name__ == '__main__':
    audit_all()
