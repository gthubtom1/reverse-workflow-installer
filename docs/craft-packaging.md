# Craft portable packaging (P4/P5 foundation)

This build recipe prepares local artifacts for the existing [installer contract](craft-install.md).
It does not publish a release or activate a profile. Only Windows x86_64 GNU is
admitted. Linux, macOS, MSVC and ARM64 native artifacts are explicitly unsupported.
The offline packaging tests can run on other hosts; that does not qualify native builds there.

## Present evidence and blockers

An actual official standalone Pi 1.5.0 npm distribution has been acquired under
`.local/packaging/`, with installation scripts disabled, a v3 integrity lock and
all-file SHA256 inventory. Its CLI version and a no-model RPC `get_state` probe
passed in isolated agent/home directories. Node is explicitly 24.20.0. No Pi Web
tree, personal settings/models/MCP/auth or sessions are used. Provider readiness,
model calls and native optional features are separate qualifications. The actual
notice registry supplies 13 exact-source associations; proxy-agent-negotiate still
lacks an applicable grant text, so our Pi ZIP remains blocked. Supported delivery
acquires complete official Pi/Node dependencies upstream on the destination
computer, outside our native Craft release. Import success and SPDX metadata do
not establish license completeness.

Reviewed driver original tree is `50a2494ae8b86dd59b1988566e2b347fc939f16c0dde6a9b6ba158875e4e33e4`
with all 19 manifest files retained. Current policy original is
`0807fb2219751caec408aa1c89d2a5bc8a5cbee17062e7c0814fe125b929ab16`:
four exact patches, fresh0326 replay, 23 source hashes and unchanged Cargo files.
Executor prepare/validate/typed-return source is imported only from its final
reviewed complete manifest. No old source hash is a default pin. The combined
freeze binds exact original production/Cargo bytes, separately hashed portable
transformations and all meaningful tests/fixtures/helpers. A complete checkout
requires the authorized maintainer to commit those sources; packaging does not
stage, commit or publish.

Historical candidate ZIPs remain immutable. Their passed isolated install/update/
conditional restore/source-drift drill qualifies the installer mechanism for that
source set. New production source needs a new freeze, new artifact and independent
runtime/business acceptance. The retained Cargo cache supports an explicit
incremental rebuild; source drift is still rejected.

For maintainability, scripts/craft_sources.py implements explicit original and
packaged identities, complete Cargo fixture-source checks and portable transforms.
scripts/test_craft_owned.py replays the actual preserved Rust tests. Native
qualification helpers are source only and syntax checked, not counted as executed
acceptance. Public test tools must be explicit environment/CLI inputs.

## Source freeze and native build

Do this only after the bridge, executor and policy owners finish their fixes and
the lead freezes the reviewed inputs. Supply the complete ordered policy patches,
a reviewed notices directory (including GNU DLL license texts), and the executor's
real entry protocol. Do not substitute the bridge README or an assumed CLI shape
for the executor's full input/output/error/lifecycle contract.

The bridge import is explicitly source-manifest bound and does not traverse a
private qualification tree:

```text
python -B scripts/build_craft_bundle.py snapshot-bridge --source <approved-driver-source> --manifest <approved-driver-SOURCE-MANIFEST.json> --source-tree-sha256 <current-lead-approved-tree-sha256>
```

After the remaining owners freeze, supply the canonical bridge path to `freeze`:

```text
python -B scripts/build_craft_bundle.py freeze --bridge adapters/craft-pi/runtime/bridge --executor <frozen-executor> --series adapters/craft-pi/runtime/patches/series.json --series-sha256 <approved-portable-series-sha256> --patch <runtime/patches/first.patch> --patch <runtime/patches/next.patch> --notices <reviewed-notices> --protocol <reviewed-entry-protocol.md>
python -B scripts/build_craft_bundle.py build --version <approved-three-part-bundle-version> --stage .local/packaging/native-build --output .local/artifacts/craft-windows-gnu --cargo <absolute-cargo.exe> --rustc <absolute-rustc.exe> --gcc <absolute-gcc.exe> --objdump <absolute-objdump.exe> --dll-dir <explicit-gnu-runtime-dir>
```

