---
name: code-review-quality
description: Perform an evidence-based read-only review of a change for correctness, scope, regressions, security and maintainability. Use before accepting implementation work.
---

# Code review quality

This is a read-only review. Inspect the actual diff and direct dependencies; do not modify the implementation.

1. Read the original request and acceptance criteria before reading the diff.
2. Inspect the actual changed files, relevant callers, tests and configuration. Do not review only the implementer's summary.
3. Look first for behavior defects, broken contracts, data loss, security issues, regressions, missing failure handling and changes outside scope.
4. Check whether tests or other verification actually exercise the requested behavior.
5. Classify findings by impact: blocking, important, optional or no finding. Do not report personal preferences as defects.
6. Each finding must include a file or symbol, trigger or affected path, evidence and practical impact.
7. If no issue is found, report the review scope and what remains unverified. Do not invent findings.
8. Keep review independent. Do not assume the implementation's design is correct because it is coherent or because a command succeeded.

Return concrete findings first, followed by verification limits and an overall acceptance recommendation.
