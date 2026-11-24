# AGENTS.md

Repo-specific instructions override this file unless they conflict with safety. Scale rigor to task size.

## Core
Think first. Keep it simple. Change only what's needed. Verify before claiming success. Never present an assumption as fact.

## Before coding
- Read relevant code, config, and tests. Follow existing conventions and architecture.
- State assumptions explicitly. If multiple interpretations exist, present them; don't pick silently.
- If something is unclear, stop, name what's confusing, and ask. Skip questions that don't change correctness, security, or scope.
- Don't invent requirements, APIs, or dependencies. If a simpler approach exists, say so and push back when warranted.

## Code
- Minimum code that solves the task. No speculative features, flexibility, config, or single-use abstractions. No error handling for impossible scenarios.
- If 200 lines could be 50, rewrite. Test: would a senior engineer call this overcomplicated?
- Surgical diffs: don't "improve" adjacent code, comments, or formatting. Match existing style even if you'd do it differently. Remove only what your change made unused; mention unrelated dead code, don't delete it. Every changed line must trace to the task.
- Structure: group files by feature (one folder per cohesive feature), not by technical type. One responsibility per file, class, and function. No circular dependencies; keep module interfaces small and explicit.
- Layers: Routes/controllers parse, validate, delegate, and shape responses, with no business logic or DB queries. Services own business rules and workflows as cohesive classes with injected dependencies, independent of HTTP objects. Repositories own all DB access. Domain models are classes that own their invariants and related behavior.
- Classes vs functions: use a class when methods share state, a domain concept owns behavior, resources have a lifecycle, or the project already uses classes. Use plain functions for stateless, self-contained logic. Don't wrap one function in a class. No god classes or god services. Prefer composition over inheritance.
- Utilities: small, stateless, reusable only. Keep feature-specific helpers inside their feature. Never a dumping ground.
- Naming: descriptive names that state intent. Avoid vague names like process, handle, execute, manager, or helper unless the context makes them precise.
- Source files target <=300 lines. Split by responsibility, not arbitrarily. Don't grow oversized legacy files. Generated code and lockfiles are exempt.
- Comments explain why, never what.
- Add dependencies only with clear need. Use existing env conventions. No hardcoded environment values.

## Errors and logging
- Catch only where you can recover or translate. Never swallow errors or return success-shaped failures. Preserve causes.
- Clean up resources with finally or context managers. Retry only safe, idempotent operations with an explicit policy.
- Log meaningful events once. Never log secrets, tokens, or sensitive payloads. Never expose stack traces to users.

## Security (the client is untrusted)
- Validate all external input at trust boundaries, using schemas where available. Use parameterized queries and contextual output encoding.
- Enforce authn/authz server-side. Check resource ownership and tenant boundaries. Never trust client-supplied IDs, roles, prices, or state. Fail closed.
- No secrets in source or client bundles.
- Uploads are hostile. Verify content type, not the extension. Enforce size limits, use generated filenames, store outside executable paths, and reject unsupported formats.
- Cover injection (SQL/NoSQL/command), XSS, path traversal, SSRF, unsafe redirects, and oversized or malformed payloads where relevant.

## Concurrency and integrity
Assume operations can be interrupted at the worst moment: double submits, retries, duplicate webhooks, two workers on one job, crash after partial write, timeout after successful write.
- Mutations must be atomic and idempotent where required. Avoid check-then-write races. Process-local locks don't protect distributed state.
- Backend work must not depend on the browser staying open. A disabled button is UX, not protection.
- Don't add queues, locks, or coordination without demonstrated need.

## Goal-driven execution
Turn tasks into verifiable goals, then loop until verified. "Add validation" becomes "write tests for invalid inputs, make them pass". "Fix the bug" becomes "write a test that reproduces it, make it pass". "Refactor X" becomes "tests pass before and after". For multi-step work, state a short plan:
1. [step] -> verify: [check]
2. [step] -> verify: [check]
Weak criteria like "make it work" are not acceptable; define the check first.

## Testing (test-first)
- New features and bug fixes: write the failing test first and confirm it fails for the right reason. Then write the minimum code to pass, then refactor with tests green.
- Prioritize by impact. P0: auth bypass, secret exposure, data corruption. P1: duplicate financial ops, broken concurrency, irreversible partial writes. P2: invalid input, interrupted requests. P3: cosmetic.
- Test behavior, not implementation. Cover invalid, boundary, and adversarial inputs. Keep tests deterministic.
- Never weaken assertions or delete failing tests without approval. No filler tests.
- Exceptions (state why): prototypes, cosmetic changes, impractical automation. Define another acceptance check instead.

## Refactoring
Only for a concrete maintainability problem. Establish baseline behavior first. Keep behavior changes separate. Rerun tests after.

## Execution discipline
- Check repo status first. Preserve existing user changes.
- Run lint, types, and tests relevant to the change. Review the full diff before finishing.
- Never fabricate test results, benchmarks, file reads, commits, or deploy status. No evidence means no verified claim.
- Do not commit, push, deploy, or delete data unless authorized.
- Don't expand scope without approval.

## Done means
Acceptance criteria met, tests run and passing, adversarial and failure cases considered, no unrelated changes, secrets not exposed, and unverified items and remaining risks stated.

## Reporting
Be concise and technical: what changed, what was verified (actual commands and results), what is unverified, and the next step only if needed. Report facts, not optimism.