The series SHA is mandatory and identifies the actual portable JSON bytes. For
current typed-return snapshot the portable SHA is
`61cf9b94c6cc3b28de8f5ea16e44ee9be7f92937bac91da880bda3bda4919a6c`;
its origin records the original approved 0807fb22 series SHA. The exact patch list/order
must match that approved series. Existing canonical patches are reused only when
all bytes match; series.json is metadata, never passed to git apply. Any change
invalidates source identity. No frozen final manifest is silently refreshed.
Recipe identity includes the build script, craft_sources.py,
craft_cargo_notices.py, test_craft_owned.py, packaging_process.py, craft.py,
configuration.py and versions.py; imported reader changes invalidate the freeze.
The complete entry/skill/instructions/reader resource snapshot is also included
and separately hashed. A parallel reader-contract update requires a new explicit
candidate freeze; an old resource snapshot cannot certify new reader bytes.

The complete source snapshot now retains all manifest-listed tests, fixtures,
examples, .gitignore and development scripts, rather than only production files.
The production src, Cargo.toml and Cargo.lock remain byte-identical. README and
config.example.json use portable instructions/placeholders; published offline tests
require explicit CRAFT_TEST_NODE/CRAFT_TEST_ROOT and executor driver/Cargo inputs.
Developer helper tool paths are explicit environment inputs. Every transformed
non-production file has original and packaged SHA256 in snapshot-origin.json.
Native qualification scripts are retained source and syntax checked, not run or
certified as provider/business acceptance. Fixture binaries are never runtime bin
outputs; their source remains available for meaningful offline regressions.

The `freeze` command copies the complete validated owned inventory;
for the canonical bridge it also retains the portable docs, MIT notice and snapshot
manifests. It retains this crate's exact dual-license Cargo declaration, choosing
its MIT option for distribution under the installer project's own copyright.
Test/fixture/helper source is included as maintained source; build output, raw
logs, private data, personal provider resources and arbitrary unmanifested inputs
are excluded. Extra
build inputs outside that supported layout must be reviewed and added to the
recipe before freezing, rather than silently read from a developer directory.
Every path dependency must resolve inside the isolated source tree. The fixed
sibling mapping preserves the current Cargo paths without rewriting source.

Use the actual toolchain executables, not rustup shims that select an ambient
version. The recipe checks Rust/Cargo 1.99.0 GNU, hashes all selected tools, and
records `rustc -vV`, target and GCC/objdump versions. It does not install a
compiler, alter global PATH, or update a global toolchain. GCC's directory is
prepended only in the build subprocess environment. Cargo home/target are under
the fresh stage; ambient credentials, Node injection and Rust flags are removed.
`--offline` uses only that stage's pre-populated Cargo cache, with no fallback.
Commands start suspended in an owned Windows Job before user code runs; timeout
terminates the Job and observes root exit plus zero active members within a finite
cleanup deadline. Unknown cleanup blocks certification. Unix commands use an owned
process group and observe only that scope; setsid escape is not contained or
claimed as verified descendant cleanup. A successful root with leftover group/Job
members also fails. Output files are local, so inherited pipes cannot hold EOF.

The upstream checkout uses exact commit
`0326b4de8051f85a0f3139cd82f88f76911e6a35`. `--upstream-mirror <local-clone>` is an
optional read-only object source; HEAD is still checked. Git ignores global
configuration and normalizes checkout bytes to LF. Each ordered patch is hash
checked, `git apply --check --index` checked and applied against the preceding
patch. Changed bases need a reviewed compatibility update, not a new digest on an
unreviewed upstream tree. There is no tracking of latest/main.

Both binaries use `cargo build --locked --release --message-format=json --target
x86_64-pc-windows-gnu --bin <exact-name>`. The compiled package inventory comes
from actual compiler-artifact messages, not every package in metadata. Original
notice text plus the corresponding locked registry .crate checksum is recorded
for those compiled dependencies. An uncompiled GUI package is not added merely
because it exists in the upstream workspace. A missing compiled notice blocks
normal assembly. The sole reviewed standard-text association is
`yaxpeax-arm@0.5.0`: `runtime/notices/cargo-standard-0bsd/SOURCE.json` pins its
registry archive, VCS commit, original and normalized Cargo metadata, and the
unchanged official SPDX v3.26.0 `text/0BSD.txt`. Its status is
`standard-license-text,declared-in-upstream-metadata`; no original upstream LICENSE
or package copyright is claimed, and YEAR/AUTHOR EMAIL template placeholders remain
unchanged. All identity/evidence hashes must match. Other SPDX declarations,
including MIT/Apache metadata without retained grants, still fail the default gate.
The standard text and provenance join the compiled inventory and source freeze;
recipe changes require a new freeze and artifact. Historical candidate ZIPs retain
their original blockers and are not retroactively release eligible.
Test features and `--all-targets` are never used for production binaries. The executor
and driver have separate retained locks. The patched upstream lock is also
preserved. Before/after inventories reject source/lock edits and new source files;
canonical manifest and recipe identities are checked throughout finalization.
A failure removes eligible manifests from both staging and final output.

