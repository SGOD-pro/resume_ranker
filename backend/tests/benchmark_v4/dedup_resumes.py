#!/usr/bin/env python3
"""SHA256 dedup of benchmark resumes. Removes exact duplicate PDFs."""

import hashlib
import os
import sys
from pathlib import Path
from collections import defaultdict

RESUME_DIR = Path(__file__).parent / "resumes"

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    pdfs = sorted(RESUME_DIR.glob("*.pdf"))
    print(f"Total PDFs before dedup: {len(pdfs)}")

    hash_to_files = defaultdict(list)
    for pdf in pdfs:
        h = sha256_file(pdf)
        hash_to_files[h].append(pdf)

    unique = 0
    duplicate_count = 0
    removed_files = []

    for h, files in hash_to_files.items():
        unique += 1
        if len(files) > 1:
            # Keep the first (lowest numbered), remove the rest
            files_sorted = sorted(files, key=lambda p: p.name)
            keep = files_sorted[0]
            for dup in files_sorted[1:]:
                removed_files.append(dup.name)
                dup.unlink()
                duplicate_count += 1

    remaining = len(list(RESUME_DIR.glob("*.pdf")))
    print(f"Unique hashes: {unique}")
    print(f"Duplicates removed: {duplicate_count}")
    print(f"PDFs remaining: {remaining}")

    if removed_files:
        print(f"\nFirst 20 removed:")
        for f in removed_files[:20]:
            print(f"  - {f}")
        if len(removed_files) > 20:
            print(f"  ... and {len(removed_files) - 20} more")

if __name__ == "__main__":
    main()
