"""Focused offline routing ownership tests; no profile, setup, provider or service calls."""
import copy
import os
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch

from test_installer import Fixture, atomic, cli, digest, encode_json, load_json, w, InstallError
import routing_ownership as ro
from configuration import Journal, restore_journal


class RoutingOwnership(unittest.TestCase):
    fake_run = Fixture.fake_run
    plan = Fixture.plan
    install = Fixture.install

    def setUp(self):
        Fixture.setUp(self)
        self.home_patch = patch.object(ro, "_user_home", return_value=self.base / "isolated-user")
        self.home_patch.start()
        self.args.client = "codex"
        self.args.components = "reverse"
        self.args.project = None
        self.config = self.agent / "config.toml"
        self.original = b'# root comment\r\nmodel = "keep"\r\n[mcp_servers.user]\r\ncommand="user"\r\n'
        atomic(self.config, self.original)

    def tearDown(self):
        self.home_patch.stop()
        Fixture.tearDown(self)

    def skill(self, name="craft-anything", root=None, folder=None):
        root = root or (self.base / "isolated-user/.agents/skills")
        path = root / (folder or name) / "SKILL.md"
        atomic(path, ("---\nname: " + name + "\ndescription: Upstream broad workflow\n---\nOfficial body stays unchanged.\n").encode())
        return path.resolve()

    def exclude(self, *paths):
        self.args.exclude_workflow_skill = [str(p) for p in paths]

    def test_fresh_conflict_and_exact_identity_restrictions(self):
        skill = self.skill()
        with self.assertRaisesRegex(InstallError, "--exclude-workflow-skill") as caught:
            self.plan()
        self.assertIn(str(skill), str(caught.exception))
        self.assertEqual(self.config.read_bytes(), self.original)
        unknown = self.skill("user-reverse-helper")
        for path in (unknown, self.skill("reverse-workflow", folder="user-router"), self.skill("rea", root=self.base / "outside")):
            self.exclude(path)
            with self.assertRaises(InstallError):
                self.plan()
        self.assertFalse(self.root.exists())

    def test_install_verify_repeat_and_update_keep_official_bytes(self):
        skill = self.skill()
        original_skill = skill.read_bytes()
        self.exclude(skill)
        plan = self.plan()
        self.assertEqual(plan["config_inputs"][str(skill)], digest(original_skill))
        first = w.install(plan, self.args)
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(skill.read_bytes(), original_skill)
        routing = first["routing_ownership"]
        self.assertEqual(routing["route_owner"], "reverse.native-router")
        self.assertEqual(routing["disabled_skills"][0]["ownership"], "installer")
        self.assertIn("tool companion", routing["upstream_craft"])
        self.exclude()
        before = self.config.read_bytes()
        second = self.install()
        self.assertEqual(second["routing_ownership"], routing)
        self.assertEqual(before, self.config.read_bytes())
        self.assertEqual(skill.read_bytes(), original_skill)
        self.assertFalse(any("setup" in c for c in self.calls))
        self.assertFalse(any(e["kind"] == "codex-skills" for e in load_json(second["backup"])["files"]))
        self.assertFalse(any(f["conflicts"] for f in w.restore(self.root, apply=True)["files"]))
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertFalse(any(f["conflicts"] for f in w.restore(self.root, apply=True)["files"]))
        self.assertNotIn("skills", tomllib.loads(self.config.read_text(encoding="utf-8")))

    def test_native_disabled_external_entry_is_not_claimed(self):
        skill = self.skill("rea")
        self.exclude(skill)
        disabled = ro.disable(self.original, [str(skill)])
        atomic(self.config, disabled)
        self.exclude()
        first = self.install()
        self.assertEqual(first["routing_ownership"]["disabled_skills"][0]["ownership"], "external")
        self.assertTrue(w.verify(self.root)["ok"])
        w.restore(self.root, apply=True)
        self.assertEqual(self.config.read_bytes(), disabled)

    def test_plan_source_drift_new_conflict_and_legacy_plan_refused(self):
        skill = self.skill()
        self.exclude(skill)
        plan = self.plan()
        atomic(skill, skill.read_bytes() + b"source drift\n")
        with self.assertRaisesRegex(InstallError, "drift|漂移"):
            w.install(plan, self.args)
        plan = self.plan()
        new_skill = self.skill("rea-agents", root=self.agent / "skills", folder="nested/vendor/rea")
        with self.assertRaisesRegex(InstallError, "--exclude-workflow-skill"):
            w.install(plan, self.args)
        new_skill.unlink()
        legacy = copy.deepcopy(plan)
        legacy.pop("routing_ownership")
        legacy["config_inputs"].pop(str(skill))
        with self.assertRaisesRegex(InstallError, "Legacy plan"):
            w.install(legacy, self.args)
        self.assertFalse(self.root.exists())
        self.assertFalse(any("setup" in c for c in self.calls))

    def test_verify_reenable_new_setup_source_drift_and_accept_fail_early(self):
        skill = self.skill()
        self.exclude(skill)
        self.install()
        before = self.config.read_bytes()
        atomic(self.config, before.replace(b"enabled = false", b"enabled = true"))
        result = w.verify(self.root)
        self.assertFalse(result["ok"])
        self.exclude()
        with self.assertRaisesRegex(InstallError, "--exclude-workflow-skill"):
            self.plan()
        self.calls.clear()
        self.assertFalse(w.accept(self.root)["ok"])
        self.assertFalse(any("doctor" in c or "--hint" in c or "-Hint" in c for c in self.calls))
        atomic(self.config, before)
        new_skill = self.skill("rea", root=self.agent / "skills")
        self.assertFalse(w.verify(self.root)["ok"])
        new_skill.unlink()
        atomic(skill, skill.read_bytes() + b"upstream changed\n")
        self.assertFalse(w.verify(self.root)["ok"])

    def test_restore_preserves_other_skills_mcp_user_edits_and_extra_fields(self):
        skill = self.skill()
        other = self.agent / "skills/user/SKILL.md"
        extra = b'\r\n[[skills.config]] # user entry\r\npath = ' + encode_json(str(other)).strip() + b'\r\nenabled = true\r\nnote = "keep"\r\n'
        enabled = b'\r\n[[skills.config]] # official entry\r\npath = ' + encode_json(str(skill)).strip() + b'\r\nenabled = true # preserve note\r\ncustom = "unchanged"\r\n'
        atomic(self.config, self.original + extra + enabled)
        self.exclude(skill)
        self.install()
        text = self.config.read_bytes().replace(b'model = "keep"', b'model = "later"')
        later = b'\r\n[mcp_servers.later]\r\ncommand="later-user-command"\r\n'
        atomic(self.config, text + later)
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(f["conflicts"] for f in result["files"]), result)
        restored = self.config.read_bytes()
        self.assertEqual(restored, (self.original + extra + enabled).replace(b'model = "keep"', b'model = "later"') + later)

    def test_restore_conflict_retains_user_changed_disable_and_receipt(self):
        skill = self.skill()
        self.exclude(skill)
        self.install()
        changed = self.config.read_bytes().replace(b"enabled = false", b"enabled = true")
        atomic(self.config, changed)
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(f["conflicts"] for f in result["files"]))
        self.assertEqual(self.config.read_bytes(), changed)
        self.assertTrue((self.root / ".installer/receipt.json").exists())

    def test_restore_combined_rea_journal_does_not_revert_other_configuration(self):
        skill = self.skill()
        self.args.components = "rea,reverse"
        self.exclude(skill)
        self.install()
        later = b'\r\n[mcp_servers.later]\r\ncommand="keep"\r\n'
        atomic(self.config, self.config.read_bytes() + later)
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(f["conflicts"] for f in result["files"]), result)
        parsed = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertNotIn("rea", parsed["mcp_servers"])
        self.assertIn("later", parsed["mcp_servers"])
        self.assertNotIn("skills", parsed)
        self.assertIn(b"# root comment", self.config.read_bytes())

    def test_non_codex_and_unselected_reverse_reject_explicit_flag_only(self):
        skill = self.skill()
        self.exclude(skill)
        for client, components in (("pi", "reverse"), ("claude", "reverse"), ("codex", "rea")):
            self.args.client, self.args.components = client, components
            if client == "claude":
                self.args.project = str(self.project)
            with self.assertRaisesRegex(InstallError, "Pi uses --exclude-rea-skill"):
                self.plan()
        self.exclude()
        self.args.client, self.args.components, self.args.project = "codex", "rea", None
        self.assertIsNone(self.plan()["routing_ownership"])
        self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertNotIn("skills", tomllib.loads(self.config.read_text(encoding="utf-8")))

    def test_root_inference_custom_home_explicit_root_project_and_nested_identity(self):
        selected = {"agent_dir": str(self.base / "user/.codex"), "codex_skills_root": str(self.base / "custom-skills"), "project": str(self.project)}
        with patch.object(ro, "_user_home", return_value=self.base / "actual-user"):
            roots = ro.codex_roots(selected)
        self.assertIn(str((self.base / "actual-user/.agents/skills").resolve()), roots)
        self.assertIn(str((self.base / "user/.agents/skills").resolve()), roots)
        self.assertIn(str((self.project / ".agents/skills").resolve()), roots)
        self.args.project = str(self.project)
        self.args.codex_skills_root = str(self.base / "custom-skills")
        skill = self.skill("rea-agents", root=self.base / "custom-skills", folder="vendor/nested/skill")
        self.exclude(skill)
        self.install()
        self.assertTrue(w.verify(self.root)["ok"])

    def test_same_named_custom_codex_detects_actual_user_shared_conflict(self):
        self.args.agent_dir = str(self.base / "custom-home/.codex")
        skill = self.skill()  # _user_home is patched to isolated-user.
        with self.assertRaisesRegex(InstallError, "--exclude-workflow-skill") as caught:
            self.plan()
        self.assertIn(str(skill), str(caught.exception))
        self.exclude(skill)
        plan = self.plan()
        roots = plan["routing_ownership"]["scan_roots"]
        self.assertIn(str((self.base / "isolated-user/.agents/skills").resolve()), roots)
        self.assertIn(str((self.base / "custom-home/.agents/skills").resolve()), roots)
        self.assertEqual(plan["config_inputs"][str(skill)], digest(skill.read_bytes()))
        self.assertFalse((self.base / "custom-home").exists())

    def test_unsupported_and_duplicate_toml_fail_without_mutation(self):
        skill = self.skill()
        self.exclude(skill)
        path = encode_json(str(skill)).strip()
        unsupported = b'\n[[skills."config"]]\npath=' + path + b'\nenabled=true\n'
        duplicate = b'\n[[skills.config]]\npath=' + path + b'\nenabled=true\n'
        for suffix in (unsupported, duplicate * 2, b'\n[skills]\nconfig = "unknown"\n'):
            with self.subTest(suffix=suffix):
                atomic(self.config, self.original + suffix)
                with self.assertRaises(InstallError):
                    self.plan()
                self.assertEqual(self.config.read_bytes(), self.original + suffix)

    def test_symlinks_escape_traversal_and_missing_file_refused(self):
        skill = self.skill()
        self.exclude(str(skill.parent / ".." / "craft-anything" / "SKILL.md"))
        with self.assertRaisesRegex(InstallError, "traversal"):
            self.plan()
        self.exclude(str(skill.parent / "missing/SKILL.md"))
        with self.assertRaises(InstallError):
            self.plan()
        self.exclude(str(skill.parent))
        with self.assertRaises(InstallError):
            self.plan()
        link = skill.parent.parent / "link"
        try:
            link.symlink_to(self.base, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        self.exclude(skill)
        with self.assertRaisesRegex(InstallError, "symlink/reparse"):
            self.plan()
        link.unlink()
        root_link = self.base / "linked-skills"
        root_link.symlink_to(skill.parent.parent, target_is_directory=True)
        self.args.codex_skills_root = str(root_link)
        with self.assertRaisesRegex(InstallError, "symlink/reparse"):
            self.plan()

    def test_repeated_cli_flags_frozen_update_and_partial_restore(self):
        import contextlib
        import io
        first = self.skill()
        second = self.skill("rea-agents", root=self.agent / "skills")
        self.args = cli.parser().parse_args(["plan", "--root", str(self.root), "--client", "codex", "--agent-dir", str(self.agent), "--reverse-root", str(self.reverse), "--components", "reverse", "--exclude-workflow-skill", str(first), "--exclude-workflow-skill", str(second)])
        receipt = self.install()
        self.assertEqual(len(receipt["routing_ownership"]["disabled_skills"]), 2)
        self.exclude()
        frozen = self.base / "frozen.json"
        atomic(frozen, encode_json(self.plan()))
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["update", "--root", str(self.root), "--plan-file", str(frozen), "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue(w.verify(self.root)["ok"])
        w.restore(self.root, apply=True)
        text = self.config.read_bytes().replace(b"enabled = false", b"enabled = true", 1)
        later_skill = self.skill("user-later")
        suffix = b'\r\n[[skills.config]]\r\npath = ' + encode_json(str(later_skill)).strip() + b'\r\nenabled = true\r\n'
        atomic(self.config, text + suffix)
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(f["conflicts"] for f in result["files"]))
        entries = tomllib.loads(self.config.read_text(encoding="utf-8"))["skills"]["config"]
        self.assertEqual(len(entries), 2)
        self.assertTrue(all(e["enabled"] for e in entries))
        self.assertIn(str(later_skill), [e["path"] for e in entries])
        self.assertTrue((self.root / ".installer/receipt.json").exists())

    def test_attachments_are_not_nested_skills_and_non_bmp_paths_restore(self):
        skill = self.skill("craft-anything", folder="vendor-\U0001f680/official")
        unrelated = self.skill("user-reference-guide", root=self.agent / "skills")
        for path in (skill, unrelated):
            atomic(path.parent / "references/a/b/c/d/e/f/g/notes.txt", b"normal deep attachment")
        self.exclude(skill)
        original = skill.read_bytes()
        self.install()
        self.assertIn("\U0001f680".encode("utf-8"), self.config.read_bytes())
        self.assertNotIn(b"\\ud83d", self.config.read_bytes())
        self.assertTrue(w.verify(self.root)["ok"])
        later = b'\r\n[mcp_servers.later]\r\ncommand="keep"\r\n'
        atomic(self.config, self.config.read_bytes() + later)
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(f["conflicts"] for f in result["files"]), result)
        self.assertEqual(skill.read_bytes(), original)
        self.assertNotIn("skills", tomllib.loads(self.config.read_text(encoding="utf-8")))
        self.assertIn(later, self.config.read_bytes())

    def test_unsupported_host_is_explicitly_not_qualified(self):
        self.args.client = "claude"
        self.args.project = str(self.project)
        receipt = self.install()
        self.assertIsNone(receipt["routing_ownership"])
        self.assertIn("not-qualified", receipt["routing_control_status"])
        self.assertIn("not-qualified", w.verify(self.root)["routing_control_status"])

    def test_reverse_only_without_config_and_legacy_scope_never_create_config(self):
        self.config.unlink()
        plan = self.plan()
        self.assertEqual(plan["routing_ownership"]["disabled_skills"], [])
        self.assertFalse(self.config.exists())
        receipt = w.install(plan, self.args)
        self.assertFalse(self.config.exists())
        self.assertTrue(w.verify(self.root)["ok"])
        self.install()
        self.assertFalse(self.config.exists())
        # Legacy receipt scope predates the explicit Skills location/control
        # inventory and can lack a config path for reverse-only installs.
        receipt = load_json(self.root / ".installer/receipt.json")
        receipt.pop("routing_ownership")
        for key in ("components", "codex_skills_root", "client_config"):
            receipt["scope"].pop(key)
        receipt["scope"]["components"] = ["reverse"]
        atomic(self.root / ".installer/receipt.json", encode_json(receipt))
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertFalse(self.config.exists())
        # Scope without components uses historic defaults; the routing helper
        # itself must still handle missing native configuration read-only.
        receipt["scope"].pop("components")
        self.assertEqual(ro.failures(receipt), [])
        self.assertFalse(self.config.exists())

    def test_pi_existing_exclusion_is_rechecked(self):
        self.args.client = "pi"
        self.args.exclude_rea_skill = [str(self.base / "upstream-rea/SKILL.md")]
        self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        settings = load_json(self.agent / "settings.json")
        settings["skills"].remove("-" + self.args.exclude_rea_skill[0])
        atomic(self.agent / "settings.json", encode_json(settings))
        self.assertFalse(w.verify(self.root)["ok"])


if __name__ == "__main__":
    unittest.main()
