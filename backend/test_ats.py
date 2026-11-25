import json
from src.ats.b2b_ats_scorer import B2BAtsScorer

pdfs = [
    ("/mnt/d/WORK/resume_ranker/data/resumes/Zoe_Thompson_Design.pdf", "Zoe Thompson"),
    ("/mnt/d/WORK/resume_ranker/data/resumes/Elijah_Brown_Video.pdf", "Elijah Brown")
]

scorer = B2BAtsScorer()

for path, name in pdfs:
    print(f"\n--- {name} ---")
    try:
        # Note: B2BAtsScorer.score expects pdf_path, s3_bucket, s3_key
        # Wait, the parser inside uses ODL. ODL requires s3 upload if we're in lambda, but wait, b2b_ats_scorer does: 
        # parser.parse_pdf(pdf_path, doc_id="ats_check", s3_bucket=s3_bucket, s3_key=s3_key)
        # Since I'm running locally, I can just pass None for s3_bucket and s3_key if the environment is dev.
        # But wait, earlier we found out ODL lambda requires s3 upload.
        # However, there's a local mode for extraction that doesn't use ODL if environment is not prod.
        # Let's just run it!
        res = scorer.score(path, "dummy-bucket", "dummy-key")
        print("Score:", res["score"])
        print("Breakdown:", json.dumps(res["breakdown"], indent=2))
        print("Missed Sections:", res["section_detection"]["missed"])
        print("Date Chronology:", res["date_consistency"])
        print("Skills:", res["keyword_preview"])
    except Exception as e:
        print("ERROR:", str(e))
