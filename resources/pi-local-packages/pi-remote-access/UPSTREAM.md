# Upstream provenance

- Repository: https://github.com/gthubtom1/agent-plugins
- Fixed commit: `2742f417d4dcf275a9a57bdf654af4a53ff25ddf` (short: `2742f417`).
- Source subtree: `plugins/pi/pi-seep-ext`.
- Local source location is machine-specific and resolved during restoration.
- License: MIT, original copyright and complete notice retained in `LICENSE`.

`extensions/remote.ts` derives from upstream `extensions/remote.ts`; only remote is declared in the new package. The original remote implementation and original ordinary-settings implementation are preserved verbatim as non-executable reference snapshots in `upstream/remote.ts.txt` and `upstream/remote-settings.ts.txt`. The snapshots contain source code, not captured runtime configuration or credential values. Their unsafe historical password output/storage code is never registered or imported.

Copied required libraries: `lib/agent-dir.ts`, `net.ts`, `probe.ts`, `qr.ts`, `tailscale-binary.ts`, and `tailscale.ts`. `tailscale.ts` uses local-client advice and never displays AuthURL. `lib/pi-api.ts` is a reduced structural host interface. `lib/remote-settings.ts` replaces password persistence with ordinary-field-only storage; `lib/storage.ts` and `lib/password-vault.ts` provide atomic local writes, secure generation, explicit restore/disable markers and credential-store-compatible storage.

Intentional recovery changes: session_start command button; password status/generate/disable without value-bearing messages; ignore legacy passwords; remove only null/empty legacy password fields on ordinary saves and protect nonempty/unknown ones and invalid ordinary JSON; retain unknown fields; use the canonical `<CRED:pi-web-remote/password>` reference; commit before applying runtime values; Tailscale status only, with original up/tray source retained in the reference snapshot; optional QR dependency does not block loading. No persona/rewind implementation or manifest entry is included. This standalone restoration does not alter the workbench's managed persona or its fallback behavior.

No deployment, package installation, settings modification, system environment change, real credential access, network configuration command or SRL source modification was performed to prepare this artifact. SDK/UI integration belongs to the separate main deployment workflow.
