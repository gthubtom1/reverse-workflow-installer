---
name: verification-before-completion
description: Verify requested behavior with direct evidence before claiming a task is complete. Use before delivery, review acceptance, or a completion report.
---

# Verification before completion

A completed edit is not automatically a completed task. Verify the behavior described by the acceptance criteria.

1. Translate each acceptance criterion into an observable check.
2. Choose the smallest relevant check for each criterion: focused test, build, command output, API request, browser interaction, file comparison, or reverse-engineering Evidence.
3. Run the check after the final relevant change. Do not rely only on an earlier run or on a model's explanation.
4. Inspect the actual output, returned data, rendered state, diff or Evidence. A successful command that did not exercise the requested behavior is not proof.
5. Check the important failure, empty, loading, permission or boundary state when the task has one.
6. Separate verified, partially verified, blocked and unverified items in the report.
7. Never claim a full end-to-end result when only static inspection, file generation or a unit-level check was performed.
8. Do not add broad tests merely to make a report look complete. Use focused checks that can fail for the requested behavior.

The final report must name the checks performed and state the remaining limits plainly.