The result includes real `bin/craft-pi-executor.exe`, `bin/pi-rpc-driver.exe`, the
recursive non-system DLL closure found through objdump, original MIT/Apache/
attribution/NOTICE, Cargo dependency license texts, reviewed runtime notices,
canonical owned source and patch originals, locks, entry protocol and build
provenance. Missing DLLs or dependency license texts block the build. This is
content reproducibility and provenance; bit-for-bit compiler reproducibility and
business/runtime acceptance are not claimed.

## Replaying owned offline regressions

After staging the exact sibling source layout (or after native build), run the
preserved Rust P1/P2 suite with explicit inputs. This reuses that stage's dependency
cache and retains exact tool/command logs; it never calls a provider:

```text
python -B scripts/test_craft_owned.py --source-layout .local/packaging/native-build/source --output .local/tests/owned-final --cargo <absolute-cargo.exe> --rustc <absolute-rustc.exe> --gcc <absolute-gcc.exe> --node .local/pi-upstream/pi/distribution/node/node.exe --target-dir .local/packaging/native-build/owned-test-target --cargo-home .local/packaging/native-build/cargo-home --release
```

`--offline` can be added after the cache has been populated with test dependencies.
Output/root is fresh and external to the frozen source directories. Driver tests
exercise actual Node fixtures; executor tests build/run only an offline fixture
application and the actual bounded MCP integration, with no model/provider. The
separately retained native qualification helpers are not invoked by this runner.
A total deadline bounds the sequential regressions. CLI failures and unknown
process cleanup are failures, never a fake pass.

For an explicitly reviewed owned-source or policy update, the build's `--reuse-stage`
requires `--previous-source-manifest` and `--previous-source-sha256`. It verifies the
old owned inventory, prior series identity, exact base, staged patch tree and source
hashes before replacing source copies. Changed approved policy patches replay in a
fresh exact-base clone after the verified old clone is preserved in history. Cargo
home/target remain in place; provenance records reuse and the previous manifest.
New replay must still match all approved source hashes and unchanged Cargo files.
No old binary hash is claimed equal to a new build.

## Official Pi: upstream acquisition on each computer

Our native Craft release does not contain an official Pi/Node ZIP. From an installer
checkout with Python 3.11+, run into a fresh output directory:

```text
python -B scripts/build_craft_bundle.py acquire-pi --stage .local/pi-upstream
```

The command downloads official Node 24.20.0 Windows x64 from the exact nodejs.org
URL in runtime/pi/node-windows-x64.json, checks archive SHA256
6cac9ffbca8f6a47091e4b5c772e0606049c3871cb67d900c0cedde630e545ba, extracts it
locally, and checks node.exe SHA256
5c976096e04e5c2c1f091938926234cc9fbebfe9787ddd149351b3b0ecc707b5.
No system tool or global PATH is changed. npm comes from that official archive.
The published built-in npm/.npmrc is permitted only at its exact path after the
archive digest is verified; generic ZIP extraction still rejects profile files.
An optional --node-archive <cached-official-zip> reuses only a hash-matching archive,
never a prior node_modules closure.

npm ci --ignore-scripts --bin-links=false uses the canonical exact Pi 1.5.0 lock,
a fresh prefix/cache, empty user/global npm configs and isolated HOME/APPDATA.
All declared dependencies remain present. We do not trim Negotiate/Bedrock or
modify official Pi source, registrations or model APIs. Output is
.local/pi-upstream/pi/distribution, containing Node/LICENSE, full node_modules,
original npm lock/provenance, collected original notices and pi-runtime.json.
A copied-Node version probe and no-model RPC get_state must pass before
.local/pi-upstream/acquisition-result.json is written. That receipt contains
installer_pi_options: all four explicit runtime options generated on this computer.
No personal Pi/Web settings, auth, models, MCP or sessions are copied.

