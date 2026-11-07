#!/usr/bin/env node
// Read-only local hash/provenance and wrapper-template verification.
// This does not authenticate upstream content or validate Pi host behavior.
// Usage: node scripts/verify-pi-grill-skills.mjs --skills-root <official-root> --output-root <owned-root> [--json]
import { runCli } from "./pi-grill-common.mjs";
runCli("verify");
