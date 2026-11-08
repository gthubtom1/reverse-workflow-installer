"""P4: offline transaction behavior for the optional standalone Pi shell guard."""
import contextlib
import copy
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import test_installer as fixtures
from test_installer import metadata
import workflow as w
import shell_guard as sg
import install as cli
from configuration import Journal, atomic, digest, encode_json, load_json
from versions import InstallError, resolve


class ShellGuardTests(unittest.TestCase):
    setUp = fixtures.Fixture.setUp
    tearDown = fixtures.Fixture.tearDown
    install = fixtures.Fixture.install

    def package(self, root=None, version=None):
        root = root or self.base / "standalone-guard"
        entry = load_json(self.source / "components.json")["shell_guard"]
        version = version or entry["version"]
        for name in entry["required_files"]:
            atomic(root / name, ("fixture " + name).encode())
        atomic(root / "package.json", encode_json({"name": entry["package_name"], "version": version, "pi": {"extensions": ["./index.ts"]}}))
        atomic(root / "index.ts", b'import { register } from "./runtime.mjs";')
        return root

    def only(self, local=True):
        self.args.components = "shell-guard"
        self.args.project = None
        self.args.reverse_root = None
        if local:
            self.args.shell_guard_root = str(self.package())

    def fetch(self, url):
        entry = load_json(self.source / "components.json")["shell_guard"]
        if url.endswith("/commits/" + entry["release_ref"]):
            return {"sha": entry["commit"], "commit": {"tree": {"sha": "c" * 40}}}
        return metadata(url)

    def plan(self):
        return w.make_plan(self.args, self.fetch)

    def fake_run(self, argv, *, cwd, env=None):
        args = [str(a) for a in argv]
        if "clone" in args:
            target = Path(args[-1])
            if target.name == "agent-plugins-shell-guard":
                self.calls.append(args)
                self.package(target / "plugins/pi/shell-guard")
                return ""
        if "rev-parse" in args and "agent-plugins-shell-guard" in str(cwd):
            self.calls.append(args)
            entry = load_json(self.source / "components.json")["shell_guard"]
            return ("c" * 40 if "HEAD^{tree}" in args else entry["commit"])
        return fixtures.Fixture.fake_run(self, argv, cwd=cwd, env=env)

    def exe(self, name="es.exe"):
        path = self.base / name
        atomic(path, b"CLI fixture")
        path.chmod(0o755)
        return path

    def settings(self, **extra):
        settings = load_json(self.agent / "settings.json")
        settings.update(extra)
        atomic(self.agent / "settings.json", encode_json(settings))
        return settings

    def test_legacy_all_and_resolver_default_do_not_select_guard(self):
        plan = self.plan()
        self.assertNotIn("shell_guard", plan["scope"]["components"])
        self.assertNotIn("shell_guard", resolve(load_json(self.source / "components.json"), metadata))
        receipt = w.install(plan, self.args)
        receipt["scope"].pop("components")
        atomic(self.root / ".installer/receipt.json", encode_json(receipt))
        self.assertEqual(w.receipt_components(receipt), ["rea", "spec_kit", "reverse"])
        self.assertNotIn("shell_guard", self.plan()["scope"]["components"])

    def test_optional_flag_adds_shell_guard_to_all(self):
        self.args.with_shell_guard = True
        plan = self.plan()
        self.assertEqual(set(plan["scope"]["components"]), set(w.ALL_COMPONENTS))
        receipt = w.install(plan, self.args)
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(receipt["installer_version"], "0.6.1")
        self.assertEqual(receipt["adapter_version"], "0.2.0")
        self.assertEqual(load_json(Path(receipt["adapter"]["root"]) / "package.json")["version"], "0.6.1")

    def test_pi_only_and_guard_options_require_selection(self):
        for client in ("none", "codex", "claude"):
            self.args.client = client
            self.args.with_shell_guard = True
            with self.subTest(client=client), self.assertRaises(InstallError):
                self.plan()
        self.args.client = "pi"
        self.args.with_shell_guard = False
        for key, value in (("shell_guard_root", str(self.package())), ("everything_es", str(self.exe())), ("replace_shell_guard_root", str(self.base / "dev"))):
            setattr(self.args, key, value)
            with self.subTest(key=key), self.assertRaises(InstallError):
                self.plan()
            setattr(self.args, key, None)
        self.assertFalse(self.calls)

    def test_local_only_no_metadata_no_package_manager_and_static_limits(self):
        self.only()
        self.args.everything_es = str(self.exe())
        before = self.settings(shellGuard={"enabled": False, "custom": 42, "everything": {"extra": "keep"}})
        plan = w.make_plan(self.args, lambda url: self.fail("unexpected metadata lookup"))
        self.assertEqual(len(plan["components"]["shell_guard"]["tree_hash"]), 64)
        receipt = w.install(plan, self.args)
        self.assertEqual(self.calls, [])
        settings = load_json(self.agent / "settings.json")
        self.assertEqual(settings["defaultModel"], before["defaultModel"])
        self.assertEqual(settings["shellGuard"], {"enabled": False, "custom": 42, "everything": {"extra": "keep", "esPath": self.args.everything_es}})
        self.assertEqual(settings["packages"], ["user-package", self.args.shell_guard_root])
        self.assertEqual(load_json(self.agent / "mcp.json")["future"], 7)
        self.assertIsNone(receipt["adapter"]["root"])
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertIn("shell-guard", str(w.accept(self.root)["unverified"]))

    def test_everything_gui_and_autostart_are_frozen_and_merged(self):
        self.only()
        self.args.everything_es = str(self.exe())
        self.args.everything_gui = str(self.exe("Everything.exe"))
        self.args.everything_autostart = True
        plan = self.plan()
        self.assertEqual(plan["scope"]["everything_gui"], str(Path(self.args.everything_gui).resolve()))
        self.assertTrue(plan["scope"]["everything_autostart"])
        self.assertEqual(plan["everything_gui_identity"]["path"], str(Path(self.args.everything_gui).resolve()))
        receipt = w.install(plan, self.args)
        settings = load_json(self.agent / "settings.json")
        everything = settings["shellGuard"]["everything"]
        self.assertEqual(everything["esPath"], self.args.everything_es)
        self.assertEqual(everything["guiPath"], self.args.everything_gui)
        self.assertTrue(everything["autostart"])
        self.assertEqual(receipt["shell_guard_config"]["guiPath"], self.args.everything_gui)
        self.assertTrue(receipt["shell_guard_config"]["autostart"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_everything_autostart_requires_gui(self):
        self.only()
        self.args.everything_autostart = True
        with self.assertRaisesRegex(InstallError, "everything-autostart"):
            self.plan()

    def test_remote_pin_and_separate_clone_directories(self):
        self.only(local=False)
        self.args.components = "shell-guard"
        seen = []
        def fetch(url):
            seen.append(url)
            return self.fetch(url)
        plan = w.make_plan(self.args, fetch)
        self.assertEqual(len(seen), 1)
        release_ref = load_json(self.source / "components.json")["shell_guard"]["release_ref"]
        self.assertTrue(any(url.endswith("/commits/" + release_ref) for url in seen))
        receipt = w.install(plan, self.args)
        clone_targets = [c[-1] for c in self.calls if "clone" in c]
        self.assertEqual(len(set(clone_targets)), 1)
        self.assertTrue(w.verify(self.root)["ok"])
        self.calls.clear()
        w.install(self.plan(), self.args)
        self.assertFalse(any("clone" in c or "checkout" in c for c in self.calls))

    def test_unpublished_tag_and_missing_tree_fail_without_fallback(self):
        self.only(local=False)
        seen = []
        def unavailable(url):
            seen.append(url)
            raise InstallError("HTTP 404 unpublished")
        with self.assertRaisesRegex(InstallError, "404"):
            w.make_plan(self.args, unavailable)
        release_ref = load_json(self.source / "components.json")["shell_guard"]["release_ref"]
        self.assertEqual(seen, ["https://api.github.com/repos/gthubtom1/agent-plugins/commits/" + release_ref])
        with self.assertRaisesRegex(InstallError, "tree"):
            w.make_plan(self.args, lambda url: {"sha": "b" * 40})
        self.assertFalse(self.calls)

    def test_local_requires_exact_identity_entry_runtime_and_src(self):
        self.only()
        root = Path(self.args.shell_guard_root)
        entry = load_json(self.source / "components.json")["shell_guard"]
        for name in entry["required_files"]:
            with self.subTest(missing=name):
                path = root / name
                held = path.with_name(path.name + ".held")
                path.rename(held)
                try:
                    with self.assertRaisesRegex(InstallError, "缺少"):
                        self.plan()
                finally:
                    held.rename(path)
        pkg = root / "package.json"
        original = load_json(pkg)
        for change in ({"name": "hub"}, {"version": "0.1.0"}, {"pi": {"extensions": ["./index.ts", "../other.ts"]}}, {"pi": {"extensions": ["./index.ts"], "skills": ["./skills"]}}, {"dependencies": {"runtime": "*"}}, {"optionalDependencies": {"runtime": "*"}}):
            with self.subTest(change=change):
                atomic(pkg, encode_json({**original, **change}))
                with self.assertRaises(InstallError):
                    self.plan()
        atomic(pkg, encode_json(original))
        self.assertFalse(self.calls)

    def test_plan_drift_and_tampering_rejected_before_any_commands(self):
        self.only()
        original = self.plan()
        for key in ("tree_hash", "root", "mode", "name", "version", "plugin_dir", "repository"):
            with self.subTest(key=key):
                plan = copy.deepcopy(original)
                plan["components"]["shell_guard"].pop(key)
                with self.assertRaises(InstallError):
                    w.install(plan, self.args)
        atomic(Path(self.args.shell_guard_root) / "src/policy.mjs", b"changed")
        with self.assertRaisesRegex(InstallError, "漂移"):
            w.install(original, self.args)
        self.assertFalse(self.calls)
        self.assertEqual(load_json(self.agent / "settings.json"), self.before)

    def test_remote_plan_rejects_unfrozen_or_wrong_fields(self):
        self.only(local=False)
        original = self.plan()
        for key, value in (("commit", "main"), ("repository_tree", None), ("version", "0.1.0"), ("ref", "main"), ("mode", "local"), ("plugin_dir", "."), ("required_files", ["index.ts"])):
            with self.subTest(key=key):
                plan = copy.deepcopy(original)
                plan["components"]["shell_guard"][key] = value
                with self.assertRaises(InstallError):
                    w.install(plan, self.args)
        self.assertFalse(self.calls)

    def test_wrong_checkout_commit_tree_or_dirty_files_cannot_activate(self):
        self.only(local=False)
        for failure in ("commit", "tree", "dirty"):
            with self.subTest(failure=failure):
                def wrong(argv, **kwargs):
                    args = list(map(str, argv))
                    if "agent-plugins-shell-guard" in str(kwargs.get("cwd")):
                        if "rev-parse" in args and failure == "commit" and "HEAD" in args:
                            return "d" * 40
                        if "HEAD^{tree}" in args and failure == "tree":
                            return "d" * 40
                        if "status" in args and failure == "dirty":
                            return " M index.ts"
                    return self.fake_run(argv, **kwargs)
                with patch.object(w, "run", wrong), self.assertRaises(InstallError):
                    w.install(self.plan(), self.args)
                self.assertFalse((self.root / ".installer/receipt.json").exists())
                self.assertEqual(load_json(self.agent / "settings.json"), self.before)

    def test_existing_old_install_optin_update_preserves_project_then_restores(self):
        first = self.install()
        atomic(self.project / "notes.txt", b"user project")
        self.args.with_shell_guard = True
        self.args.shell_guard_root = str(self.package())
        second = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual((self.project / "notes.txt").read_bytes(), b"user project")
        settings = load_json(self.agent / "settings.json")
        settings["packages"].append("later")
        settings["model"] = "later-model"
        atomic(self.agent / "settings.json", encode_json(settings))
        w.restore(self.root, apply=True)
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])
        settings = load_json(self.agent / "settings.json")
        self.assertIn("later", settings["packages"])
        self.assertEqual(settings["model"], "later-model")
        self.assertNotIn(second["shell_guard"]["root"], settings["packages"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_selected_local_guard_persists_on_update_without_optin(self):
        self.only()
        first = self.install()
        self.args.components = "shell-guard"
        self.args.shell_guard_root = None
        self.args.with_shell_guard = False
        plan = self.plan()
        self.assertEqual(plan["scope"]["shell_guard_root"], first["shell_guard"]["root"])
        second = w.install(plan, self.args)
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(first["shell_guard"]["tree_hash"], second["shell_guard"]["tree_hash"])
        self.assertEqual(load_json(self.agent / "settings.json")["packages"].count(first["shell_guard"]["root"]), 1)
        self.args.components = "rea"
        self.assertIn("shell_guard", self.plan()["scope"]["components"])

    def test_update_rejects_active_drift(self):
        self.only()
        self.install()
        atomic(Path(self.args.shell_guard_root) / "runtime.mjs", b"changed")
        self.assertFalse(w.verify(self.root)["ok"])
        plan = self.plan()  # Even re-plan must not bless drift in the active receipt.
        with self.assertRaisesRegex(InstallError, "活动 shell-guard 漂移"):
            w.install(plan, self.args)

    def test_everything_path_must_be_absolute_existing_executable(self):
        self.only()
        for value in ("es.exe", str(self.base / "missing.exe"), str(self.base)):
            with self.subTest(value=value):
                self.args.everything_es = value
                with self.assertRaises(InstallError):
                    self.plan()
        self.args.everything_es = str(self.exe("not-cli.txt"))
        if os.name == "nt":
            with self.assertRaises(InstallError):
                self.plan()
        self.assertFalse(self.calls)

    def test_everything_hash_and_settings_drift_reject_apply(self):
        self.only()
        exe = self.exe()
        self.args.everything_es = str(exe)
        plan = self.plan()
        atomic(exe, b"changed CLI")
        with self.assertRaisesRegex(InstallError, "Everything CLI"):
            w.install(plan, self.args)
        self.assertFalse(self.calls)

    def test_existing_everything_config_is_preserved_or_conflicts(self):
        self.only()
        old = str(self.exe())
        self.settings(shellGuard={"enabled": False, "everything": {"esPath": old}, "other": 4})
        receipt = self.install()
        self.assertIsNone(receipt["shell_guard_config"])
        self.assertEqual(load_json(self.agent / "settings.json")["shellGuard"]["everything"]["esPath"], old)
        self.args.everything_es = str(self.exe("other-es.exe"))
        with self.assertRaisesRegex(InstallError, "用户配置"):
            self.plan()

    def test_managed_everything_update_and_restore_preserve_other_settings(self):
        self.only()
        self.args.everything_es = str(self.exe())
        first = self.install()
        self.args.everything_es = str(self.exe("es2.exe"))
        second = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        settings = load_json(self.agent / "settings.json")
        settings["shellGuard"]["later"] = True
        settings["shellGuard"]["everything"]["limit"] = 12
        atomic(self.agent / "settings.json", encode_json(settings))
        w.restore(self.root, apply=True)
        settings = load_json(self.agent / "settings.json")
        self.assertEqual(settings["shellGuard"]["everything"]["esPath"], first["shell_guard_config"]["esPath"])
        self.assertTrue(settings["shellGuard"]["later"])
        self.assertEqual(settings["shellGuard"]["everything"]["limit"], 12)
        self.assertNotEqual(first["transaction"], second["transaction"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_restore_preserves_later_user_es_path_as_conflict(self):
        self.only()
        self.args.everything_es = str(self.exe())
        self.install()
        settings = load_json(self.agent / "settings.json")
        settings["shellGuard"]["everything"]["esPath"] = "later-user-path"
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(f["conflicts"] for f in result["files"]))
        self.assertEqual(load_json(self.agent / "settings.json")["shellGuard"]["everything"]["esPath"], "later-user-path")

    def migration(self, object_registration=False):
        self.only()
        old = self.package(self.base / "dev-guard", "0.1.0")
        registration = {"source": str(old), "userMeta": 3} if object_registration else str(old)
        self.settings(packages=["user-package", registration], shellGuard={"enabled": False, "everything": {"esPath": "user-owned"}})
        self.args.replace_shell_guard_root = str(old)
        return old, registration

    def test_exact_migration_freezes_hash_and_restores_registration(self):
        old, registration = self.migration(object_registration=True)
        old_hash = sg.tree_hash(old)
        plan = self.plan()
        self.assertEqual(plan["shell_guard_migration"]["tree_hash"], old_hash)
        w.install(plan, self.args)
        self.assertTrue(w.verify(self.root)["ok"])
        settings = load_json(self.agent / "settings.json")
        self.assertIn({"source": self.args.shell_guard_root, "userMeta": 3}, settings["packages"])
        self.assertNotIn(registration, settings["packages"])
        self.assertEqual(sg.tree_hash(old), old_hash)
        settings["model"] = "later"
        atomic(self.agent / "settings.json", encode_json(settings))
        w.restore(self.root, apply=True)
        settings = load_json(self.agent / "settings.json")
        self.assertIn(registration, settings["packages"])
        self.assertEqual(settings["model"], "later")
        self.assertFalse(settings["shellGuard"]["enabled"])

    def test_migration_requires_exact_registration_and_rejects_drift(self):
        old, registration = self.migration()
        plan = self.plan()
        atomic(old / "src/policy.mjs", b"dev edit")
        with self.assertRaisesRegex(InstallError, "迁移源.*漂移"):
            w.install(plan, self.args)
        self.assertFalse(self.calls)
        self.settings(packages=["user-package"])
        with self.assertRaisesRegex(InstallError, "恰好匹配"):
            self.plan()
        self.settings(packages=["user-package", registration, registration])
        with self.assertRaisesRegex(InstallError, "重复"):
            self.plan()

    def test_duplicates_other_copies_filters_hubs_direct_extensions_rejected(self):
        self.only()
        root = self.args.shell_guard_root
        other = self.package(self.base / "other-guard")
        hub = self.base / "hub"
        self.package(hub / "plugins/pi/shell-guard")
        cases = [
            {"packages": [root, root]},
            {"packages": [str(other)]},
            {"packages": [{"source": root, "extensions": ["index.ts"]}]},
            {"packages": [str(hub)]},
            {"packages": ["npm:@toti/pi-shell-guard"]},
            {"packages": ["git:github.com/gthubtom1/agent-plugins"]},
            {"packages": ["npm:agent-plugins@1.1.0"]},
            {"packages": [], "extensions": [str(Path(root) / "index.ts")]},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.settings(packages=[], extensions=[])
                self.settings(**case)
                with self.assertRaises(InstallError):
                    self.plan()
        self.assertFalse(self.calls)

    def test_failed_activation_rolls_back_migration_and_everything_and_receipt(self):
        old, registration = self.migration()
        # Keep the original user esPath; rollback must restore exact settings.
        self.args.everything_es = None
        before = load_json(self.agent / "settings.json")
        plan = self.plan()
        original = Journal.write
        def fail(journal, path, data, kind="file", **kwargs):
            if Path(path).name == "receipt.json":
                raise InstallError("fixture failure after settings activation")
            return original(journal, path, data, kind, **kwargs)
        with patch.object(Journal, "write", fail), self.assertRaises(InstallError):
            w.install(plan, self.args)
        self.assertEqual(load_json(self.agent / "settings.json"), before)
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertTrue(old.is_dir())
        self.assertIn(registration, before["packages"])

    def test_verify_requires_receipt_hash_identity_and_registration(self):
        self.only()
        receipt = self.install()
        path = self.root / ".installer/receipt.json"
        for section, key in (("hashes", "shell_guard_sha256"), ("shell_guard", "tree_hash"), ("shell_guard", "mode"), ("paths", "shell_guard")):
            with self.subTest(section=section, key=key):
                changed = copy.deepcopy(receipt)
                changed[section].pop(key)
                atomic(path, encode_json(changed))
                self.assertFalse(w.verify(self.root)["ok"])
        atomic(path, encode_json(receipt))
        self.settings(packages=["user-package"])
        self.assertFalse(w.verify(self.root)["ok"])

    def test_restore_after_user_edit_of_migrated_registration_never_resurrects_old_copy(self):
        old, registration = self.migration(object_registration=True)
        self.install()
        settings = load_json(self.agent / "settings.json")
        edited = next(p for p in settings["packages"] if isinstance(p, dict))
        edited["userMeta"] = 99
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        restored = load_json(self.agent / "settings.json")
        self.assertIn(edited, restored["packages"])
        self.assertNotIn(registration, restored["packages"])
        self.assertTrue(any("replaced-registration" in str(item["conflicts"]) for item in result["files"]))

    def test_restore_does_not_resurrect_old_dev_copy_after_user_removes_new_registration(self):
        old, registration = self.migration()
        self.install()
        self.settings(packages=["user-package"])
        result = w.restore(self.root, apply=True)
        self.assertEqual(load_json(self.agent / "settings.json")["packages"], ["user-package"])
        self.assertTrue(any(item["conflicts"] for item in result["files"]))

    def test_successful_migration_freezes_original_settings_and_cli_on_failed_activation(self):
        self.only()
        old = self.package(self.base / "dev-guard", "0.1.0")
        self.args.replace_shell_guard_root = str(old)
        self.args.everything_es = str(self.exe())
        before = self.settings(packages=[str(old)], shellGuard={"custom": 1, "everything": {"maxResults": 9}})
        original = Journal.write
        def fail(journal, path, data, kind="file", **kwargs):
            if Path(path).name == "receipt.json":
                raise InstallError("fixture failure")
            return original(journal, path, data, kind, **kwargs)
        with patch.object(Journal, "write", fail), self.assertRaises(InstallError):
            self.install()
        self.assertEqual(load_json(self.agent / "settings.json"), before)
        self.assertFalse((self.root / ".installer/receipt.json").exists())

    def test_settings_plan_drift_and_everything_identity_verify_drift(self):
        self.only()
        plan = self.plan()
        self.settings(later="user config")
        with self.assertRaisesRegex(InstallError, "漂移"):
            w.install(plan, self.args)
        self.assertFalse(self.calls)
        self.args.everything_es = str(self.exe())
        self.install()
        atomic(Path(self.args.everything_es), b"CLI edit")
        Path(self.args.everything_es).chmod(0o755)
        self.assertFalse(w.verify(self.root)["ok"])
        with self.assertRaisesRegex(InstallError, "活动 shell-guard 漂移"):
            self.install()

    def test_linked_package_root_and_linked_source_file_rejected(self):
        self.only()
        root = Path(self.args.shell_guard_root)
        link = self.base / "guard-link"
        try:
            link.symlink_to(root, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("symbolic links unavailable: " + type(exc).__name__)
        self.args.shell_guard_root = str(link)
        with self.assertRaisesRegex(InstallError, "链接"):
            self.plan()
        self.args.shell_guard_root = str(root)
        (root / "extra-link.mjs").symlink_to(root / "runtime.mjs")
        with self.assertRaisesRegex(InstallError, "链接"):
            self.plan()
        self.assertFalse(self.calls)

    def test_late_package_migration_source_and_cli_drift_roll_back_activation(self):
        self.only()
        old = self.package(self.base / "old-dev", "0.1.0")
        self.args.replace_shell_guard_root = str(old)
        self.args.everything_es = str(self.exe())
        before = self.settings(packages=[str(old)], shellGuard={"custom": 1})
        targets = [Path(self.args.shell_guard_root) / "src/policy.mjs", old / "src/policy.mjs", Path(self.args.everything_es)]
        original = Journal.write
        for target in targets:
            with self.subTest(target=target.name):
                def drift(journal, path, data, kind="file", **kwargs):
                    result = original(journal, path, data, kind, **kwargs)
                    if Path(path) == Path(self.args.everything_es) or Path(target) == Path(self.args.everything_es):
                        Path(self.args.everything_es).chmod(0o755)
                    if Path(path) == self.agent / "settings.json":
                        atomic(target, b"changed after activation")
                    return result
                plan = self.plan()
                with patch.object(Journal, "write", drift), self.assertRaisesRegex(InstallError, "漂移"):
                    w.install(plan, self.args)
                self.assertEqual(load_json(self.agent / "settings.json"), before)
                self.assertFalse((self.root / ".installer/receipt.json").exists())

    def test_relative_bare_local_hub_and_guard_duplicates_rejected(self):
        self.only()
        local = self.package(self.agent / "local-guard")
        self.args.shell_guard_root = str(local)
        self.settings(packages=[str(local), "local-guard"])
        with self.assertRaisesRegex(InstallError, "重复"):
            self.plan()
        hub = self.agent / "hub"
        self.package(hub / "plugins/pi/shell-guard")
        self.settings(packages=["hub"])
        with self.assertRaisesRegex(InstallError, "hub"):
            self.plan()

    def test_other_named_package_direct_extension_is_rejected(self):
        self.only()
        other = self.package(self.base / "custom-dev-name", "0.1.0")
        for source in (str(other / "index.ts"), str(other)):
            with self.subTest(source=source):
                self.settings(extensions=[source])
                with self.assertRaisesRegex(InstallError, "直接 extensions"):
                    self.plan()
        self.assertFalse(self.calls)

    def test_restore_new_packages_field_removes_guard_but_keeps_user_additions(self):
        self.only()
        atomic(self.agent / "settings.json", encode_json({"model": "x"}))
        receipt = self.install()
        settings = load_json(self.agent / "settings.json")
        settings["packages"].append("later-user-package")
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        settings = load_json(self.agent / "settings.json")
        self.assertEqual(settings, {"model": "x", "packages": ["later-user-package"]})
        self.assertNotIn(receipt["shell_guard"]["root"], settings["packages"])
        self.assertFalse(any(item["conflicts"] for item in result["files"]))

    def test_restore_conflict_keeps_active_transaction_until_successful_retry(self):
        self.only()
        self.args.everything_es = str(self.exe())
        first = self.install()
        self.args.everything_es = str(self.exe("new-es.exe"))
        second = self.install()
        settings = load_json(self.agent / "settings.json")
        settings["shellGuard"]["everything"]["esPath"] = "later-user-value"
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(item["conflicts"] for item in result["files"]))
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], second["transaction"])
        settings = load_json(self.agent / "settings.json")
        settings["shellGuard"]["everything"]["esPath"] = second["shell_guard_config"]["esPath"]
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, transaction=second["transaction"], apply=True)
        self.assertFalse(any(item["conflicts"] for item in result["files"]))
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_frozen_cli_rejects_relative_everything_override_even_for_same_file(self):
        self.only()
        exe = self.exe()
        self.args.everything_es = str(exe)
        path = self.base / "plan.json"
        atomic(path, encode_json(self.plan()))
        relative = os.path.relpath(exe, Path.cwd())
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["install", "--root", str(self.root), "--plan-file", str(path), "--everything-es", relative, "--apply"])
        self.assertEqual(code, 1)
        self.assertFalse((self.root / ".installer/receipt.json").exists())

    @unittest.skipUnless(os.name == "nt", "Windows slash/case aliases")
    def test_windows_equivalent_everything_slashes_preserve_user_spelling(self):
        self.only()
        exe = self.exe()
        forward = exe.as_posix()
        backward = str(exe.resolve())
        self.assertNotEqual(forward, backward)
        self.assertTrue(sg.same_path(forward, backward))
        self.assertTrue(sg.same_path(forward.upper(), backward))
        for spelling in (forward, backward):
            with self.subTest(spelling=spelling):
                self.settings(shellGuard={"everything": {"esPath": spelling, "maxResults": 17}, "custom": True})
                self.args.everything_es = backward if spelling == forward else forward
                plan = self.plan()
                receipt = w.install(plan, self.args)
                settings = load_json(self.agent / "settings.json")
                self.assertEqual(settings["shellGuard"]["everything"]["esPath"], spelling)
                self.assertEqual(settings["shellGuard"]["everything"]["maxResults"], 17)
                self.assertTrue(w.verify(self.root)["ok"])
                self.assertTrue(sg.same_path(receipt["shell_guard_config"]["esPath"], spelling))
                receipt["shell_guard_config"]["esPath"] = spelling
                receipt["shell_guard_config"]["executable"]["path"] = spelling
                atomic(self.root / ".installer/receipt.json", encode_json(receipt))
                self.assertTrue(w.verify(self.root)["ok"])

    def test_equivalent_everything_dot_path_preserves_spelling_and_real_conflicts_reject(self):
        self.only()
        exe = self.exe()
        spelling = str(exe.parent) + os.sep + "." + os.sep + exe.name
        self.settings(shellGuard={"everything": {"esPath": spelling}, "custom": 3})
        self.args.everything_es = str(exe)
        self.install()
        self.assertEqual(load_json(self.agent / "settings.json")["shellGuard"]["everything"]["esPath"], spelling)
        self.assertTrue(w.verify(self.root)["ok"])
        other = self.exe("other.exe")
        settings = load_json(self.agent / "settings.json")
        settings["shellGuard"]["everything"]["esPath"] = str(other)
        atomic(self.agent / "settings.json", encode_json(settings))
        self.assertFalse(w.verify(self.root)["ok"])
        with self.assertRaisesRegex(InstallError, "用户配置"):
            self.plan()

    def test_partial_restore_retry_accepts_fields_already_at_before_value(self):
        self.only()
        self.args.everything_es = str(self.exe())
        first = self.install()
        self.args.shell_guard_root = str(self.package(self.base / "guard-next"))
        self.args.everything_es = str(self.exe("next-es.exe"))
        second = self.install()
        new_root = second["shell_guard"]["root"]
        settings = load_json(self.agent / "settings.json")
        settings["packages"] = [{"source": item, "userMeta": 1} if item == new_root else item for item in settings["packages"]]
        settings["unrelated"] = "keep"
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(item["conflicts"] for item in result["files"]))
        settings = load_json(self.agent / "settings.json")
        self.assertEqual(settings["shellGuard"]["everything"]["esPath"], first["shell_guard_config"]["esPath"])
        settings["packages"] = [new_root if isinstance(item, dict) and item.get("source") == new_root else item for item in settings["packages"]]
        atomic(self.agent / "settings.json", encode_json(settings))
        result = w.restore(self.root, transaction=second["transaction"], apply=True)
        self.assertFalse(any(item["conflicts"] for item in result["files"]))
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])
        self.assertEqual(load_json(self.agent / "settings.json")["unrelated"], "keep")
        self.assertTrue(w.verify(self.root)["ok"])

    def test_frozen_cli_plan_replay_without_resolution_and_conflict_rejection(self):
        self.only()
        path = self.base / "plan.json"
        atomic(path, encode_json(self.plan()))
        with patch.object(w, "resolve", side_effect=AssertionError("must not refetch")), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["install", "--root", str(self.root), "--plan-file", str(path), "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue(w.verify(self.root)["ok"])
        with contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["update", "--root", str(self.root), "--plan-file", str(path), "--shell-guard-root", str(self.base / "other"), "--apply"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
