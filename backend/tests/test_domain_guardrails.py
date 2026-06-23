"""
V9 Guardrail tests — Domain classifier regression tests.

These tests must FAIL if domain dictionaries regress in future.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ranking.domain_classifier import DomainClassifier


def test_civil_engineer_not_healthcare():
    """Civil engineer with AutoCAD + STAAD must not classify as healthcare."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['AutoCAD', 'STAAD', 'Civil Engineering', 'Surveying', 'Revit'],
        'experience': [{'role': 'Senior Engineer - Quantity Surveying', 'description': 'construction infrastructure'}],
        'education': [{'degree': 'Diploma in Civil Engineering'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'engineering', f"Expected engineering, got {domain}"
    assert subdomain == 'civil', f"Expected civil subdomain, got {subdomain}"
    assert domain != 'healthcare', "Civil engineer classified as healthcare!"


def test_mechanical_engineer_not_healthcare():
    """Mechanical engineer with SolidWorks + CATIA must not classify as healthcare."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['SolidWorks', 'CATIA', 'AutoCAD', 'Manufacturing', 'Mechanical Engineering'],
        'experience': [{'role': 'Design Engineer', 'description': 'mechanical design manufacturing'}],
        'education': [{'degree': 'Diploma in Mechanical Engineering'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'engineering', f"Expected engineering, got {domain}"
    assert subdomain == 'mechanical', f"Expected mechanical subdomain, got {subdomain}"
    assert domain != 'healthcare', "Mechanical engineer classified as healthcare!"


def test_electrical_engineer_not_healthcare():
    """Electrical engineer with B.Tech EEE must not classify as healthcare."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['MATLAB', 'Cable Installation', 'Linux', 'Robotics'],
        'experience': [{'role': 'SITE ELECTRICAL ENGINEER', 'description': 'electrical systems'}],
        'education': [{'degree': 'B.TECH (Electrical and Electronics Engineering)'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'engineering', f"Expected engineering, got {domain}"
    assert domain != 'healthcare', "Electrical engineer classified as healthcare!"


def test_nurse_classifies_healthcare():
    """Nurse with ICU + GNM must classify as healthcare."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['CPR', 'Patient Care', 'Nursing', 'HIPAA'],
        'experience': [{'role': 'Staff Nurse', 'description': 'ICU ward patient care hospital'}],
        'education': [{'degree': 'GNM Nursing'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'healthcare', f"Expected healthcare, got {domain}"


def test_mbbs_classifies_healthcare():
    """MBBS candidate must classify as healthcare."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['Clinical Assessment', 'Patient Care'],
        'experience': [{'role': 'Physician', 'description': 'hospital clinical diagnosis treatment'}],
        'education': [{'degree': 'MBBS'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'healthcare', f"Expected healthcare, got {domain}"


def test_engineer_with_generic_terms_still_engineering():
    """Engineer with Compliance, Monitoring, Organization must stay engineering."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['AutoCAD', 'Compliance', 'Monitoring', 'Quality Control', 'Manufacturing', 'Assembly', 'HVAC'],
        'experience': [{'role': 'Production Engineer', 'description': 'Bajaj Auto manufacturing'}],
        'education': [{'degree': 'B.Tech Mechanical Engineering'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'engineering', f"Expected engineering, got {domain}"


def test_procurement_engineer_not_legal():
    """Procurement engineer with contract terms must not classify as legal."""
    dc = DomainClassifier()
    candidate = {
        'skills': ['AutoCAD', 'Manufacturing', 'Dispute Resolution', 'Cost Estimation', 'CAD', 'Mechanical Engineering'],
        'experience': [{'role': 'Procurement & Contracts Engineer (Mechanical)', 'description': 'Metro projects'}],
        'education': [{'degree': 'Bachelor of Technology'}],
    }
    domain, subdomain, conf = dc.classify_with_subdomain(candidate)
    assert domain == 'engineering', f"Expected engineering, got {domain}"
    assert domain != 'legal', "Procurement engineer classified as legal!"


if __name__ == '__main__':
    tests = [
        test_civil_engineer_not_healthcare,
        test_mechanical_engineer_not_healthcare,
        test_electrical_engineer_not_healthcare,
        test_nurse_classifies_healthcare,
        test_mbbs_classifies_healthcare,
        test_engineer_with_generic_terms_still_engineering,
        test_procurement_engineer_not_legal,
    ]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__doc__.strip()}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {test.__doc__.strip()} — {e}")
            failed += 1

    print(f"\n  Results: {passed}/{passed + failed} passed")
    if failed:
        sys.exit(1)
