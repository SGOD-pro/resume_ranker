# Pre-Deletion Safety Check Protocol

This protocol defines the mandatory 5-step verification process that MUST be executed before deleting any legacy, unused, or superseded code in the repository.

---

## 1. Safety Check Checklist

Before deleting any file or symbol:

- [ ] **Check 1: Grep CloudFormation / SAM Infrastructure**
  ```bash
  grep -rn "<target_symbol_or_path>" backend/deploy/template.yaml infra/ template.yaml
  ```
  Ensure the resource, handler, layer, or parameter is not referenced by any AWS SAM or CloudFormation template.

- [ ] **Check 2: Grep CI/CD and GitHub Workflows**
  ```bash
  grep -rn "<target_symbol_or_path>" .github/
  ```
  Ensure GitHub Actions workflows, linting steps, test scripts, or deployment pipelines do not reference the target.

- [ ] **Check 3: Dynamic Import and Reflection Inspection**
  ```bash
  grep -rn "importlib\|getattr\|__import__" backend/src/
  grep -rn "<target_module_basename>" backend/src/ frontend/src/
  ```
  Ensure no plugins, dependency injection, lazy loaders, or dynamic string lookups reference the target.

- [ ] **Check 4: Run Isolated Test Suite**
  Run all regression and unit tests before and after staging the deletion:
  ```bash
  uv run pytest backend/tests/unit
  ```

- [ ] **Check 5: Create Revert Commit Anchor**
  Before applying file removals, record the clean pre-deletion commit SHA:
  ```bash
  PRE_DELETE_SHA=$(git rev-parse HEAD)
  echo "Revert anchor: ${PRE_DELETE_SHA}"
  ```
  If any regressions or hidden dependencies surface later, execute:
  ```bash
  git revert <deletion_commit_sha>
  # or
  git checkout ${PRE_DELETE_SHA} -- <specific_file_path>
  ```
