---
name: lightweight-architecture
description: Design simple, reversible module, API, data and integration boundaries for changes that cross components or are costly to undo. Avoid architecture work for small local edits.
---

# Lightweight architecture

Use this only when a change crosses modules, introduces an API or data boundary, adds an external integration, or makes a decision that will be expensive to reverse. Do not invoke it for an obvious single-file change.

1. Read the existing structure, conventions, tests and nearby implementations before proposing a new design.
2. State the user outcome, non-goals, constraints and the smallest useful first slice.
3. Identify the few boundaries that matter: inputs, outputs, ownership, data flow, errors, permissions and external dependencies.
4. Define contracts before implementation. Keep names, input/output shapes and error behavior predictable and consistent with the existing system.
5. Prefer an existing module or a simple direct implementation over a new layer, service, factory, event bus or configuration system.
6. Choose vertical slices that leave a working, testable path after each stage. Do not build every database layer, then every API layer, then every UI layer before testing anything.
7. Compare alternatives only when they materially affect scope, risk, reversibility, cost or user-visible behavior. Recommend one and explain the tradeoff in plain language.
8. Record an architecture decision only when it is hard to reverse, surprising without context and the result of a real tradeoff.
9. If evidence is insufficient, mark the decision as open instead of inventing a future-proof design.

The output should be a short design brief with boundaries, dependencies, milestones, verification points and explicit out-of-scope items.
