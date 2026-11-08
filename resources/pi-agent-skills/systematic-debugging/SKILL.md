---
name: systematic-debugging
description: Investigate unexpected behavior, failing tests, build errors, and regressions through reproduction and evidence before changing code.
---

# Systematic debugging

Use this when behavior is unexpected, a test or build fails, or a previous fix did not solve the problem.

1. State the expected behavior, actual behavior, exact trigger and environment.
2. Reproduce the problem with the smallest reliable command, input or interaction. Record the output and whether the reproduction is stable.
3. Localize the failure: identify the first incorrect value, event, request, file, stack frame or boundary. Read the direct caller and callee before proposing a fix.
4. Form one evidence-based hypothesis at a time. Run the smallest experiment that can confirm or reject it. Do not make several speculative edits together.
5. Fix the root cause at the correct boundary. Preserve existing behavior outside the requested case.
6. Add or update a focused regression check when the behavior is important and the project has an appropriate test surface.
7. Re-run the original reproduction and the affected checks. Inspect the actual output instead of treating an exit code as proof.
8. If evidence contradicts the current hypothesis, stop the current path, explain what changed, and choose a new hypothesis. Do not keep stacking patches.
9. Report unresolved environmental failures separately from code failures.

Final reports must distinguish reproduced facts, likely cause, applied fix, verification, and remaining uncertainty.
