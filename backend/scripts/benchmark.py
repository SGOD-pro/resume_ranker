"""
benchmark.py — Capture extraction benchmark for all resumes.
Outputs JSON with per-resume field counts for regression testing.
"""
import json, glob, os, sys
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.pipeline import PDFPipelineV3
from src.config.settings import RESUME_DIR, BASELINES_DIR


def capture():
    pipe = PDFPipelineV3()
    results = {}
    for pdf in sorted(glob.glob(str(RESUME_DIR / '*.pdf'))):
        name = os.path.splitext(os.path.basename(pdf))[0]
        print(f"  {name}...", end=' ', flush=True)
        r = pipe.extract(pdf)
        f = r.fields
        pi = f.get('personal_info', {})
        results[name] = {
            "name": pi.get('name'),
            "email": pi.get('email'),
            "phone": pi.get('phone'),
            "location": pi.get('location'),
            "has_summary": bool(f.get('summary')),
            "exp_count": len(f.get('experience', [])),
            "edu_count": len(f.get('education', [])),
            "skills_count": len(f.get('skills', [])),
            "cert_count": len(f.get('certifications', [])),
            "project_count": len(f.get('projects', [])),
            "lang_count": len(f.get('languages', [])),
        }
        print("✓")
    return results

if __name__ == '__main__':
    default_output = str(BASELINES_DIR / 'benchmark_output.json')
    output_file = sys.argv[1] if len(sys.argv) > 1 else default_output
    results = capture()
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {output_file}")

    # Print summary metrics
    total = len(results)
    summary_ok = sum(1 for r in results.values() if r['has_summary'])
    exp_ok = sum(1 for r in results.values() if r['exp_count'] > 0)
    edu_ok = sum(1 for r in results.values() if r['edu_count'] > 0)
    skills_ok = sum(1 for r in results.values() if r['skills_count'] > 0)
    cert_ok = sum(1 for r in results.values() if r['cert_count'] > 0)
    contact_fields = sum(
        sum(1 for k in ['name','email','phone','location'] if r.get(k))
        for r in results.values()
    )
    print(f"\n  Summary:        {summary_ok}/{total} ({summary_ok/total*100:.0f}%)")
    print(f"  Experience:     {exp_ok}/{total} ({exp_ok/total*100:.0f}%)")
    print(f"  Education:      {edu_ok}/{total} ({edu_ok/total*100:.0f}%)")
    print(f"  Skills:         {skills_ok}/{total} ({skills_ok/total*100:.0f}%)")
    print(f"  Certifications: {cert_ok}/{total} ({cert_ok/total*100:.0f}%)")
    print(f"  Contact:        {contact_fields}/{total*4} ({contact_fields/(total*4)*100:.0f}%)")
