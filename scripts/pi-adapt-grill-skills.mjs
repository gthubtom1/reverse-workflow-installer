#!/usr/bin/env node
// Generate/update wrappers in an explicit installer-owned root.
// Usage: node scripts/pi-adapt-grill-skills.mjs --skills-root <official-root> --output-root <owned-root> [--json]
import { runCli } from "./pi-grill-common.mjs";
runCli("adapt");
