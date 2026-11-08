---
name: anti-overengineering
description: Keep implementation within the user's intended scope and prefer the simplest viable solution. Use when an agent starts adding abstractions, fallbacks, dependencies, or unrelated improvements.
---

# Anti-overengineering

Use this as a scope and simplicity check. It is a guardrail, not a reason to skip required tests, accessibility, error handling, security boundaries, or direct dependencies.

1. Restate the requested outcome and the explicit non-goals before changing code.
2. Read the existing implementation and reuse its patterns before adding a new abstraction, file, dependency, configuration value, or service.
3. Choose the smallest solution that satisfies the current acceptance criteria. Do not design for an imagined second implementation or future product.
4. Handle real errors at real boundaries: user input, external data, permissions, I/O and network calls. Do not add speculative fallbacks or defensive checks for impossible internal states.
5. Do not refactor, rename, format, document, or improve unrelated code while completing the task.
6. Required tests, focused regression checks, accessibility fixes and directly necessary supporting changes are within scope even when the user did not name each file.
7. If a proposed change materially expands scope, stop and report the smallest option, the expanded option and the consequence of each. Do not silently choose the expanded option.
8. Before delivery, remove code that does not support the requested behavior or required verification.

Report any assumption that affects scope. Keep the final diff understandable in one focused review.
