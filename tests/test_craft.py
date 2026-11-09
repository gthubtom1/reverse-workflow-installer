"""Offline Craft package behavior. Toy executable artifacts are NOT product bundles."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_installer as fixtures
from test_installer import REPO, metadata
import install as cli
import workflow as w
import craft as cr
from configuration import Journal, atomic, digest, encode_json, load_json
from versions import InstallError, resolve


def toy_bundle(root, version="0.1.0"):
    files = {name: ("fixture " + name).encode() for name in cr.REQUIRED}
    files.update({"bin/owner.py": b'import json, os, sys\nprint(json.dumps({"args":sys.argv[1:], "pi":os.environ["CRAFT_PI_ENTRY"], "root":os.environ["CRAFT_BUNDLE_ROOT"]}))\n',
                  "bin/driver.py": b'raise SystemExit("fixture driver only")\n', "patches/policy.patch": b"fixture patch\n",
                  "docs/entry.md": b"Toy owner echoes args, never starts Pi/provider. Paths are relative.\n"})
    for name, data in files.items():
        atomic(root / name, data)
    manifest = {"name": "craft-pi-bundle", "version": version, "contract": copy.deepcopy(cr.CONTRACT),
                "base_commit": cr.BASE_COMMIT, "pi": {"version": "1.5.0", "protocol": "rpc"},
                "artifact": {**cr.host(), "source_commit": "a" * 40, "build_source": "offline toy fixture; not a product build"},
                "runtime": {"entry_protocol": "docs/entry.md", "entry": "bin/owner.py", "entry_kind": "python", "driver": "bin/driver.py", "driver_kind": "python", "required_files": ["docs/entry.md"]},
                "patches": [{"path": "patches/policy.patch", "sha256": digest(files["patches/policy.patch"])}],
                "files": {name: digest(data) for name, data in files.items()}}
    atomic(root / cr.MANIFEST, encode_json(manifest))
    return manifest


def toy_reverse_contract(root):
    for name in cr.REVERSE_FILES:
        atomic(root / name, ("offline R46 fixture: " + name + "\n").encode())
    atomic(root / "VERSION", b"1.9.0\n")
    descriptor = {"schema_version": 1, "contract_id": "reverse.r46.execution-backend", "contract_version": 1,
                  "min_reverse_version": "1.9.0", "capabilities": list(cr.REVERSE_CAPABILITIES),
                  "required_files": [{"path": name, "sha256": digest((root / name).read_bytes())} for name in cr.REVERSE_FILES]}
    atomic(root / cr.REVERSE_DESCRIPTOR, encode_json(descriptor))
    return descriptor


class CraftTests(unittest.TestCase):
    def setUp(self):
        fixtures.Fixture.setUp(self)
        self.reverse_descriptor = toy_reverse_contract(self.reverse)
        for name in ("craft.py", "configuration.py", "versions.py"):
            atomic(self.source / "scripts" / name, (REPO / "scripts" / name).read_bytes())
        self.bundle = self.base / "bundle source 中文"
        self.manifest = toy_bundle(self.bundle)
        self.pi_distribution = self.base / "standalone-pi"
        package = self.pi_distribution / "node_modules/@earendil-works/pi-coding-agent"
        self.pi_entry = package / "dist/bundle/cli.js"
        # Real Python execution of an inert version fixture; no official runtime/provider.
        atomic(self.pi_entry, b'print("1.5.0")\n')
        atomic(package / "package.json", encode_json({"name": "@earendil-works/pi-coding-agent", "version": "1.5.0", "dependencies": {"toy-dependency": "1.0.0"}}))
        self.pi_dependency = self.pi_distribution / "node_modules/toy-dependency/runtime.js"
        atomic(self.pi_dependency, b"// inert dependency fixture\n")
        atomic(self.pi_dependency.parent / "package.json", encode_json({"name": "toy-dependency", "version": "1.0.0"}))
        atomic(self.pi_distribution / "pi-runtime.json", encode_json({"schema_version": 1, "name": "official-pi-standalone", "version": "1.5.0", "package_root": package.relative_to(self.pi_distribution).as_posix(), "dependency_root": "node_modules", "entry": self.pi_entry.relative_to(self.pi_distribution).as_posix(), "dependency_closure": "self-contained-node-modules-v1", "files": {}}))
        self.refresh_pi()
        self.args.components = "reverse,spec-kit,craft"
        self.args.craft_pi_distribution = str(self.pi_distribution)
        self.args.craft_bundle = str(self.bundle)
        self.args.craft_pi_node = str(Path(sys.executable).resolve())
        self.args.craft_pi_entry = str(self.pi_entry)
        self.args.craft_pi_version = "1.5.0"

    tearDown = fixtures.Fixture.tearDown
    plan = fixtures.Fixture.plan
    install = fixtures.Fixture.install

    def fake_run(self, argv, *, cwd, env=None):
        if str(argv[-1]) == "--version" and str(argv[0]) == str(Path(sys.executable).resolve()):
            self.calls.append([str(a) for a in argv])
            return subprocess.run([str(x) for x in argv], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
        return fixtures.Fixture.fake_run(self, argv, cwd=cwd, env=env)

    def refresh_pi(self):
        value = load_json(self.pi_distribution / "pi-runtime.json")
        value["files"] = {name: sha for name, sha in cr.inventory(self.pi_distribution).items() if name != "pi-runtime.json"}
        atomic(self.pi_distribution / "pi-runtime.json", encode_json(value))

    def save_manifest(self, value):
        atomic(self.bundle / cr.MANIFEST, encode_json(value))

    def entry(self, receipt, *arguments):
        return subprocess.run([sys.executable, "-B", str(Path(receipt["craft"]["resources"]) / "entry.py"), *arguments],
                              cwd=self.base, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_default_all_does_not_enable_craft(self):
        self.args.components = "all"
        for key in ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_pi_version"):
            setattr(self.args, key, None)
        plan = self.plan()
        self.assertNotIn("craft", plan["components"])
        self.assertNotIn("craft", resolve(load_json(self.source / "components.json"), metadata))
        receipt = w.install(plan, self.args)
        self.assertIsNone(receipt["craft"])
        self.assertFalse(any("craft-pi" in str(x) for x in load_json(self.agent / "settings.json")["packages"]))

    def test_dependency_and_client_fail_before_resolution(self):
        for components, client in (("craft", "pi"), ("reverse,craft", "pi"), ("reverse,spec-kit,craft", "codex")):
            with self.subTest(components=components, client=client):
                self.args.components, self.args.client = components, client
                with self.assertRaises(InstallError):
                    self.plan()
                self.assertEqual(self.calls, [])

    def test_unpublished_remote_has_no_fallback(self):
        self.args.craft_bundle = None
        with self.assertRaisesRegex(InstallError, "unsupported artifact until published"):
            self.plan()
        with self.assertRaisesRegex(InstallError, "unsupported until"):
            resolve(load_json(self.source / "components.json"), lambda url: self.fail(url), components=["craft"])

    def test_whole_bundle_exact_copy_and_unique_entry_resources(self):
        before_mcp = (self.agent / "mcp.json").read_bytes()
        receipt = self.install()
        copied = Path(receipt["craft"]["root"])
        self.assertNotEqual(copied, self.bundle)
        self.assertEqual(cr.inventory(copied), cr.inventory(self.bundle))
        for name in cr.inventory(self.bundle):
            self.assertEqual((copied / name).read_bytes(), (self.bundle / name).read_bytes())
        self.assertEqual(receipt["schema_version"], 1)
        self.assertEqual(receipt["installer_version"], "0.7.0")
        self.assertEqual((self.agent / "mcp.json").read_bytes(), before_mcp)
        self.assertFalse((self.agent / "AGENTS.md").exists())
        self.assertFalse((self.agent / "agents").exists())
        self.assertTrue(w.verify(self.root)["ok"])
        checked = self.entry(receipt, "--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn(str(copied / "bin/owner.py"), json.loads(checked.stdout)["command"])
        self.assertFalse(list(Path(receipt["craft"]["resources"]).rglob("__pycache__")))
        self.assertFalse(any("npm" in str(c) for c in self.calls))
        self.assertEqual(len(cr.registration(load_json(self.agent / "settings.json"), self.agent, (receipt["craft"]["resources"],))), 1)

    def test_portable_entry_invokes_exact_installed_artifact_with_explicit_pi(self):
        receipt = self.install()
        result = self.entry(receipt, "--execute", "--", "--toy-argument", "中文 value")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["args"], ["--toy-argument", "中文 value"])
        self.assertEqual(data["pi"], str(self.pi_entry.resolve()))
        self.assertEqual(data["root"], receipt["craft"]["root"])

    def test_relocated_bundle_all_relative_references_still_work(self):
        moved = self.base / "moved unpacked package"
        shutil.copytree(self.bundle, moved)
        self.args.craft_bundle = str(moved)
        receipt = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(self.entry(receipt, "--check").returncode, 0)

    def test_bundle_drift_missing_added_dirty_files_reject_before_activation(self):
        for operation in ("edit", "missing", "extra"):
            with self.subTest(operation=operation):
                toy_bundle(self.bundle)
                plan = self.plan()
                p = self.bundle / "bin/driver.py"
                if operation == "edit": atomic(p, b"drift")
                elif operation == "missing": p.unlink()
                else: atomic(self.bundle / "dirty-build-output.txt", b"not frozen")
                self.calls.clear()
                with self.assertRaisesRegex(InstallError, "inventory/hash drift"):
                    w.install(plan, self.args)
                self.assertFalse((self.root / ".installer/receipt.json").exists())
                self.assertEqual(self.calls, [])
                (self.bundle / "dirty-build-output.txt").unlink(missing_ok=True)

    def test_moved_source_root_rejects_frozen_plan(self):
        plan = self.plan()
        moved = self.base / "new-bundle-root"
        shutil.copytree(self.bundle, moved)
        plan["scope"]["craft_bundle"] = str(moved)
        with self.assertRaisesRegex(InstallError, "root/content drift"):
            w.validate_plan(plan)

    def test_manifest_required_identity_and_artifact_paths_fail_closed(self):
        mutations = [lambda m: m.pop("files"), lambda m: m.pop("patches"),
                     lambda m: m.update(base_commit="b" * 40),
                     lambda m: m["artifact"].update(os="unsupported"),
                     lambda m: m["contract"].update(min_reader=2),
                     lambda m: m["contract"].update(required_capabilities=["unknown"]),
                     lambda m: m["runtime"].update(entry="../source.rs"),
                     lambda m: m["runtime"].update(entry="C:/source.rs"),
                     lambda m: m["runtime"].update(entry_kind="cargo-source"),
                     lambda m: m["patches"][0].update(sha256="f" * 64),
                     lambda m: m["pi"].update(protocol="json"),
                     lambda m: m.update(runtime=[]), lambda m: m.update(artifact=[]),
                     lambda m: m["runtime"].pop("entry_protocol"),
                     lambda m: m["runtime"].update(entry="Cargo.lock", entry_kind="python"),
                     lambda m: m["files"].update({"bin/owner.py": "fakehash"})]
        for mutate in mutations:
            m = copy.deepcopy(self.manifest)
            mutate(m)
            self.save_manifest(m)
            with self.subTest(manifest=m), self.assertRaises(InstallError):
                cr.bundle(self.bundle)

    def test_linked_root_and_file_rejected(self):
        link = self.base / "bundle-link"
        try:
            link.symlink_to(self.bundle, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaisesRegex(InstallError, "symlink"):
            cr.bundle(link)
        link.unlink()
        p = self.bundle / "bin/driver.py"
        p.unlink()
        p.symlink_to(self.pi_entry)
        with self.assertRaisesRegex(InstallError, "symlink"):
            cr.bundle(self.bundle)

    def test_explicit_pi_version_mismatch_and_file_drift(self):
        self.args.craft_pi_version = "1.4.0"
        with self.assertRaisesRegex(InstallError, "version"):
            self.plan()
        self.args.craft_pi_version = "1.5.0"
        atomic(self.pi_entry, b'print("1.4.0")\n')
        self.refresh_pi()
        with self.assertRaisesRegex(InstallError, "--version mismatch"):
            self.plan()
        atomic(self.pi_entry, b'print("1.5.0")\n')
        self.refresh_pi()
        plan = self.plan()
        atomic(self.pi_entry, b'print("1.5.0") # changed\n')
        with self.assertRaisesRegex(InstallError, "inventory/hash drift"):
            w.install(plan, self.args)

    def test_missing_runtime_never_falls_back_to_path_pi(self):
        for option in ("craft_pi_node", "craft_pi_entry"):
            original = getattr(self.args, option)
            setattr(self.args, option, str(self.base / "missing"))
            with self.assertRaisesRegex(InstallError, "runtime file missing"):
                self.plan()
            setattr(self.args, option, original)

    def test_receipt_capability_and_artifact_drift_denies_verify_and_entry(self):
        receipt = self.install()
        target = Path(receipt["craft"]["root"]) / "bin/owner.py"
        original = target.read_bytes()
        atomic(target, b"user changed artifact")
        self.assertFalse(w.verify(self.root)["ok"])
        self.assertNotEqual(self.entry(receipt, "--check").returncode, 0)
        atomic(target, original)
        receipt["craft_contract"]["min_reader"] = 999
        atomic(self.root / ".installer/receipt.json", encode_json(receipt))
        self.assertFalse(w.verify(self.root)["ok"])
        self.assertNotEqual(self.entry(receipt, "--check").returncode, 0)
        with self.assertRaisesRegex(InstallError, "unsupported"):
            w.restore(self.root, apply=True)

    def test_installed_runtime_hash_drift_denies_entry(self):
        receipt = self.install()
        atomic(self.pi_entry, b'print("1.5.0") # later edit\n')
        self.assertFalse(w.verify(self.root)["ok"])
        self.assertNotEqual(self.entry(receipt, "--check").returncode, 0)

    def test_registered_duplicate_filtered_foreign_and_direct_resources_reject(self):
        receipt = self.install()
        initial = load_json(self.agent / "settings.json")
        wanted = receipt["craft"]["resources"]
        variants = []
        duplicate = copy.deepcopy(initial); duplicate["packages"].append(wanted); variants.append(duplicate)
        filtered = copy.deepcopy(initial); filtered["packages"] = [{"source": x, "skills": []} if x == wanted else x for x in filtered["packages"]]; variants.append(filtered)
        foreign = copy.deepcopy(initial); foreign["packages"].append("npm:" + cr.PACKAGE_NAME); variants.append(foreign)
        direct = copy.deepcopy(initial); direct["skills"].append(str(Path(wanted) / "skills/reconstruction-execution")); variants.append(direct)
        parent = copy.deepcopy(initial); parent["packages"].append(str(Path(wanted).parent)); variants.append(parent)
        for settings in variants:
            atomic(self.agent / "settings.json", encode_json(settings))
            self.assertFalse(w.verify(self.root)["ok"])
            with self.assertRaises(InstallError): self.plan()

    def test_existing_old_receipt_stays_readable_and_craft_optin_update_preserves_source(self):
        self.args.components = "reverse,spec-kit"
        values = {key: getattr(self.args, key) for key in ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_pi_version")}
        for key in values: setattr(self.args, key, None)
        old = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertIsNone(old["craft"])
        self.args.with_craft = True
        for key, value in values.items(): setattr(self.args, key, value)
        first = self.install()
        self.args.with_craft = False
        for key in values: setattr(self.args, key, None)
        plan = self.plan()
        self.assertIn("craft", plan["scope"]["components"])
        self.assertEqual(plan["scope"]["craft_bundle"], str(self.bundle))
        self.assertIsNotNone(plan["craft_update"]["old"])
        second = w.install(plan, self.args)
        self.assertEqual(first["craft"]["root"], second["craft"]["root"])
        self.assertEqual(first["schema_version"], old["schema_version"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_update_parallel_bundle_and_restore_exact_old_receipt(self):
        first = self.install()
        original_receipt = (self.root / ".installer/receipt.json").read_bytes()
        second_source = self.base / "bundle-v2"
        toy_bundle(second_source, "0.1.1")
        self.args.craft_bundle = str(second_source)
        second = self.install()
        self.assertNotEqual(first["craft"]["root"], second["craft"]["root"])
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(item["conflicts"] for item in result["files"]))
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), original_receipt)
        self.assertTrue(w.verify(self.root)["ok"])
        with self.assertRaisesRegex(InstallError, "最新到最旧"):
            w.restore(self.root, second["transaction"], apply=True)

    def test_restore_preserves_unrelated_settings_and_user_data(self):
        receipt = self.install()
        data = self.project / "user-data.txt"
        atomic(data, b"user data keep")
        settings = load_json(self.agent / "settings.json")
        settings["userExtra"] = {"ownedBy": "user"}
        settings["packages"].append("new-user-package")
        atomic(self.agent / "settings.json", encode_json(settings))
        restored = w.restore(self.root, apply=True)
        self.assertFalse(any(item["conflicts"] for item in restored["files"]))
        self.assertEqual(data.read_bytes(), b"user data keep")
        settings = load_json(self.agent / "settings.json")
        self.assertEqual(settings["userExtra"], {"ownedBy": "user"})
        self.assertIn("new-user-package", settings["packages"])
        self.assertNotIn(receipt["craft"]["resources"], settings["packages"])
        self.assertTrue((self.bundle / "bin/owner.py").is_file())

    def test_restore_user_instructions_conflict_keeps_receipt_and_retry_succeeds(self):
        receipt = self.install()
        receipt_bytes = (self.root / ".installer/receipt.json").read_bytes()
        instructions = Path(receipt["craft"]["resources"]) / "builder-instructions.md"
        original = instructions.read_bytes()
        atomic(instructions, b"user instruction edits")
        restored = w.restore(self.root, apply=True)
        self.assertTrue(any(x["conflicts"] for x in restored["files"]))
        self.assertEqual(instructions.read_bytes(), b"user instruction edits")
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), receipt_bytes)
        atomic(instructions, original)
        restored = w.restore(self.root, apply=True)
        self.assertFalse(any(x["conflicts"] for x in restored["files"]))

    def test_restore_user_registration_edit_conflict_keeps_active_receipt(self):
        receipt = self.install()
        old_receipt = (self.root / ".installer/receipt.json").read_bytes()
        settings = load_json(self.agent / "settings.json")
        wanted = receipt["craft"]["resources"]
        settings["packages"] = [{"source": wanted, "skills": []} if x == wanted else x for x in settings["packages"]]
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(x["conflicts"] for x in result["files"]))
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), old_receipt)
        self.assertIn({"source": wanted, "skills": []}, load_json(self.agent / "settings.json")["packages"])

    def test_restore_modified_bundle_preserves_bytes_and_receipt(self):
        receipt = self.install()
        artifact = Path(receipt["craft"]["root"]) / "bin/owner.py"
        atomic(artifact, b"later local edits")
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(item["conflicts"] for item in result["files"]))
        self.assertEqual(artifact.read_bytes(), b"later local edits")
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], receipt["transaction"])

    def test_late_activation_failure_rolls_back_new_resources_and_settings(self):
        before = (self.agent / "settings.json").read_bytes()
        original = Journal.write
        def fail(journal, target, data, *args, **kwargs):
            if Path(target) == self.root / ".installer/receipt.json":
                raise InstallError("fixture receipt activation failure")
            return original(journal, target, data, *args, **kwargs)
        with patch.object(Journal, "write", fail), self.assertRaisesRegex(InstallError, "activation failure"):
            self.install()
        self.assertEqual((self.agent / "settings.json").read_bytes(), before)
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertFalse(list((self.root / "versions").rglob("entry.py")))
        self.assertTrue((self.bundle / "bin/owner.py").is_file())
        self.assertTrue(self.install()["installed"])

    def test_pending_recovery_restores_new_managed_files_and_conflict_blocks(self):
        target = self.root / "versions/interrupted/craft-bundle/bin/owner.py"
        journal = Journal(self.root / ".installer/transactions/interrupted")
        journal.write(target, b"managed artifact")
        atomic(target, b"user edited interrupted artifact")
        with self.assertRaisesRegex(InstallError, "后续修改"):
            w.recover_pending_transactions(self.root)
        self.assertEqual(target.read_bytes(), b"user edited interrupted artifact")
        atomic(target, b"managed artifact")
        self.assertEqual(w.recover_pending_transactions(self.root), ["interrupted"])
        self.assertFalse(target.exists())

    def test_frozen_cli_replay_no_metadata_and_mismatched_option_rejects(self):
        plan = self.plan()
        frozen = self.base / "plan.json"
        atomic(frozen, encode_json(plan))
        argv = ["install", "--root", str(self.root), "--plan-file", str(frozen), "--apply"]
        with patch.object(w, "resolve", side_effect=AssertionError("unexpected lookup")), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli.main(argv), 0)
        self.assertTrue(w.verify(self.root)["ok"])
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli.main([*argv, "--craft-pi-version", "1.4.0"]), 1)

    def test_explicit_flag_adds_craft_to_core_selection_only(self):
        self.args.components = "all"
        self.args.with_craft = True
        self.assertEqual(w.scope(self.args)["components"], ["rea", "spec_kit", "reverse", "craft"])

    def test_pending_unknown_capability_refuses_any_rollback(self):
        target = self.root / "versions/interrupted/craft-bundle/owned.txt"
        journal = Journal(self.root / ".installer/transactions/interrupted")
        journal.data["craft_contract"] = {**cr.CONTRACT, "min_reader": 999}
        journal.write(target, b"managed")
        with self.assertRaisesRegex(InstallError, "unsupported"):
            w.recover_pending_transactions(self.root)
        self.assertEqual(target.read_bytes(), b"managed")
        with self.assertRaisesRegex(InstallError, "unsupported"):
            w.restore(self.root, "interrupted", apply=True)
        self.assertEqual(target.read_bytes(), b"managed")

    def test_failed_upgrade_preserves_old_receipt_bundle_and_registration(self):
        first = self.install()
        receipt_bytes = (self.root / ".installer/receipt.json").read_bytes()
        settings_bytes = (self.agent / "settings.json").read_bytes()
        second = self.base / "new-bundle"
        toy_bundle(second, "0.1.1")
        self.args.craft_bundle = str(second)
        original = Journal.write
        def fail(journal, target, data, *args, **kwargs):
            if Path(target) == self.root / ".installer/receipt.json":
                raise InstallError("upgrade activation failure")
            return original(journal, target, data, *args, **kwargs)
        with patch.object(Journal, "write", fail), self.assertRaisesRegex(InstallError, "upgrade activation"):
            self.install()
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), receipt_bytes)
        self.assertEqual((self.agent / "settings.json").read_bytes(), settings_bytes)
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(self.entry(first, "--check").returncode, 0)

    def test_late_source_drift_rolls_back_before_receipt(self):
        original = cr.merge_settings
        before = (self.agent / "settings.json").read_bytes()
        def drift(*args):
            result = original(*args)
            atomic(self.bundle / "bin/driver.py", b"late source mutation")
            return result
        with patch.object(cr, "merge_settings", drift), self.assertRaisesRegex(InstallError, "inventory/hash drift"):
            self.install()
        self.assertEqual((self.agent / "settings.json").read_bytes(), before)
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertFalse(list((self.root / "versions").rglob("entry.py")))

    def test_later_resource_edits_block_update_without_overwrite(self):
        receipt = self.install()
        instructions = Path(receipt["craft"]["resources"]) / "builder-instructions.md"
        atomic(instructions, b"my later instructions")
        with self.assertRaisesRegex(InstallError, "Active Craft drift"):
            self.install()
        self.assertEqual(instructions.read_bytes(), b"my later instructions")
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], receipt["transaction"])

    def test_plan_freezes_instructions_lib_and_new_resource_file(self):
        paths = [self.source / "adapters/craft-pi/builder-instructions.md", self.source / "scripts/craft.py", self.source / "adapters/craft-pi/new-resource.md"]
        for target in paths:
            with self.subTest(target=target):
                plan = self.plan()
                before = target.read_bytes() if target.exists() else None
                atomic(target, (before or b"") + b"\nchanged after plan\n")
                self.calls.clear()
                with self.assertRaisesRegex(InstallError, "resource source inventory/hash drift"):
                    w.install(plan, self.args)
                self.assertEqual(self.calls, [])
                self.assertFalse((self.root / ".installer/receipt.json").exists())
                if before is None: target.unlink()
                else: atomic(target, before)

    def test_late_resource_source_edit_rolls_back_before_activation(self):
        original = cr.merge_settings
        before = (self.agent / "settings.json").read_bytes()
        def drift(*args):
            result = original(*args)
            atomic(self.source / "adapters/craft-pi/builder-instructions.md", b"late resource source mutation")
            return result
        with patch.object(cr, "merge_settings", drift), self.assertRaisesRegex(InstallError, "resource source inventory/hash drift"):
            self.install()
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertEqual((self.agent / "settings.json").read_bytes(), before)

    def test_pi_dependency_drift_entry_unchanged_rejects_plan_apply_verify_and_entry(self):
        plan = self.plan()
        unchanged = self.pi_entry.read_bytes()
        before = self.pi_dependency.read_bytes()
        atomic(self.pi_dependency, b"dependency drift; entry unchanged")
        with self.assertRaisesRegex(InstallError, "distribution/dependency.*drift"):
            w.install(plan, self.args)
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        atomic(self.pi_dependency, before)
        receipt = self.install()
        atomic(self.pi_dependency, b"later dependency drift")
        self.assertEqual(self.pi_entry.read_bytes(), unchanged)
        self.assertFalse(w.verify(self.root)["ok"])
        result = self.entry(receipt, "--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("distribution/dependency", result.stderr)
        # Updating a self-description cannot silently replace the frozen identity either.
        self.refresh_pi()
        self.assertFalse(w.verify(self.root)["ok"])
        self.assertNotEqual(self.entry(receipt, "--check").returncode, 0)

    def test_unmanifested_or_unresolved_pi_distribution_is_unsupported(self):
        manifest = self.pi_distribution / "pi-runtime.json"
        before = manifest.read_bytes()
        manifest.unlink()
        with self.assertRaisesRegex(InstallError, "runtime unsupported"):
            self.plan()
        atomic(manifest, before)
        package_json = self.pi_entry.parents[2] / "package.json"
        value = load_json(package_json)
        value["dependencies"]["not-contained"] = "1.0.0"
        atomic(package_json, encode_json(value))
        self.refresh_pi()
        with self.assertRaisesRegex(InstallError, "closure unresolved"):
            self.plan()

    def test_r46_old_reverse_missing_and_corrupt_descriptor_rejected(self):
        path = self.reverse / cr.REVERSE_DESCRIPTOR
        before = path.read_bytes()
        atomic(self.reverse / "VERSION", b"1.8.2\n")
        with self.assertRaisesRegex(InstallError, "needs-contract.*minimum"):
            self.plan()
        atomic(self.reverse / "VERSION", b"1.9.0\n")
        path.unlink()
        with self.assertRaisesRegex(InstallError, "needs-contract"):
            self.plan()
        atomic(path, b"{broken")
        with self.assertRaisesRegex(InstallError, "needs-contract"):
            self.plan()
        atomic(path, before)
        self.args.reverse_root = None
        with self.assertRaisesRegex(InstallError, "needs-contract.*--reverse-root"):
            self.plan()
        self.assertEqual(self.calls, [])

    def test_r46_descriptor_unknown_unsafe_duplicate_and_minimum_rejected(self):
        mutations = [lambda d: d.update(schema_version=2), lambda d: d.update(schema_version=True),
                     lambda d: d.update(contract_version=2), lambda d: d.update(contract_id="other"),
                     lambda d: d["capabilities"].append("unknown"), lambda d: d["capabilities"].pop(),
                     lambda d: d.update(min_reverse_version="garbage"), lambda d: d.update(min_reverse_version="1.8.2"),
                     lambda d: d.update(min_reverse_version="1.10.0"), lambda d: d.update(extra_scope="allow-all"),
                     lambda d: d["required_files"].pop(),
                     lambda d: d["required_files"].__setitem__(1, copy.deepcopy(d["required_files"][0])),
                     lambda d: d["required_files"][0].update(path="../escape.md"),
                     lambda d: d["required_files"][0].update(path="C:/absolute.md"),
                     lambda d: d["required_files"][0].update(path="skills/other.md"),
                     lambda d: d["required_files"][0].update(extra="unsafe"),
                     lambda d: d["required_files"][0].update(sha256="0" * 64)]
        for change in mutations:
            value = copy.deepcopy(self.reverse_descriptor)
            change(value)
            atomic(self.reverse / cr.REVERSE_DESCRIPTOR, encode_json(value))
            with self.subTest(value=value), self.assertRaisesRegex(InstallError, "needs-contract"):
                self.plan()
        atomic(self.reverse / cr.REVERSE_DESCRIPTOR, b'{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(InstallError, "duplicate"):
            self.plan()
        self.assertFalse((self.root / ".installer/receipt.json").exists())

    def test_r46_file_missing_or_symlink_escape_rejected(self):
        target = self.reverse / cr.REVERSE_FILES[0]
        original = target.read_bytes()
        target.unlink()
        with self.assertRaisesRegex(InstallError, "needs-contract"):
            self.plan()
        outside = self.base / "outside-contract.md"
        atomic(outside, original)
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlink unavailable")
        with self.assertRaisesRegex(InstallError, "needs-contract.*symlink"):
            self.plan()

    def test_r46_freezes_descriptor_version_and_all_four_files(self):
        for name in (cr.REVERSE_DESCRIPTOR, "VERSION", *cr.REVERSE_FILES):
            target = self.reverse / name
            before = target.read_bytes()
            plan = self.plan()
            self.assertEqual(plan["schema_version"], 2)
            atomic(target, before + b"\n")
            self.calls.clear()
            with self.subTest(name=name), self.assertRaisesRegex(InstallError, "needs-contract"):
                w.install(plan, self.args)
            self.assertEqual(self.calls, [])
            self.assertFalse((self.root / ".installer/receipt.json").exists())
            atomic(target, before)

    def test_r46_late_contract_drift_rolls_back_before_receipt(self):
        original = cr.merge_settings
        before = (self.agent / "settings.json").read_bytes()
        def drift(*args):
            result = original(*args)
            atomic(self.reverse / cr.REVERSE_DESCRIPTOR, encode_json(self.reverse_descriptor) + b"\n")
            return result
        with patch.object(cr, "merge_settings", drift), self.assertRaisesRegex(InstallError, "needs-contract.*drift"):
            self.install()
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertEqual((self.agent / "settings.json").read_bytes(), before)

    def test_r46_receipt_drift_verify_and_entry_deny_before_bad_task(self):
        receipt = self.install()
        self.assertEqual(receipt["craft_reverse_contract"], cr.reverse_contract(self.reverse))
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(self.entry(receipt, "--check").returncode, 0)
        for name in (cr.REVERSE_DESCRIPTOR, *cr.REVERSE_FILES):
            target = self.reverse / name
            before = target.read_bytes()
            atomic(target, before + b"\n")
            with self.subTest(name=name):
                self.assertFalse(w.verify(self.root)["ok"])
                result = self.entry(receipt, "--execute", "--", "must-not-start")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("needs-contract", result.stderr)
            atomic(target, before)
        # Resealing edited content does not replace the frozen descriptor identity.
        atomic(self.reverse / cr.REVERSE_FILES[0], b"new rule bytes")
        descriptor = copy.deepcopy(self.reverse_descriptor)
        descriptor["required_files"][0]["sha256"] = digest((self.reverse / cr.REVERSE_FILES[0]).read_bytes())
        atomic(self.reverse / cr.REVERSE_DESCRIPTOR, encode_json(descriptor))
        self.assertFalse(w.verify(self.root)["ok"])
        self.assertNotEqual(self.entry(receipt, "--check").returncode, 0)

    def test_r46_noncraft_core_plan_schema1_unaffected(self):
        self.args.components = "reverse,spec-kit"
        for name in ("craft_bundle", "craft_pi_node", "craft_pi_entry", "craft_pi_distribution", "craft_pi_version"):
            setattr(self.args, name, None)
        (self.reverse / cr.REVERSE_DESCRIPTOR).unlink()
        atomic(self.reverse / "VERSION", b"1.8.2\n")
        plan = self.plan()
        self.assertEqual(plan["schema_version"], 1)
        self.assertIsNone(plan["craft_reverse_contract"])
        w.validate_plan(plan)
        self.assertTrue(w.install(plan, self.args)["installed"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_craft_schema2_is_actually_rejected_by_original_061_plan_reader(self):
        plan = self.plan()
        self.assertEqual(plan["schema_version"], 2)
        self.assertEqual(plan["adapter_version"], "0.2.0")
        old = self.base / "original-reader"
        old.mkdir()
        for name in ("workflow.py", "configuration.py", "versions.py", "shell_guard.py", "package_utils.py"):
            # Use the immutable public v0.6.1 commit, not the local integration
            # history (whose tree is equal but whose commit is absent in CI).
            shown = subprocess.run(["git", "-C", str(REPO), "show", "02341811920dc419eb4af27eb836f8e683eddc96:scripts/" + name], capture_output=True, check=True)
            atomic(old / name, shown.stdout)
        frozen = self.base / "schema2-plan.json"
        atomic(frozen, encode_json(plan))
        code = 'import json,sys; import workflow\nfrom versions import InstallError\ntry:\n workflow.validate_plan(json.load(open(sys.argv[1],encoding="utf-8")))\nexcept InstallError as e:\n print(str(e)); sys.exit(0 if "schema/adapter" in str(e) else 2)\nsys.exit(3)\n'
        result = subprocess.run([sys.executable, "-B", "-c", code, str(frozen)], cwd=old, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("schema/adapter", result.stdout)
        with self.assertRaisesRegex(InstallError, "schema"):
            w.validate_plan({**plan, "schema_version": 1})

    def test_remote_pin_parser_rejects_moved_tag_and_missing_hash(self):
        from acquire_craft import OWN, REVERSE, UPSTREAM
        record = {"schema_version": 1,
                  "craft": {"repository": OWN, "tag": "craft-pi-v0.1.0", "commit": "c" * 40, "asset": "toy.zip", "asset_id": 31, "sha256": "d" * 64, "manifest_sha256": "e" * 64},
                  "reverse": {"repository": REVERSE, "tag": "v1.9.0", "commit": "f" * 40, "archive_sha256": "a" * 64, "descriptor_sha256": "b" * 64},
                  "upstream": {"repository": UPSTREAM, "commit": cr.BASE_COMMIT}}
        def fetch(url):
            key = "craft" if "reverse-workflow-installer" in url else "reverse"
            item = record[key]
            if "/commits/" in url: return {"sha": item["commit"]}
            release = {"id": 1, "tag_name": item["tag"], "draft": False, "prerelease": False,
                       "html_url": item["repository"] + "/releases/tag/" + item["tag"], "assets": []}
            if key == "craft":
                release["assets"] = [{"id":31, "name":"toy.zip", "digest":"sha256:" + item["sha256"],
                                       "url":"https://api.github.com/repos/gthubtom1/reverse-workflow-installer/releases/assets/31",
                                       "browser_download_url":OWN + "/releases/download/craft-pi-v0.1.0/toy.zip"}]
            return release
        self.assertIn("metadata-verified", cr.pinned_release(record, fetch)["status"])
        def moved(url):
            return {"sha": "e" * 40} if "/commits/" in url else fetch(url)
        with self.assertRaisesRegex(InstallError, "moved tag"):
            cr.pinned_release(record, moved)
        def missing_hash(url):
            value = fetch(url)
            if value.get("assets"): value["assets"][0].pop("digest")
            return value
        with self.assertRaisesRegex(InstallError, "SHA256"):
            cr.pinned_release(record, missing_hash)
        record["craft"]["repository"] = UPSTREAM
        with self.assertRaisesRegex(InstallError, "repository"):
            cr.pinned_release(record, fetch)


if __name__ == "__main__":
    unittest.main()
