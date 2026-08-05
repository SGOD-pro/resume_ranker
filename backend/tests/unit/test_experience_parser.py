import pytest
import re
from src.extractors.experience.experience_parser import DATE_RANGE_RE

def test_date_range_re_negative_lookarounds():
    # Negative test cases: shouldn't match phone numbers or zip code blocks
    
    # Telephone with spaces/dashes
    assert not DATE_RANGE_RE.search("555 - 1234")
    assert not DATE_RANGE_RE.search("1234 - 5678")
    assert not DATE_RANGE_RE.search("98765-43210")
    assert not DATE_RANGE_RE.search("5555 - 1234")
    assert not DATE_RANGE_RE.search("555-1234")
    
    # Long digits (e.g., 10-digit phone)
    assert not DATE_RANGE_RE.search("1234567890")
    
    # Should still match valid date ranges
    assert DATE_RANGE_RE.search("2015 - 2020")
    assert DATE_RANGE_RE.search("2015 - Present")
    assert DATE_RANGE_RE.search("Jan 2019 to Current")
    assert DATE_RANGE_RE.search("1 9 9 9 - 2 0 0 1")
    assert DATE_RANGE_RE.search("02/2015 - 08/2020")
