"""
debug_scoring.py — Quick diagnostic: extract + score a few resumes
===================================================================
Usage: python debug_scoring.py
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from src.services.extraction_service import ExtractionService
from src.ranking.scorer import CandidateScorer
from src.schemas.scoring import JobDescription
from src.registries.skill_registry import find_matches, match as skill_match, normalize

# ── Test config ───────────────────────────────────────────────────────────────
RESUME_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'test', 'resumes')

# Just test a few
TEST_FILES = ['souvik.pdf', '1.pdf', '2.pdf', '3.pdf']
JD_MUST_HAVE = ['React', 'Node', 'Python', 'JS', 'Docker']
JD_NICE_HAVE = ['Redis', 'AWS', 'K8S']

def main():
    svc = ExtractionService()
    
    print("=" * 80)
    print("DEBUGGING SKILL EXTRACTION & MATCHING")
    print("=" * 80)
    print(f"JD must_have_skills: {JD_MUST_HAVE}")
    print(f"Normalized JD skills: {[normalize(s) for s in JD_MUST_HAVE]}")
    print()

    for fname in TEST_FILES:
        pdf_path = os.path.join(RESUME_DIR, fname)
        if not os.path.exists(pdf_path):
            print(f"⚠ {fname} not found at {pdf_path}")
            continue
        
        print(f"\n{'─' * 80}")
        print(f"📄 RESUME: {fname}")
        print(f"{'─' * 80}")
        
        try:
            result = svc.extract_single(pdf_path)
            fields = json.loads(json.dumps(
                result.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
            ))
        except Exception as e:
            print(f"  ❌ Extraction failed: {e}")
            continue
        
        # Show extracted skills
        skills = fields.get('skills', [])
        print(f"  NAME: {fields.get('personal_info', {}).get('name', 'Unknown')}")
        print(f"  EXTRACTED SKILLS ({len(skills)}):")
        for s in sorted(skills):
            print(f"    - {s}  (normalized: {normalize(s)})")
        
        # Test matching
        matched, missing = find_matches(skills, JD_MUST_HAVE)
        print(f"\n  MUST-HAVE MATCHING:")
        print(f"    ✅ Matched: {matched}")
        print(f"    ❌ Missing: {missing}")
        
        # Detailed per-skill debug
        print(f"\n  PER-SKILL DETAIL:")
        for jd_sk in JD_MUST_HAVE:
            for c_sk in skills:
                if skill_match(c_sk, jd_sk):
                    print(f"    '{jd_sk}' ← matched by '{c_sk}' (norm: {normalize(c_sk)} vs {normalize(jd_sk)})")
                    break
            else:
                print(f"    '{jd_sk}' ← NOT MATCHED by any extracted skill")
                # Show closest normalized candidates
                jd_norm = normalize(jd_sk)
                for c_sk in skills:
                    c_norm = normalize(c_sk)
                    if jd_norm in c_norm or c_norm in jd_norm:
                        print(f"      ⚠ NEAR MISS: '{c_sk}' (norm: {c_norm}) vs '{jd_sk}' (norm: {jd_norm})")
        
        # Show raw_text_sections keys
        raw_sections = fields.get('raw_text_sections', {})
        print(f"\n  RAW TEXT SECTIONS: {list(raw_sections.keys())}")
        
        # Show experience entries
        experience = fields.get('experience', [])
        print(f"  EXPERIENCE ENTRIES: {len(experience)}")
        for i, exp in enumerate(experience[:3]):
            desc = (exp.get('description') or '')[:100]
            print(f"    [{i}] {exp.get('role', 'N/A')} @ {exp.get('company', 'N/A')}: {desc}...")

    # Now score them all
    print(f"\n\n{'=' * 80}")
    print("FULL SCORING RUN")
    print(f"{'=' * 80}")
    
    all_candidates = []
    for fname in TEST_FILES:
        pdf_path = os.path.join(RESUME_DIR, fname)
        if not os.path.exists(pdf_path):
            continue
        try:
            result = svc.extract_single(pdf_path)
            fields = json.loads(json.dumps(
                result.fields,
                default=lambda o: o.__dict__ if hasattr(o, '__dict__') else str(o)
            ))
            fields['_document_id'] = result.document_id
            if 'extraction_quality' not in fields:
                fields['extraction_quality'] = 0.0
            all_candidates.append(fields)
        except Exception as e:
            print(f"  ❌ {fname}: {e}")
    
    jd = JobDescription(
        title='Full Stack Developer',
        department='Engineering',
        description='need a full stack developer who knows backend and front-end both',
        must_have_skills=JD_MUST_HAVE,
        nice_to_have_skills=JD_NICE_HAVE,
        min_years=0,
        max_years=10,
        education_level='bachelor',
        education_field='CS / related',
        keywords=[],
        weights={'skills': 0.40, 'experience': 0.25, 'keywords': 0.20, 'education': 0.15},
    )
    
    scorer = CandidateScorer()
    results = scorer.rank(jd, all_candidates)
    
    for r in results:
        ko_str = '❌ KO' if r.knocked_out else '✅'
        print(f"\n  {ko_str} {r.name:30s} score={r.final_score:5.1f}")
        print(f"      skill_score={r.skill_score:.1f} exp_score={r.experience_score:.1f} kw_score={r.keyword_score:.1f} edu_score={r.education_score:.1f}")
        print(f"      matched_must_have={r.matched_must_have}")
        print(f"      missing_must_have={r.missing_must_have}")
        if r.knockout_reasons:
            for kr in r.knockout_reasons:
                print(f"      ⛔ {kr}")


if __name__ == '__main__':
    main()
