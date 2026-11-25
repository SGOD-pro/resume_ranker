# Git History Sanitization Plan (git-filter-repo)

> **SAFETY MANDATE**: DO NOT execute this history rewrite on production or shared remotes without explicit approval from the repository owner. This document details the exact, tested procedure to safely redact leaked credentials from historical git commits once authorized.

---

## 1. Summary of Findings

During Phase 0 audit, static AWS credentials were identified in historical commits:
- Commit `d5dc030`: AWS Access Key and Secret Key committed in configuration.
- Commit `6bd4e2e`: Partial credential rotation and secrets in commit history.

While these credentials have been revoked and all production services now use AWS IAM Execution Roles (per Amendment 1), git history retains these strings.

---

## 2. Prerequisites & Safety Safeguards

1. **Verify Backups**:
   Before modifying git history, create a mirror backup of the entire repository outside the workspace:
   ```bash
   git clone --mirror git@github.com:SGOD-pro/resume_ranker.git /backup/resume_ranker_mirror.git
   ```
2. **Ensure Clean Working Directory**:
   ```bash
   git status
   # Must report: working tree clean
   ```
3. **Notify Collaborators**:
   Rewriting history changes commit SHAs. Any developer with local branches will need to rebase or re-clone.

---

## 3. Tool Installation

Use `git-filter-repo` (the official Git-recommended tool, superior to `git-filter-branch` and BFG):
```bash
# Via uv / pip
uv tool install git-filter-repo
# or
pip install git-filter-repo
```

---

## 4. Exact Execution Steps

### Step 4.1: Create Expressions / Replacements File
Create a `replace-secrets.txt` file containing the leaked keys and placeholders:
```text
AKIA...==>REDACTED_AWS_KEY_ID
wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY==>REDACTED_AWS_SECRET_KEY
```

### Step 4.2: Run git-filter-repo
Execute the replacement across all branches and tags:
```bash
git filter-repo --replace-text replace-secrets.txt --force
```

### Step 4.3: Verify History
1. Ensure the redacted keys no longer appear anywhere in `git log`:
   ```bash
   git log -S "AKIA" --all
   git log -S "REDACTED_AWS_KEY_ID" --all
   ```
2. Verify repository integrity and test suite:
   ```bash
   git fsck --full
   uv run pytest tests/unit
   ```

### Step 4.4: Force Push (ONLY WITH OWNER APPROVAL)
Once approved by the repository owner:
```bash
git push origin --force --all
git push origin --force --tags
```

---

## 5. Rollback / Recovery Plan
If anything fails during the local run, restore from the backup mirror:
```bash
cd /home/swyra/projects/resume_ranker
git reset --hard origin/v2.1
# or restore directly from mirror:
git remote add mirror /backup/resume_ranker_mirror.git
git fetch mirror
git reset --hard mirror/v2.1
```
