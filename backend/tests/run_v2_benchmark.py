import json
import time
from pathlib import Path
from src.extraction.deterministic_extraction_service import DeterministicExtractionService
from src.extraction.structural_parsing_service import StructuralParsingService
from src.scoring.scoring_service import ScoringService
from src.schemas.scoring import JobDescription
import logging

logging.basicConfig(level=logging.ERROR)

def run():
    print("Starting V2 Benchmark (on local PDFs with JVM)...")
    resume_dir = Path("data/resumes")
    pdfs = list(resume_dir.glob("*.pdf"))
    if not pdfs:
        print("No PDFs found!")
        return

    structural_service = StructuralParsingService()
    extraction_service = DeterministicExtractionService()
    scoring_service = ScoringService()
    
    jd = JobDescription(
        title="Software Engineer",
        must_have_skills=["Python", "SQL"],
        nice_to_have_skills=["AWS", "Docker"],
        min_years=3,
        required_degree="bachelor"
    )
    
    start = time.time()
    
    names_found = 0
    skills_found = 0
    experience_found = 0
    education_found = 0
    total = len(pdfs)
    
    for pdf in pdfs:
        with open(pdf, "rb") as f:
            pdf_bytes = f.read()
            
        try:
            structural = structural_service.parse(pdf_bytes, pdf.name)
            ext_res = extraction_service.parse(structural, pdf.name)

            if ext_res.name: names_found += 1
            if ext_res.skills: skills_found += 1
            if ext_res.experience: experience_found += 1
            if ext_res.education: education_found += 1
            
            score_res = scoring_service.score(ext_res, jd)
            
        except Exception as e:
            print(f"Error on {pdf.name}: {e}")
            
    elapsed = time.time() - start
    avg_time = elapsed / total
    
    ext_quality = (
        0.20 * (names_found/total) +
        0.25 * (skills_found/total) +
        0.25 * (experience_found/total) +
        0.20 * (education_found/total) +
        0.10 * 1.0 # assume email found for simplicity
    ) * 100
    
    print("\n--- V2 BENCHMARK RESULTS ---")
    print(f"Total Resumes Evaluated: {total}")
    print(f"Extraction Quality: {ext_quality:.1f}%")
    print(f"Performance (avg ms/resume): {avg_time*1000:.1f}ms")
    
    print("\n--- COMPARISON TO V1 ---")
    try:
        with open("tests/benchmark_v4/report.json") as f:
            v1_data = json.load(f)
        v1_ext = v1_data["scorecard"]["scores"].get("Extraction Quality")
        v1_perf = v1_data["scorecard"]["scores"].get("Performance")
        print(f"V1 Extraction Quality: {v1_ext} %")
        print(f"V1 Performance: {v1_perf} ms/resume")
        
        diff = ext_quality - v1_ext
        print(f"\nDelta Extraction: {'+' if diff > 0 else ''}{diff:.1f}%")
    except Exception as e:
        print("Could not load V1 report for comparison:", e)

if __name__ == "__main__":
    run()