The command's public entry supervises its entire worker in the existing owned
Windows Job (or Unix process group) with a **600-second total wall deadline**.
`--deadline-seconds` can shorten it to 1..600 seconds. Socket timeouts are not used
as a substitute for this total limit. Timeout or unknown cleanup blocks completion
and removes a premature acquisition-result receipt in the new stage. Already
existing output directories are refused before any command is launched.
The network boundary is nodejs.org plus exact registry.npmjs.org URLs/integrities
in the npm lock. Other-platform optional packages stay pinned in the lock but need
not be installed on Windows. Another computer still needs network and Python;
this is reproducible online acquisition, not offline Pi redistribution or proof
that a physically different computer was tested. The native Craft bundle remains
a separate input.

The 13 notices are copied verbatim with all registry artifacts, sizes and SHA256
values checked. NOTICE-inventory.json retains exact npm name/version/integrity and
the original source association. AWS tag/version/time evidence is explicitly not
an npm build attestation. Real Unlicense dedication, grant and warranty text is
recognized; a bare SPDX label is insufficient. proxy-agent-negotiate@1.1.0 remains
unknown and release-pi stays blocked. Upstream local acquisition does not imply
authorization for our project to republish that distribution. Notice collection
is not legal approval.

The lower-level prepare-pi command remains available for an already explicit
Node/npm installation. New-computer instructions use acquire-pi and need no
developer-machine paths or manual Node layout. Provider credentials and model
qualification remain separate from the version/state-only probes.

## Local installation and release preparation

Use [craft-install.md](craft-install.md) to plan/apply against a fresh independent
root, pointing `--craft-bundle` at the real output and the four Pi options at the
separate standalone distribution. Node/entry/distribution are explicit; no path
to the original build machine is required. Move the complete distribution and
bundle, then create a new plan with their destination paths. Existing frozen
plans intentionally reject source root movement. Once a real reviewed native
bundle exists, the generated acquisition receipt supplies the Pi options directly:

```python
import json
from pathlib import Path
import subprocess
import sys

runtime = json.loads(Path('.local/pi-upstream/acquisition-result.json').read_text(encoding='utf-8'))
subprocess.run([
    sys.executable, '-B', 'scripts/install.py', 'plan',
    '--components', 'reverse,spec-kit,craft', '--client', 'pi',
    '--root', '../fresh-workflow', '--agent-dir', '../fresh-workflow/pi-agent',
    '--project', '../fresh-project', '--reverse-root', '../reverse-skill',
    '--craft-bundle', '../reviewed-craft-bundle',
    *runtime['installer_pi_options'], '--output', '.local/fresh-plan.json',
], check=True)
```

This does not claim the still-pending native bundle/fresh install was tested.
Apply/verify use the existing installer transaction commands in craft-install.md.
The acquisition root must be retained as the receipt's explicit external runtime.

```text
python -B scripts/build_craft_bundle.py release-artifact --bundle .local/artifacts/craft-windows-gnu --output .local/artifacts/craft-windows-gnu.zip
python -B -m unittest discover -s tests -p test_craft_packaging.py -v
```

Native release preparation excludes the separately acquired official Pi/Node tree.
The optional release-pi command remains blocked by the actual missing notice and
is not the supported delivery path. Native preparation validates the existing
bundle before writing an archive. The earlier Pi ZIP's notice
completeness claim has been withdrawn; it is historical evidence, not a product
asset. No raw Pi/Node closure is embedded in our native Craft bundle.
A successful native release preparation writes a ZIP with stable
member ordering/timestamps, a real SHA256 sidecar, upload-plan JSON and release
body Markdown. It performs no upload, tag creation, release or push. The upload
plan deliberately has `published: false` and `release_url: null`. A real future
asset must be published by the approved owner, then its real repository/tag/
commit/unique asset URL and digest resolved and reviewed before adding an
installer pin. No remote download is added to the installer CLI in this phase;
its current local contract and explicit compatibility pin remain unchanged.
The ZIP reader validates all members before extraction and rejects path escapes,
case collisions, links, encrypted members, credential/profile paths and empty
archives. Extraction alone never certifies a Craft bundle; run its full gate.

The new CI workflow runs packaging unit tests offline on Windows/Ubuntu. A
manual, trusted Windows GNU build job requires a pre-provisioned runner with exact
tools and frozen canonical sources. It runs no model calls. A workflow file is
not evidence that a hosted or self-hosted job has run or passed.
