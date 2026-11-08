# Portable Pi development skills

These are small first-party skills for the current multi-agent setup. They are intentionally separate from the existing external UI, reverse-workflow and grilling skills.

Included:
- anti-overengineering: scope and simplicity guardrail
- systematic-debugging: evidence-first debugging
- verification-before-completion: evidence before completion claims
- code-review-quality: read-only implementation review
- lightweight-architecture: small, reversible architecture decisions

Install them into the global skills directory on a target Windows machine:

%USERPROFILE%\.agents\skills\

Do not copy the source computer's auth, model, settings, sessions or memory files. Skills use dynamic discovery; they are not hard-bound to a profile name.