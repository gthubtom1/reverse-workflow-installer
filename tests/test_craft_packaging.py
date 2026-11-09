"""Offline packaging failure/identity checks. Rust/PE/Pi text here is inert fixture data."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import build_craft_bundle as b
import craft
from configuration import load_json
from versions import InstallError


class PackagingTests(unittest.TestCase):
    def setUp(self):
        parent = REPO / ".local/tests"
        parent.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="packaging-", dir=parent)
        self.root = Path(self.tmp.name)
        self.bridge = self.root / "bridge"
        self.executor = self.root / "executor"
        for root, name in ((self.bridge, "craft-pi-bridge"), (self.executor, "craft-pi-executor")):
            self.put(root / "Cargo.toml", f'[package]\nname = "{name}"\nversion = "0.1.0"\n')
            self.put(root / "Cargo.lock", "# Inert test lockfile; no Cargo build performed\n")
            self.put(root / "src/main.rs", "// inert fixture Rust source\n")
        self.put(self.executor / "Cargo.toml", (self.executor / "Cargo.toml").read_text() + '[dependencies]\ncraft-pi-bridge = {path = "../craft-pi-bridge"}\n')
        self.policy_patch = self.root / "policy.patch"
        self.put(self.policy_patch, "inert policy patch fixture\n")
        self.notices = self.root / "notices"
        self.put(self.notices / "THIRD_PARTY_NOTICES.md", "Inert fixture notices\n")
        self.protocol = self.root / "protocol.md"
        self.put(self.protocol, "Inert fixture entry protocol\n")
        self.runtime = self.root / "canonical"

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def freeze(self, patches=None):
        approved = self.root / 'approved-series'
        approved.mkdir(exist_ok=True)
        records = []
        paths = []
        for p in patches or [self.policy_patch]:
            target = approved / Path(p).name
            shutil.copy2(p, target)
            paths.append(target)
            records.append({'file': target.name, 'sha256': b.sha(target)})
        series = approved / 'series.json'
        b.write_json(series, {'base_commit': b.BASE, 'series': records})
        return b.freeze(self.bridge, self.executor, paths, self.notices, self.protocol, self.runtime,
                        series_path=series, series_sha256=b.sha(series))

    def test_existing_approved_patches_can_freeze_and_series_drift_is_rejected(self):
        patches = self.runtime / 'patches'
        patches.mkdir(parents=True)
        target = patches / self.policy_patch.name
        shutil.copy2(self.policy_patch, target)
        series = patches / 'series.json'
        b.write_json(series, {'base_commit': b.BASE, 'series': [{'file': target.name, 'sha256': b.sha(target)}]})
        approved_sha = b.sha(series)
        value = b.freeze(self.bridge, self.executor, [target], self.notices, self.protocol, self.runtime,
                         series_path=series, series_sha256=approved_sha)
        self.assertEqual(b.source_identity(self.runtime)[0], value)
        self.assertEqual(value['patch_series']['sha256'], approved_sha)
        self.assertNotIn('patches/series.json', {p['path'] for p in value['patches']})
        with self.assertRaisesRegex(InstallError, 'SHA256 mismatch'):
            b.approved_series(series, '0' * 64)
        self.put(series, series.read_text() + '\n')
        with self.assertRaisesRegex(InstallError, 'drift'):
            b.source_identity(self.runtime)

    def test_recipe_import_dependency_drift_invalidates_freeze(self):
        self.freeze()
        original = b.recipe_identity()
        with patch.object(b, 'recipe_identity', return_value={**original, 'craft.py': '0' * 64}), self.assertRaisesRegex(InstallError, 'recipe changed'):
            b.source_identity(self.runtime)

    def test_node_copy_rejects_corruption_and_source_drift(self):
        source = self.root / 'node-fixture.exe'
        target = self.root / 'copied-node.exe'
        self.put(source, 'inert node fixture')
        expected = b.sha(source)
        self.assertEqual(b.copy_node(source, target, expected), target)
        original = b.copy_file
        for change_source in (False, True):
            self.put(source, 'inert node fixture')
            def corrupt(src, dst):
                original(src, dst)
                self.put(source if change_source else target, 'drift')
            with patch.object(b, 'copy_file', side_effect=corrupt), self.assertRaisesRegex(InstallError, 'identity drift'):
                b.copy_node(source, target, expected)

    def test_pi_version_probe_uses_copied_node_and_rejects_midprobe_drift(self):
        source = self.root / 'source-node.exe'
        copied = self.root / 'copy-node.exe'
        for p in (source, copied):
            self.put(p, 'inert Node bytes')
        expected = b.sha(source)
        with patch.object(b, 'command', return_value=b.PI_VERSION) as run:
            b.probe_pi_version(source, copied, self.root / 'cli.js', self.root, {}, expected)
        self.assertEqual(run.call_args.args[0][0], copied)
        def change(*args, **kwargs):
            self.put(copied, 'corrupted during version probe')
            return b.PI_VERSION
        with patch.object(b, 'command', side_effect=change), self.assertRaisesRegex(InstallError, 'during probe'):
            b.probe_pi_version(source, copied, self.root / 'cli.js', self.root, {}, expected)

    def test_npm_spdx_or_readme_label_is_not_license_notice_and_blocks_release(self):
        root = self.root / 'pi-distribution'
        package = root / 'node_modules' / b.PI_PACKAGE
        self.put(package / 'package.json', json.dumps({'name': b.PI_PACKAGE, 'version': b.PI_VERSION, 'license': 'MIT'}))
        self.put(package / 'README.md', '# Pi\nLicense: MIT\n')
        lock = {'lockfileVersion': 3, 'packages': {'': {}, 'node_modules/' + b.PI_PACKAGE: {'version': b.PI_VERSION,
                'resolved': 'https://registry.npmjs.org/pi/-/pi.tgz', 'integrity': 'sha512-YWJj'}}}
        b.write_json(root / 'package-lock.json', lock)
        report = b.npm_notice_inventory(root)
        self.assertEqual(report['distribution_status'], 'blocked-missing-notices')
        self.assertEqual(report['missing'][0]['name'], b.PI_PACKAGE)
        b.write_json(root / 'NOTICE-inventory.json', report)
        archive = self.root / 'blocked.zip'
        with self.assertRaisesRegex(InstallError, 'release blocked'):
            b.release_artifact(root, archive, pi=True)
        self.assertFalse(archive.exists())
        # Inert fixture copyright text tests inventory only, never certifies a real package.
        self.put(package / 'LICENSE', 'Copyright inert test author\nPermission is hereby granted to test fixtures only. ' + 'Fixture text. ' * 20)
        report = b.npm_notice_inventory(root)
        b.write_json(root / 'NOTICE-inventory.json', report)
        self.assertFalse(b.require_pi_notices(root)['missing'])
        self.put(package / 'LICENSE', 'changed')
        with self.assertRaisesRegex(InstallError, 'release blocked'):
            b.require_pi_notices(root)

    def test_owned_command_timeout_terminates_descendant_and_never_certifies_unknown(self):
        marker = self.root / 'descendant.pid'
        worker = self.root / 'spawn.py'
        self.put(worker, 'import subprocess,sys,time\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])\nPath(sys.argv[1]).write_text(str(p.pid))\ntime.sleep(30)\n')
        result = b.run_owned([sys.executable, worker, marker], cwd=self.root, timeout=1, cleanup_seconds=2)
        self.assertTrue(result['timed_out'])
        self.assertTrue(marker.exists())
        if b.os.name == 'nt':
            self.assertEqual(result['cleanup'], 'verified')
            import ctypes
            api = ctypes.WinDLL('kernel32', use_last_error=True)
            api.OpenProcess.restype = ctypes.c_void_p
            api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
            handle = api.OpenProcess(0x1000, False, int(marker.read_text()))
            if handle:
                status = ctypes.c_uint32()
                api.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                api.CloseHandle.argtypes = [ctypes.c_void_p]
                self.assertTrue(api.GetExitCodeProcess(handle, ctypes.byref(status)))
                api.CloseHandle(handle)
                self.assertNotEqual(status.value, 259)
        with patch.object(b, 'run_owned', return_value={'cleanup': 'unknown', 'timed_out': True, 'had_descendants': True, 'scope': 'fixture'}), self.assertRaisesRegex(InstallError, 'cleanup=unknown'):
            b.command(['inert'], cwd=self.root)

    def test_snapshot_keeps_relative_layout_and_excludes_test_peer(self):
        self.put(self.bridge / "tests/fixtures/fake_pi.rs", "not distributable")
        self.put(self.bridge / "target/fake-pi.exe", "not distributable")
        self.put(self.bridge / "settings.json", "excluded without reading")
        value = self.freeze()
        self.assertEqual(b.source_identity(self.runtime)[0], value)
        self.assertEqual(value["base_commit"], b.BASE)
        self.assertEqual(value["recipe_sha256"], b.sha(b.__file__))
        self.assertEqual(value["mapping"]["craft-pi-executor"], "executor")
        self.assertTrue(any("fake_pi" in x for x in value["files"]))
        self.assertFalse(any("/target/" in x for x in value["files"]))
        self.assertEqual((self.runtime / "executor/Cargo.toml").read_bytes(), (self.executor / "Cargo.toml").read_bytes())

    def test_approved_bridge_snapshot_preserves_cargo_and_source_with_distinct_packaged_identity(self):
        self.put(self.bridge / 'src/lib.rs', '// inert library source')
        self.put(self.bridge / 'README.md', 'local-only evidence README')
        self.put(self.bridge / 'config.example.json', json.dumps({'pi': {}, 'cancel': {}}))
        self.put(self.bridge / 'tests/fixtures/fake_pi.rs', '// not runtime source')
        files = b.tree(self.bridge)
        digest = b.hashlib.sha256(''.join(f'{p}\0{files[p]}\n' for p in sorted(files)).encode()).hexdigest()
        manifest_path = self.root / 'frozen-driver.json'
        b.write_json(manifest_path, {'source_tree_sha256': digest, 'files': [{'path': p, 'sha256': h} for p, h in sorted(files.items())]})
        target = self.root / 'packaged-bridge'
        result = b.snapshot_bridge(self.bridge, manifest_path, digest, target)
        b.validate_bridge_snapshot(target)
        self.assertNotEqual(result['frozen_source_tree_sha256'], result['packaged_source_tree_sha256'])
        self.assertEqual((target / 'Cargo.toml').read_bytes(), (self.bridge / 'Cargo.toml').read_bytes())
        self.assertEqual((target / 'src/lib.rs').read_bytes(), (self.bridge / 'src/lib.rs').read_bytes())
        self.assertNotIn('local-only', (target / 'README.md').read_text())
        self.assertTrue((target / 'config.example.json').exists())
        self.assertTrue((target / 'tests/fixtures/fake_pi.rs').exists())
        self.assertIn('gthubtom1', (target / 'LICENSE-MIT').read_text())
        self.assertEqual(set(b.tree(target)), {'Cargo.toml', 'Cargo.lock', 'src/main.rs', 'src/lib.rs',
                         'README.md', 'LICENSE-MIT', 'ATTRIBUTION.md', 'FROZEN-SOURCE-MANIFEST.json',
                         'snapshot-origin.json', 'packaged-source-manifest.json', 'config.example.json', 'tests/fixtures/fake_pi.rs'})
        self.put(target / 'src/lib.rs', 'changed')
        with self.assertRaisesRegex(InstallError, 'driver source drift'):
            b.validate_bridge_snapshot(target)

    def test_bridge_snapshot_requires_explicit_matching_hash_and_complete_production_inventory(self):
        self.put(self.bridge / 'src/lib.rs', '// inert library source')
        files = b.tree(self.bridge)
        digest = b.hashlib.sha256(''.join(f'{p}\0{files[p]}\n' for p in sorted(files)).encode()).hexdigest()
        manifest_path = self.root / 'frozen-driver.json'
        b.write_json(manifest_path, {'source_tree_sha256': digest, 'files': [{'path': p, 'sha256': h} for p, h in sorted(files.items())]})
        target = self.root / 'packaged-bridge'
        with self.assertRaisesRegex(InstallError, 'tree hash mismatch'):
            b.snapshot_bridge(self.bridge, manifest_path, '0' * 64, target)
        self.assertFalse(target.exists())
        self.put(self.bridge / 'src/unlisted.rs', '// not frozen')
        with self.assertRaisesRegex(InstallError, 'inventory mismatch'):
            b.snapshot_bridge(self.bridge, manifest_path, digest, target)
        self.assertFalse(target.exists())

    def test_missing_canonical_freeze_does_not_build(self):
        self.runtime.mkdir()
        with self.assertRaisesRegex(InstallError, "awaiting source freeze"):
            b.source_identity(self.runtime)

    def test_empty_source_rejected(self):
        (self.bridge / "src/main.rs").unlink()
        with self.assertRaisesRegex(InstallError, "empty"):
            self.freeze()
        self.assertFalse((self.runtime / "source-manifest.json").exists())

    def test_source_changed_during_copy_cannot_be_certified(self):
        original = b.copy_file
        def change(source, destination):
            original(source, destination)
            if Path(source) == self.bridge / "src/main.rs":
                self.put(source, "changed by parallel worker")
        with patch.object(b, "copy_file", side_effect=change), self.assertRaisesRegex(InstallError, "changed while freezing"):
            self.freeze()
        self.assertFalse((self.runtime / "source-manifest.json").exists())

    def test_corrupted_copy_cannot_certify_unchanged_source(self):
        original = b.copy_file
        def corrupt(source, destination):
            original(source, destination)
            if Path(source) == self.executor / 'src/main.rs':
                Path(destination).write_bytes(b'corrupted copy')
        with patch.object(b, 'copy_file', side_effect=corrupt), self.assertRaisesRegex(InstallError, 'copied source differs'):
            self.freeze()
        self.assertFalse((self.runtime / 'source-manifest.json').exists())

    def test_source_added_changed_deleted_while_building_rejected(self):
        self.freeze()
        frozen = b.source_identity(self.runtime)
        source = self.runtime / "executor/src/main.rs"
        source.write_text("drift")
        with self.assertRaisesRegex(InstallError, "drift"):
            b.assert_unchanged(self.runtime, frozen)
        source.unlink()
        with self.assertRaisesRegex(InstallError, "drift"):
            b.assert_unchanged(self.runtime, frozen)

    def test_new_source_and_rewritten_manifest_cannot_replace_frozen_identity(self):
        self.freeze()
        frozen = b.source_identity(self.runtime)
        p = self.runtime / "executor/src/new.rs"
        self.put(p, "new")
        with self.assertRaisesRegex(InstallError, "drift"):
            b.assert_unchanged(self.runtime, frozen)
        value = load_json(self.runtime / "source-manifest.json")
        value["files"][p.relative_to(self.runtime).as_posix()] = b.sha(p)
        b.write_json(self.runtime / "source-manifest.json", value)
        with self.assertRaisesRegex(InstallError, "source changed"):
            b.assert_unchanged(self.runtime, frozen)

    def test_incompatible_source_base_and_recipe_fail_closed(self):
        self.freeze()
        value = load_json(self.runtime / "source-manifest.json")
        for key, val in (("base_commit", "a" * 40), ("recipe_sha256", "b" * 64), ("target", "x86_64-pc-windows-msvc")):
            mutated = copy.deepcopy(value)
            mutated[key] = val
            b.write_json(self.runtime / "source-manifest.json", mutated)
            with self.subTest(key=key), self.assertRaises(InstallError):
                b.source_identity(self.runtime)

    def test_unlisted_or_duplicate_patch_is_rejected(self):
        self.freeze()
        value = load_json(self.runtime / "source-manifest.json")
        value["patches"].append(value["patches"][0])
        b.write_json(self.runtime / "source-manifest.json", value)
        with self.assertRaisesRegex(InstallError, "patch"):
            b.source_identity(self.runtime)
        value["patches"] = []
        b.write_json(self.runtime / "source-manifest.json", value)
        with self.assertRaisesRegex(InstallError, "patch"):
            b.source_identity(self.runtime)

    def test_external_cargo_dependency_rejected(self):
        outside = (self.root / 'external-dependency').as_posix()
        self.put(self.executor / "Cargo.toml", f'[package]\nname="craft-pi-executor"\n[dependencies]\nevil={{path="{outside}"}}\n')
        self.freeze()
        with self.assertRaisesRegex(InstallError, "escapes"):
            b.source_identity(self.runtime)

    def test_target_specific_and_build_dependencies_cannot_escape(self):
        for section in ('build-dependencies', 'target.\'cfg(windows)\'.dependencies', 'dev-dependencies'):
            self.put(self.executor / "Cargo.toml", f'[package]\nname="craft-pi-executor"\n[{section}]\nevil={{path="../../outside"}}\n')
            metadata = __import__('tomllib').loads((self.executor / 'Cargo.toml').read_text())
            self.assertEqual(list(b.dependency_paths(metadata)), ['../../outside'])
        # The staged preflight also covers patched upstream Cargo manifests before Cargo is run.
        with self.assertRaisesRegex(InstallError, "outside isolated source"):
            b.validate_cargo_paths(self.root)

    def test_failed_final_copy_removes_both_eligible_manifests(self):
        from test_craft import toy_bundle
        self.freeze()
        frozen = b.source_identity(self.runtime)
        source = self.root / "candidate"
        manifest = toy_bundle(source)
        (source / craft.MANIFEST).unlink()
        output = self.root / "final"
        original = b.shutil.copytree
        def moving_source(src, dest, *args, **kwargs):
            result = original(src, dest, *args, **kwargs)
            if Path(src) == source:
                self.put(self.runtime / 'executor/src/late.rs', 'late edit')
            return result
        with patch.object(b.shutil, 'copytree', side_effect=moving_source), self.assertRaisesRegex(InstallError, 'drift'):
            b.certify_bundle(source, manifest, self.runtime, frozen, output)
        self.assertFalse((source / craft.MANIFEST).exists())
        self.assertFalse((output / craft.MANIFEST).exists())

    def test_secret_denied_before_reading_item(self):
        self.put(self.notices / "auth.json", "do not read")
        with self.assertRaisesRegex(InstallError, "forbidden"):
            self.freeze()

    def test_patch_base_and_hash_failure_before_apply(self):
        self.freeze()
        records = load_json(self.runtime / "source-manifest.json")["patches"]
        calls = []
        def wrong(argv, **kwargs):
            calls.append(argv)
            return "b" * 40
        with self.assertRaisesRegex(InstallError, "base incompatible"):
            b.apply_patches(self.root, self.runtime, records, wrong)
        self.assertEqual(len(calls), 1)
        def right(argv, **kwargs):
            return b.BASE if "rev-parse" in argv else ""
        self.put(self.runtime / records[0]["path"], "drift")
        with self.assertRaisesRegex(InstallError, "hash drift"):
            b.apply_patches(self.root, self.runtime, records, right)

    @unittest.skipUnless(shutil.which("git"), "Git unavailable")
    def test_ordered_patches_really_apply_and_context_failure_is_fatal(self):
        source = self.root / "git-fixture"
        source.mkdir()
        def git(*args):
            return b.command(["git", *args], cwd=source)
        git("init")
        git("config", "core.autocrlf", "false")
        self.put(source / "file.txt", "one\n")
        git("add", "file.txt")
        git("-c", "user.name=PackagingFixture", "-c", "user.email=fixture@invalid", "commit", "-m", "inert fixture")
        records = []
        for i, (old, new) in enumerate((("one", "two"), ("two", "three"))):
            path = self.root / f"{i}.patch"
            self.put(path, f"diff --git a/file.txt b/file.txt\n--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-{old}\n+{new}\n")
            records.append({"path": path.name, "sha256": b.sha(path)})
        def fixture_git(argv, **kwargs):
            # The fixture has its own real commit; only the production base gate is substituted.
            return b.BASE if "rev-parse" in argv else b.command(argv, **kwargs)
        with self.assertRaisesRegex(InstallError, "command failed"):
            b.apply_patches(source, self.root, list(reversed(records)), fixture_git)
        self.assertEqual((source / "file.txt").read_text(), "one\n")
        b.apply_patches(source, self.root, records, fixture_git)
        self.assertEqual((source / "file.txt").read_text(), "three\n")

    def cached_policy_fixture(self):
        upstream = self.root / 'cached-upstream'
        upstream.mkdir()
        b.git_command(['git', 'init', '--quiet'], cwd=upstream)
        for name, data in {'Cargo.toml': '[workspace]\n', 'Cargo.lock': 'version = 4\n', 'policy.txt': 'base\n'}.items():
            self.put(upstream / name, data)
        b.git_command(['git', 'add', '.'], cwd=upstream)
        b.git_command(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '--quiet', '-m', 'inert fixture base'], cwd=upstream)
        base = b.git_command(['git', 'rev-parse', 'HEAD'], cwd=upstream)
        self.put(upstream / 'policy.txt', 'old\n')
        b.git_command(['git', 'add', 'policy.txt'], cwd=upstream)
        previous_root = self.root / 'prior-runtime'
        prior_series = previous_root / 'patches/series.json'
        b.write_json(prior_series, {'source_inventory': [{'path': 'policy.txt', 'sha256': b.sha(upstream / 'policy.txt')}], 'lock_sha256': b.sha(upstream / 'Cargo.lock')})
        previous = {'files': {'patches/series.json': b.sha(prior_series)}, 'patches': [{'path': 'patches/old.patch', 'sha256': 'old'}]}
        runtime = self.root / 'new-runtime'
        patch_file = runtime / 'patches/new.patch'
        self.put(patch_file, 'diff --git a/policy.txt b/policy.txt\n--- a/policy.txt\n+++ b/policy.txt\n@@ -1 +1 @@\n-base\n+new\n')
        value = {'patches': [{'path': 'patches/new.patch', 'sha256': b.sha(patch_file)}]}
        return upstream, base, previous_root / 'source-manifest.json', previous, runtime, value

    def test_changed_approved_policy_replays_fresh_base_and_preserves_verified_history(self):
        upstream, base, path, previous, runtime, value = self.cached_policy_fixture()
        before = b.staged_tree(upstream)
        cache = self.root / 'target/cache-marker'
        self.put(cache, 'retained compiled cache')
        with patch.object(b, 'BASE', base):
            b.refresh_cached_policy(upstream, path, previous, runtime, value, self.root / 'history')
        self.assertEqual((upstream / 'policy.txt').read_text(), 'new\n')
        history = list((self.root / 'history').iterdir())
        self.assertEqual(len(history), 1)
        self.assertEqual(b.staged_tree(history[0]), before)
        self.assertEqual(b.git_command(['git', 'rev-parse', 'HEAD'], cwd=upstream), base)
        self.assertEqual(cache.read_text(), 'retained compiled cache')

    def test_cached_policy_drift_denies_before_source_move_or_patch_replay(self):
        upstream, base, path, previous, runtime, value = self.cached_policy_fixture()
        self.put(upstream / 'policy.txt', 'unreviewed drift\n')
        with patch.object(b, 'BASE', base), self.assertRaisesRegex(InstallError, 'tree drift'):
            b.refresh_cached_policy(upstream, path, previous, runtime, value, self.root / 'history')
        self.assertEqual((upstream / 'policy.txt').read_text(), 'unreviewed drift\n')
        self.assertFalse((self.root / 'history').exists())

    def test_staged_source_detects_untracked_file_without_git_database(self):
        source = self.root / "source"
        self.put(source / "src.rs", "source")
        self.put(source / ".git/index", "not source")
        before = b.staged_tree(source)
        self.put(source / "new.rs", "new source")
        self.assertNotEqual(before, b.staged_tree(source))
        self.assertEqual(set(before), {"src.rs"})

    def test_dll_dependency_closure_and_missing_runtime(self):
        libs = self.root / "libs"
        self.put(libs / "libgcc_s_seh-1.dll", "inert fixture, never executable")
        binary = self.root / "bin/owner.exe"
        self.put(binary, "inert PE fixture")
        def dump(argv, **kwargs):
            name = Path(argv[-1]).name
            return "file format pei-x86-64\nDLL Name: KERNEL32.dll\n" + ("DLL Name: libgcc_s_seh-1.dll\n" if name == "owner.exe" else "")
        with self.assertRaisesRegex(InstallError, "unresolved non-system DLL"):
            b.collect_dlls([binary], binary.parent, "objdump", [], dump)
        report = b.collect_dlls([binary], binary.parent, "objdump", [libs], dump)
        self.assertIn("libgcc_s_seh-1.dll", report)
        self.assertEqual(b.sha(binary.parent / "libgcc_s_seh-1.dll"), b.sha(libs / "libgcc_s_seh-1.dll"))
        with self.assertRaisesRegex(InstallError, "not a Windows"):
            b.dll_imports(binary, "objdump", lambda *a, **k: "ELF")

    def test_npm_lock_rejects_missing_integrity_external_registry_and_wrong_version(self):
        value = {"lockfileVersion": 3, "packages": {"": {}, "node_modules/" + b.PI_PACKAGE: {"version": b.PI_VERSION, "resolved": "https://registry.npmjs.org/pi/-/pi.tgz", "integrity": "sha512-YWJj"}}}
        b.validate_npm_lock(value)
        for key, replacement in (("integrity", ""), ("resolved", "https://evil.invalid/pi.tgz"), ("version", "1.4.0"), ("link", True)):
            bad = copy.deepcopy(value)
            bad["packages"]["node_modules/" + b.PI_PACKAGE][key] = replacement
            with self.subTest(key=key), self.assertRaises(InstallError):
                b.validate_npm_lock(bad)

    def test_zip_escape_secret_case_collision_symlink_and_empty_rejected(self):
        for i, names in enumerate((["../escape"], ["C:/escape"], ["auth.json"], ["bin/a", "BIN/A"], [])):
            archive = self.root / f"bad{i}.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name in names:
                    z.writestr(name, "inert")
            target = self.root / f"extracted{i}"
            with self.subTest(names=names), self.assertRaises(InstallError):
                b.safe_extract_zip(archive, target)
            self.assertFalse(target.exists())
        archive = self.root / "link.zip"
        with zipfile.ZipFile(archive, "w") as z:
            item = zipfile.ZipInfo("link")
            item.external_attr = 0o120777 << 16
            z.writestr(item, "../escape")
        with self.assertRaisesRegex(InstallError, "link"):
            b.safe_extract_zip(archive, self.root / "link-out")

    def test_zip_copy_hash_drift_and_missing_entry_are_rejected_by_gate(self):
        # Reuse the installer suite's explicitly labelled Python toy package, never a real product.
        from test_craft import toy_bundle
        source = self.root / "toy-bundle"
        toy_bundle(source)
        archive = self.root / "bundle.zip"
        result = b.release_artifact(source, archive)
        extracted = b.safe_extract_zip(archive, self.root / "extracted")
        craft.bundle(extracted)
        self.assertEqual(b.sha(archive), result["sha256"])
        self.assertFalse(result["published"])
        self.assertIsNone(load_json(archive.with_suffix(".zip.upload-plan.json"))["release_url"])
        (extracted / "bin/owner.py").write_text("drift")
        with self.assertRaisesRegex(InstallError, "hash drift"):
            craft.bundle(extracted)
        (extracted / "bin/owner.py").unlink()
        with self.assertRaisesRegex(InstallError, "hash drift"):
            craft.bundle(extracted)

    def test_bundle_small_files_first_retains_bytes_and_reduces_journal_blob_rewrites(self):
        from test_craft import toy_bundle
        from configuration import Journal
        source = self.root / 'copy-source'
        toy_bundle(source)
        for rel, data in {'bin/large-fixture.dat': b'X' * 65536,
                          'docs/a.txt': b'a', 'docs/b.txt': b'b'}.items():
            target = source / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        manifest = load_json(source / 'craft-bundle.json')
        manifest['files'] = {p: h for p, h in b.tree(source).items() if p != 'craft-bundle.json'}
        b.write_json(source / 'craft-bundle.json', manifest)
        component = craft.bundle(source)
        journal = Journal(self.root / 'copy-journal')
        destination = self.root / 'copied'
        craft.install_bundle(component, destination, journal)
        order = [Path(item['path']).relative_to(destination).as_posix() for item in journal.data['files']]
        self.assertEqual(order, sorted(component['files'], key=lambda p: ((source / p).stat().st_size, p)))
        self.assertEqual(order[-1], 'bin/large-fixture.dat')
        self.assertEqual(b.tree(source), b.tree(destination))
        old_order = list(component['files'])
        old_rewrites = len(old_order) - old_order.index('bin/large-fixture.dat')
        self.assertGreater(old_rewrites, len(order) - order.index('bin/large-fixture.dat'))

    def test_bundle_late_write_failure_keeps_pending_recovery_and_user_edits(self):
        from test_craft import toy_bundle
        import configuration as cfg
        source = self.root / 'failure-source'
        toy_bundle(source)
        component = craft.bundle(source)
        destination = self.root / 'failed-copy'
        journal = cfg.Journal(self.root / 'failure-journal')
        ordered = sorted(component['files'], key=lambda p: ((source / p).stat().st_size, p))
        original_atomic = cfg.atomic
        def fail_last(path, data):
            if Path(path) == destination / ordered[-1]:
                raise InstallError('injected late destination write failure')
            original_atomic(path, data)
        with patch.object(cfg, 'atomic', fail_last), self.assertRaisesRegex(InstallError, 'injected late'):
            craft.install_bundle(component, destination, journal)
        persisted = load_json(journal.path)
        self.assertEqual(persisted['status'], 'pending')
        self.assertEqual(len(persisted['files']), len(ordered))
        edited = destination / ordered[0]
        edited.write_bytes(b'user edit must survive')
        result = cfg.restore_journal(journal.path, apply=True)
        self.assertEqual(edited.read_bytes(), b'user edit must survive')
        self.assertTrue(any(item.get('conflicts') for item in result))
        self.assertTrue(all(not (destination / rel).exists() for rel in ordered[1:]))

    def test_no_ambient_credentials_or_node_injection(self):
        with patch.dict(b.os.environ, {"SECRET_TOKEN": "inert", "NODE_OPTIONS": "inert", "NPM_CONFIG_SCRIPT_SHELL": "inert", "RUSTFLAGS": "inert", "PI_CODING_AGENT_DIR": "inert"}):
            env = b.isolated_env()
        for name in ("SECRET_TOKEN", "NODE_OPTIONS", "NPM_CONFIG_SCRIPT_SHELL", "RUSTFLAGS", "PI_CODING_AGENT_DIR"):
            self.assertNotIn(name, env)

    def test_other_platform_explicitly_unsupported(self):
        with patch.object(craft, "host", return_value={"os": "linux", "arch": "x86_64"}), self.assertRaisesRegex(InstallError, "unsupported platform"):
            b.build(argparse.Namespace())


if __name__ == "__main__":
    unittest.main()
