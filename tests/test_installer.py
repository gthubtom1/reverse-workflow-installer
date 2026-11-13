"""Offline behavioral tests: fake official tools, real transaction/config writes."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import install as cli
import workflow as w
from configuration import Journal, atomic, codex_merge, digest, encode_json, load_json, restore_journal
from versions import InstallError, resolve


def git(command, cwd):
    completed = subprocess.run(["git", *command], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise AssertionError("git " + " ".join(command) + " failed: " + completed.stderr)
    return completed.stdout


def make_git_reverse(base):
    repo = base / "git-reverse"
    repo.mkdir()
    git(["init", "-q"], repo)
    atomic(repo / ".gitignore", b"work/\ntool-index.json\n")
    for name in ("RULES.md", "skills/SKILL.md", "skills/config/routing.json", "skills/scripts/master-route.sh"):
        atomic(repo / name, b"native source\n")
    git(["add", "-A"], repo)
    return repo

LOCAL = REPO / ".local/tests"
LOCAL.mkdir(parents=True, exist_ok=True)


def metadata(url):
    if "npmjs" in url:
        return {"name": "rea-agents", "version": "6.8.0", "engines": {"node": ">=24.22.1"}, "dist": {"integrity": "sha512-fixture"}}
    if "pypi" in url:
        return {"info": {"name": "specify-cli"}, "releases": {"1.2.0": [{"filename": "old.whl"}], "1.3.0": [{"filename": "stable.whl", "digests": {"sha256": "f" * 64}}], "2.0.0rc1": [{"filename": "pre.whl"}], "9.0.0": [{"filename": "bad.whl", "yanked": True}]}}
    if url.endswith("/releases/latest"):
        raise InstallError("HTTP 404 fixture")
    if url.endswith("/commits/main") or "/commits/v" in url:
        return {"sha": "a" * 40}
    raise AssertionError(url)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        shutil.copytree(REPO / "adapters", self.source / "adapters")
        shutil.copyfile(REPO / "components.json", self.source / "components.json")
        self.repo_patch = patch.object(w, "REPO", self.source)
        self.repo_patch.start()
        self.root, self.agent, self.project = [self.base / name for name in ("stack", "agent with spaces 中文", "project")]
        self.reverse = self.base / "reverse"
        for name in ("RULES.md", "skills/SKILL.md", "skills/config/routing.json", "skills/scripts/master-route.sh"):
            atomic(self.reverse / name, b"native-fixture\n")
        self.node = self.base / "node/node.exe"
        atomic(self.node, b"node-fixture")
        atomic(self.node.parent / "node_modules/npm/bin/npm-cli.js", b"npm-fixture")
        self.calls = []
        self.failure = None
        self.fake_patch = patch.object(w, "run", self.fake_run)
        self.fake_patch.start()
        self.which = patch.object(w.shutil, "which", lambda name: str(self.base / name))
        self.which.start()
        self.args = cli.parser().parse_args(["install", "--root", str(self.root), "--agent-dir", str(self.agent), "--client", "pi", "--project", str(self.project), "--reverse-root", str(self.reverse), "--node", str(self.node), "--apply"])
        self.args.codex_skills_root = str(self.base / "codex-skills")
        self.before = {"defaultModel": "keep-me", "packages": ["user-package"], "skills": ["user-skill"]}
        atomic(self.agent / "settings.json", encode_json(self.before))
        atomic(self.agent / "mcp.json", encode_json({"mcpServers": {"user": {"command": "user-owned"}}, "future": 7}))

    def tearDown(self):
        self.which.stop()
        self.fake_patch.stop()
        self.repo_patch.stop()
        self.temp.cleanup()

    def fake_run(self, argv, *, cwd, env=None):
        argv = [str(a) for a in argv]
        self.calls.append(argv)
        if self.failure and self.failure in argv:
            raise InstallError("fixture official failure")
        if "rev-parse" in argv:
            return "a" * 40
        if "status" in argv:
            return ""
        if "-C" in argv and "checkout" in argv:
            return ""
        if "clone" in argv and "--no-checkout" in argv:
            self.assertEqual(argv[-2], "https://github.com/gthubtom1/agent-plugins")
            return ""
        if "-e" in argv:
            return "24.22.1"
        if "install" in argv and "--prefix" in argv:
            prefix = Path(argv[argv.index("--prefix") + 1])
            version = next(x.split("@")[-1] for x in argv if x.startswith("rea-agents@"))
            atomic(prefix / "node_modules/rea-agents/package.json", encode_json({"name": "rea-agents", "version": version}))
            atomic(prefix / "node_modules/rea-agents/scripts/rea.mjs", b"rea original fixture")
            atomic(prefix / "package-lock.json", encode_json({"packages": {"node_modules/rea-agents": {"integrity": "sha512-fixture"}}}))
            return ""
        if "tool" in argv and "install" in argv:
            atomic(Path(env["UV_TOOL_BIN_DIR"]) / ("specify.exe" if os.name == "nt" else "specify"), b"specify fixture")
            atomic(Path(env["UV_TOOL_DIR"]) / "specify-cli/package.py", b"official spec fixture")
            return ""
        if "version" in argv:
            return '{"cli_version":"1.3.0"}'
        if "setup" in argv:
            if "--dry-run" in argv:
                return '{"status":"planned"}'
            stage = Path(env["PI_CODING_AGENT_DIR"])
            if "pi" in argv:
                config = load_json(stage / "mcp.json")
                config.setdefault("mcpServers", {})["rea"] = {"type": "stdio", "command": argv[0], "args": [argv[1], "mcp"]}
                atomic(stage / "mcp.json", encode_json(config))
            else:
                config = stage / "config.toml"
                existing = config.read_text(encoding="utf-8")
                if "[mcp_servers.rea]" in existing:
                    from configuration import toml_parts
                    existing = toml_parts(config.read_bytes())[2]
                atomic(config, (existing + '\n[mcp_servers.rea]\ncommand = ' + json.dumps(argv[0]) + '\nargs = ' + json.dumps([argv[1], "mcp"]) + '\n').encode())
            return '{"status":"installed"}'
        if "init" in argv:
            project = Path(argv[argv.index("init") + 1])
            client = argv[argv.index("--integration") + 1]
            atomic(project / ".specify/memory/constitution.md", b"original constitution")
            native = ".pi/prompts/speckit.specify.md" if client == "pi" else (".claude/commands/speckit.specify.md" if client == "claude" else ".agents/skills/speckit-specify/SKILL.md")
            atomic(project / native, b"original integration")
            return ""
        raise AssertionError(argv)

    def plan(self):
        return w.make_plan(self.args, metadata)

    def install(self):
        return w.install(self.plan(), self.args)

    def test_install_preserves_config_and_records_limits(self):
        result = self.install()
        config = load_json(self.agent / "mcp.json")
        self.assertEqual(config["future"], 7)
        self.assertEqual(config["mcpServers"]["user"]["command"], "user-owned")
        self.assertEqual(load_json(self.agent / "settings.json")["defaultModel"], "keep-me")
        self.assertTrue(result["installed"])
        self.assertEqual(result["validation"]["mcp_handshake_and_tools_schema"], "unverified")
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertFalse(any("clone" in c for c in self.calls))
        self.assertNotIn("npx", str(self.calls))
        self.assertTrue(any("--skill=false" in c and "--dry-run" in c for c in self.calls))
        self.assertTrue(any("--integration" in c and "pi" in c for c in self.calls))

    def test_pi_global_and_package_entry_use_resolvable_receipts(self):
        result = self.install()
        global_text = (self.agent / "skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(str(self.root / ".installer/receipt.json"), global_text)
        self.assertIn("直接读取本机安装回执", global_text)
        self.assertNotIn("再读取其中 `receipt`", global_text)
        adapter = Path(result["adapter"]["root"])
        locator = load_json(adapter / "receipt-location.json")
        self.assertEqual(load_json(Path(locator["receipt"]))["transaction"], result["transaction"])
        self.assertNotIn("下一步建议必须根据当前 Evidence 动态生成 2–5", global_text)

    def test_repeat_no_reinstall_no_duplicate_resources(self):
        first = self.install()
        self.calls.clear()
        second = self.install()
        self.assertEqual(first["paths"], second["paths"])
        self.assertFalse(any("install" in c or "init" in c for c in self.calls))
        packages = load_json(self.agent / "settings.json")["packages"]
        self.assertEqual(len(packages), 2)

    def test_failure_does_not_write_installed_and_retry_works(self):
        self.failure = "--yes"
        with self.assertRaises(InstallError):
            self.install()
        self.assertFalse((self.root / ".installer/receipt.json").exists())
        self.assertEqual(load_json(self.agent / "settings.json"), self.before)
        self.failure = None
        self.assertTrue(self.install()["installed"])

    def test_failure_during_activation_rolls_back_configs(self):
        original = Journal.write
        def fail(journal, path, data, kind="file"):
            if Path(path).name == "constitution.md":
                raise InstallError("fixture activation failure")
            return original(journal, path, data, kind)
        with patch.object(Journal, "write", fail):
            with self.assertRaises(InstallError):
                self.install()
        self.assertEqual(load_json(self.agent / "settings.json"), self.before)
        self.assertNotIn("rea", load_json(self.agent / "mcp.json")["mcpServers"])
        self.assertFalse((self.root / ".installer/receipt.json").exists())

    def test_plan_drift_rejected_before_any_package_command(self):
        plan = self.plan()
        atomic(self.agent / "settings.json", b'{"new":"user edit"}')
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "漂移"):
            w.install(plan, self.args)
        self.assertFalse(self.calls)

    def test_reverse_drift_rejected(self):
        plan = self.plan()
        atomic(self.reverse / "RULES.md", b"changed rules")
        with self.assertRaisesRegex(InstallError, "漂移"):
            w.install(plan, self.args)

    def test_restore_preserves_later_user_config_and_project_changes(self):
        receipt = self.install()
        settings = load_json(self.agent / "settings.json")
        settings["defaultModel"] = "new-user-model"
        settings["packages"].append("later-package")
        atomic(self.agent / "settings.json", encode_json(settings))
        config = load_json(self.agent / "mcp.json")
        config["mcpServers"]["later"] = {"command": "keep"}
        atomic(self.agent / "mcp.json", encode_json(config))
        constitution = self.project / ".specify/memory/constitution.md"
        atomic(constitution, b"user edited constitution")
        preview = w.restore(self.root)
        self.assertTrue((self.root / ".installer/receipt.json").exists())
        restored = w.restore(self.root, apply=True)
        self.assertEqual(load_json(self.agent / "settings.json")["defaultModel"], "new-user-model")
        self.assertIn("later-package", load_json(self.agent / "settings.json")["packages"])
        self.assertNotIn("rea", load_json(self.agent / "mcp.json")["mcpServers"])
        self.assertIn("later", load_json(self.agent / "mcp.json")["mcpServers"])
        self.assertEqual(constitution.read_bytes(), b"user edited constitution")
        self.assertTrue(any(f["conflicts"] for f in restored["files"]))
        self.assertTrue(Path(receipt["backup"]).is_file())
        self.assertTrue(preview["files"])

    def test_owned_rea_user_edit_is_kept_on_restore(self):
        self.install()
        config = load_json(self.agent / "mcp.json")
        config["mcpServers"]["rea"]["command"] = "user-overridden"
        atomic(self.agent / "mcp.json", encode_json(config))
        result = w.restore(self.root, apply=True)
        self.assertEqual(load_json(self.agent / "mcp.json")["mcpServers"]["rea"]["command"], "user-overridden")
        self.assertTrue(any(f["conflicts"] for f in result["files"]))

    def test_verify_detects_original_package_tampering(self):
        receipt = self.install()
        atomic(Path(receipt["paths"]["rea_package"]) / "scripts/rea.mjs", b"tampered")
        self.assertFalse(w.verify(self.root)["ok"])

    def test_existing_project_is_never_overwritten(self):
        atomic(self.project / "user.txt", b"keep")
        with self.assertRaisesRegex(InstallError, "必须不存在或为空"):
            self.install()
        self.assertEqual((self.project / "user.txt").read_bytes(), b"keep")

    def test_update_preserves_existing_templates(self):
        self.install()
        constitution = self.project / ".specify/memory/constitution.md"
        atomic(constitution, b"my project design")
        self.calls.clear()
        result = self.install()
        self.assertEqual(constitution.read_bytes(), b"my project design")
        self.assertEqual(result["checks"]["project_init"], "preserved-existing")
        self.assertFalse(any("init" in c for c in self.calls))

    def test_explicit_external_packages_reused_read_only(self):
        first = self.install()
        # Use an independent scope, referencing the already prepared official fixtures.
        self.args.root = str(self.base / "second-stack")
        self.args.agent_dir = str(self.base / "second-agent")
        self.args.project = str(self.base / "second-project")
        self.args.rea_prefix = first["paths"]["rea_prefix"]
        self.args.spec_kit_tools = first["paths"]["uv_tools"]
        self.args.spec_kit_bin = first["paths"]["uv_bin"]
        self.calls.clear()
        result = self.install()
        self.assertEqual(result["paths"]["rea_package"], first["paths"]["rea_package"])
        self.assertFalse(any("install" in c for c in self.calls))

    def test_codex_official_setup_integration_and_thin_reference(self):
        self.args.client = "codex"
        atomic(self.agent / "config.toml", b'model = "keep"\n[mcp_servers.user]\ncommand = "user"\n')
        result = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        text = (self.project / ".agents/skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(str(self.root / ".installer/receipt.json"), text)
        self.assertEqual(result["scope"]["client"], "codex")
        self.assertTrue(any("--integration" in c and "codex" in c for c in self.calls))
        self.assertFalse(any("plugin" in c for c in self.calls))

    def test_real_version_change_is_parallel_and_restore_returns_previous_receipt(self):
        first = self.install()
        atomic(self.project / ".specify/memory/constitution.md", b"keep my UI/design")
        def next_metadata(url):
            result = metadata(url)
            if "npmjs" in url:
                result["version"] = "6.9.0"
            return result
        self.args.upgrade_components = True
        next_plan = w.make_plan(self.args, next_metadata)
        second = w.install(next_plan, self.args)
        self.assertNotEqual(first["paths"]["rea_prefix"], second["paths"]["rea_prefix"])
        self.assertTrue(Path(first["paths"]["rea_package"]).is_dir())
        self.assertEqual((self.project / ".specify/memory/constitution.md").read_bytes(), b"keep my UI/design")
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(f["conflicts"] for f in result["files"]))
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_failed_upgrade_preserves_previous_active_receipt(self):
        first = self.install()
        def next_metadata(url):
            result = metadata(url)
            if "npmjs" in url:
                result["version"] = "6.9.0"
            return result
        self.args.upgrade_components = True
        self.failure = "--yes"
        with self.assertRaises(InstallError):
            w.install(w.make_plan(self.args, next_metadata), self.args)
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_later_user_rea_edit_refuses_update_without_overwrite(self):
        self.install()
        config = load_json(self.agent / "mcp.json")
        config["mcpServers"]["rea"]["timeout"] = 1234
        atomic(self.agent / "mcp.json", encode_json(config))
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "后续用户修改"):
            self.install()
        self.assertEqual(load_json(self.agent / "mcp.json"), config)
        self.assertFalse(any("setup" in c for c in self.calls))

    def test_codex_restore_preserves_later_unrelated_tables(self):
        self.args.client = "codex"
        atomic(self.agent / "config.toml", b'model = "keep"\n')
        self.install()
        config = self.agent / "config.toml"
        atomic(config, config.read_bytes() + b'\n[mcp_servers.later]\ncommand="keep-later"\n')
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(f["conflicts"] for f in result["files"]))
        self.assertIn(b"keep-later", config.read_bytes())
        self.assertNotIn(b"mcp_servers.rea", config.read_bytes())

    def test_cli_preview_does_not_invoke_package_commands(self):
        import contextlib
        import io
        output = io.StringIO()
        argv = ["install", "--root", str(self.root), "--client", "pi", "--agent-dir", str(self.agent), "--project", str(self.project), "--reverse-root", str(self.reverse), "--node", str(self.node)]
        with patch.object(w, "resolve", lambda manifest, **kwargs: resolve(manifest, metadata, **kwargs)), contextlib.redirect_stdout(output):
            self.assertEqual(cli.main(argv), 0)
        self.assertNotIn("installed", json.loads(output.getvalue()))
        self.assertFalse(any("install" in c or "setup" in c or "init" in c for c in self.calls))
        self.assertFalse((self.root / ".installer").exists())

    def test_frozen_plan_does_not_resolve_latest_again(self):
        import contextlib
        import io
        plan = self.plan()
        path = self.base / "frozen.json"
        atomic(path, encode_json(plan))
        with patch.object(w, "resolve", side_effect=AssertionError("must not fetch again")), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["install", "--root", str(self.root), "--plan-file", str(path), "--apply"])
        self.assertEqual(code, 0)

    def test_tampered_frozen_config_scope_rejected(self):
        plan = self.plan()
        plan["config_inputs"][str(self.base / "unrelated.json")] = None
        with self.assertRaisesRegex(InstallError, "范围"):
            w.install(plan, self.args)

    def test_auto_schema_identity_does_not_use_cli_presence(self):
        atomic(self.agent / "pi-evidence.json", encode_json({"$schema": "https://pi.dev/schemas/settings.schema.json"}))
        self.assertEqual(w.detect_client("auto", self.agent / "pi-evidence.json", {})[0], "pi")
        atomic(self.agent / "config.toml", b'approval_policy="on-request"\n')
        self.assertEqual(w.detect_client("auto", self.agent / "config.toml", {})[0], "codex")
        with self.assertRaises(InstallError):
            w.detect_client("auto", self.agent / "mcp.json", {})

    def test_runtime_and_original_spec_environment_drift(self):
        receipt = self.install()
        atomic(Path(receipt["paths"]["uv_tools"]) / "specify-cli/package.py", b"mutated official package")
        self.assertFalse(w.verify(self.root)["ok"])

    def test_scope_rejects_tool_project_and_config_mismatch(self):
        self.args.project = str(self.reverse / "project")
        with self.assertRaisesRegex(InstallError, "重叠"):
            self.plan()
        self.args.project = str(self.project)
        self.args.client_config = str(self.agent / "settings.json")
        with self.assertRaisesRegex(InstallError, "mcp.json"):
            self.plan()

    def test_manual_and_exact_exclusion_are_frozen(self):
        self.args.rea_manual = True
        self.args.exclude_rea_skill = [str(self.base / "existing-rea/SKILL.md")]
        receipt = self.install()
        settings = load_json(self.agent / "settings.json")
        self.assertIn("-" + self.args.exclude_rea_skill[0], settings["skills"])
        manifest = load_json(Path(receipt["adapter"]["root"]) / "package.json")
        self.assertEqual(manifest["pi"]["extensions"], [])
        self.assertEqual(manifest["pi"]["themes"], [])
    def test_selected_reverse_can_install_without_host_or_spec_kit(self):
        self.args.components = "reverse"
        self.args.client = "none"
        self.args.agent_dir = None
        self.args.client_config = None
        self.args.project = None
        receipt = self.install()
        self.assertEqual(receipt["scope"]["components"], ["reverse"])
        self.assertIsNone(receipt["managed_rea_config"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_selected_rea_can_install_without_reverse_or_spec_kit(self):
        self.args.components = "rea"
        self.args.project = None
        self.args.reverse_root = None
        receipt = self.install()
        self.assertEqual(receipt["scope"]["components"], ["rea"])
        self.assertTrue(receipt["managed_rea_config"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_selected_spec_kit_can_install_without_reverse_or_rea(self):
        self.args.components = "spec-kit"
        self.args.agent_dir = None
        self.args.client_config = None
        self.args.reverse_root = None
        receipt = self.install()
        self.assertEqual(receipt["scope"]["components"], ["spec_kit"])
        self.assertTrue((self.project / ".specify/memory/constitution.md").is_file())
        self.assertTrue(w.verify(self.root)["ok"])


    def test_repeat_install_upgrades_recorded_global_skill(self):
        first = self.install()
        source = self.source / "adapters/pi/skills/reverse-workflow/SKILL.md"
        atomic(source, source.read_bytes() + b"\nAdapter body revision from a newer installer.\n")
        second = self.install()
        global_text = (self.agent / "skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Adapter body revision from a newer installer", global_text)
        self.assertNotEqual(first["adapter"]["key"], second["adapter"]["key"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_user_modified_global_skill_is_rejected(self):
        self.install()
        target = self.agent / "skills/reverse-workflow/SKILL.md"
        atomic(target, target.read_bytes() + b"local user note")
        with self.assertRaisesRegex(InstallError, "已被用户修改"):
            self.install()
        self.assertIn("local user note", target.read_text(encoding="utf-8"))

    def test_same_agent_other_root_rejects_with_actionable_conflict(self):
        first = self.install()
        self.args.root = str(self.base / "second-stack")
        self.args.project = str(self.base / "second-project")
        with self.assertRaisesRegex(InstallError, "另一安装根"):
            self.install()
        self.assertIn(str(self.root / ".installer/receipt.json"), (self.agent / "skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])

    def test_legacy_unrecorded_pi_skill_upgrade_uses_previous_adapter_bytes(self):
        self.install()
        path = self.root / ".installer/receipt.json"
        legacy = load_json(path)
        for key in ("config_diff", "history", "backup"):
            legacy.pop(key, None)
        atomic(path, encode_json(legacy))
        source = self.source / "adapters/pi/skills/reverse-workflow/SKILL.md"
        atomic(source, source.read_bytes() + b"\nLegacy upgrade body.\n")
        self.install()
        self.assertIn("Legacy upgrade body", (self.agent / "skills/reverse-workflow/SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue(w.verify(self.root)["ok"])

    def test_legacy_full_receipt_shape_still_verifies(self):
        self.install()
        path = self.root / ".installer/receipt.json"
        legacy = load_json(path)
        legacy["scope"].pop("components")
        legacy.pop("resource_selection")
        legacy.pop("entry_hashes")
        legacy["hashes"].pop("reverse_sha256", None)
        legacy["adapter"].pop("key", None)
        atomic(path, encode_json(legacy))
        self.assertTrue(w.verify(self.root)["ok"])

    def test_legacy_receipt_without_components_blocks_silent_shrink(self):
        self.install()
        path = self.root / ".installer/receipt.json"
        legacy = load_json(path)
        legacy["scope"].pop("components")
        atomic(path, encode_json(legacy))
        self.args.components = "reverse"
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "收缩"):
            self.install()
        self.assertFalse(any("install" in call or "setup" in call or "init" in call for call in self.calls))

    def test_claude_rea_preserves_explicit_provider_environment(self):
        self.args.components = "rea"
        self.args.client = "claude"
        config = self.agent / "claude_desktop_config.json"
        environment = {"GHIDRA_INSTALL_DIR": str(self.base / "my-ghidra"), "JAVA_HOME": str(self.base / "my-jdk")}
        atomic(config, encode_json({"mcpServers": {"rea": {"command": "old-node", "args": ["old-launcher"], "env": environment}, "user": {"command": "keep"}}}))
        result = self.install()
        self.assertEqual(load_json(config)["mcpServers"]["rea"]["env"], environment)
        self.assertEqual(load_json(config)["mcpServers"]["user"], {"command": "keep"})
        self.assertEqual(result["managed_rea_config"]["command"], str(self.node))
        self.assertTrue(w.verify(self.root)["ok"])

    def test_claude_subset_writes_global_and_project_entries(self):
        self.args.components = "reverse"
        self.args.client = "claude"
        receipt = self.install()
        self.assertTrue((self.agent / "skills/reverse-workflow/SKILL.md").is_file())
        self.assertTrue((self.project / "CLAUDE.md").is_file())
        self.assertIn(str(self.root / ".installer/receipt.json"), (self.project / "CLAUDE.md").read_text(encoding="utf-8"))
        self.assertEqual(receipt["scope"]["components"], ["reverse"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_codex_subset_writes_global_and_project_entries(self):
        self.args.components = "reverse"
        self.args.client = "codex"
        receipt = self.install()
        self.assertTrue((self.agent / "AGENTS.md").is_file())
        self.assertTrue((Path(self.args.codex_skills_root) / "reverse-workflow/SKILL.md").is_file())
        self.assertTrue((self.project / ".agents/skills/reverse-workflow/SKILL.md").is_file())
        self.assertIn(str(self.root / ".installer/receipt.json"), (self.agent / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(receipt["scope"]["components"], ["reverse"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_subset_pi_resource_selection_is_applied_and_verified(self):
        self.args.components = "reverse"
        self.args.rea_manual = True
        self.args.exclude_rea_skill = [str(self.base / "existing-rea/SKILL.md")]
        receipt = self.install()
        settings = load_json(self.agent / "settings.json")
        exclusion = "-" + self.args.exclude_rea_skill[0]
        manual = receipt["resource_selection"]["rea_manual_skill"]
        self.assertIn(exclusion, settings["skills"])
        self.assertTrue(Path(manual).is_file())
        self.assertIn(manual, settings["skills"])
        self.assertTrue(w.verify(self.root)["ok"])
        settings["skills"].remove(exclusion)
        atomic(self.agent / "settings.json", encode_json(settings))
        self.assertFalse(w.verify(self.root)["ok"])

    def test_subset_repeat_reuses_complete_and_keeps_original_hashes(self):
        self.args.components = "rea"
        self.args.project = None
        self.args.reverse_root = None
        first = self.install()
        self.calls.clear()
        second = self.install()
        self.assertFalse(any("install" in call for call in self.calls))
        self.assertEqual(first["hashes"]["rea_sha256"], second["hashes"]["rea_sha256"])
        atomic(Path(first["paths"]["rea_package"]) / "scripts/rea.mjs", b"tampered")
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "漂移"):
            self.install()
        self.assertFalse(any("install" in call for call in self.calls))

    def test_subset_expansion_allowed_and_shrink_rejected(self):
        self.args.components = "reverse"
        self.install()
        self.args.components = "rea,reverse"
        self.calls.clear()
        expanded = self.install()
        self.assertEqual(expanded["scope"]["components"], ["rea", "reverse"])
        self.assertFalse(any("init" in call for call in self.calls))
        self.assertTrue(w.verify(self.root)["ok"])
        self.args.components = "reverse"
        with self.assertRaisesRegex(InstallError, "收缩"):
            self.install()

    def test_subset_transition_keeps_history_pointer_and_restores(self):
        self.args.components = "rea"
        self.args.project = None
        self.args.reverse_root = None
        first = self.install()
        second = self.install()
        receipt = load_json(self.root / ".installer/receipt.json")
        self.assertEqual(receipt["previous_transaction"], first["transaction"])
        self.assertEqual(receipt["history"], [first["transaction"], second["transaction"]])
        self.assertEqual(w.restore(self.root, apply=True)["applied"], True)
        self.assertEqual(load_json(self.root / ".installer/receipt.json")["transaction"], first["transaction"])

    def test_subset_managed_rea_edit_blocks_repeat(self):
        self.args.components = "rea"
        self.args.project = None
        self.args.reverse_root = None
        self.install()
        config = load_json(self.agent / "mcp.json")
        config["mcpServers"]["rea"]["timeout"] = 99
        atomic(self.agent / "mcp.json", encode_json(config))
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "后续用户修改"):
            self.install()
        self.assertFalse(any("setup" in call for call in self.calls))
        self.assertEqual(load_json(self.agent / "mcp.json"), config)

    def test_pi_object_form_package_source_is_verified_and_preserved(self):
        receipt = self.install()
        adapter = receipt["adapter"]["root"]
        settings = load_json(self.agent / "settings.json")
        settings["packages"] = [{"source": p} if p == adapter else p for p in settings["packages"]]
        atomic(self.agent / "settings.json", encode_json(settings))
        self.assertTrue(w.verify(self.root)["ok"])
        self.install()
        packages = load_json(self.agent / "settings.json")["packages"]
        self.assertTrue(any(isinstance(p, dict) and p.get("source") == adapter for p in packages))
        self.assertTrue(w.verify(self.root)["ok"])

    def test_plan_resolves_only_selected_components(self):
        self.args.components = "rea"
        self.args.project = None
        self.args.reverse_root = None
        seen = []

        def fetch(url):
            seen.append(url)
            if "github" in url:
                raise AssertionError("unexpected GitHub lookup")
            return metadata(url)

        plan = w.make_plan(self.args, fetch)
        self.assertEqual(sorted(plan["components"]), ["rea"])
        self.assertFalse([url for url in seen if "github" in url])
        w.validate_plan(plan)

    def test_local_reverse_root_plan_skips_upstream_lookup(self):
        self.args.components = "reverse"
        self.args.project = None

        def fetch(url):
            raise AssertionError(url)

        plan = w.make_plan(self.args, fetch)
        self.assertEqual(plan["components"]["reverse"]["mode"], "read-only-working-copy")
        self.assertEqual(plan["components"]["reverse"]["commit"], "a" * 40)
        w.validate_plan(plan)


    def test_identity_compares_client_literally(self):
        identity = w.normalized_identity({"client": "pi", "root": str(self.root), "agent_dir": None, "client_config": None, "project": None})
        self.assertEqual(identity["client"], "pi")
        self.assertEqual(identity["root"], str(self.root.resolve()))

    def test_specify_init_args_shared_flags(self):
        self.assertIn("--ignore-agent-tools", w.specify_init_args("specify", "target", "claude"))
        self.assertIn("--ignore-agent-tools", w.specify_init_args("specify", "target", "codex"))
        self.assertNotIn("--ignore-agent-tools", w.specify_init_args("specify", "target", "pi"))

    def test_verify_detects_global_skill_body_drift_with_receipt_path_intact(self):
        self.install()
        target = self.agent / "skills/reverse-workflow/SKILL.md"
        text = target.read_text(encoding="utf-8")
        self.assertIn(str(self.root / ".installer/receipt.json"), text)
        atomic(target, (text + "\nuser appended instructions\n").encode())
        result = w.verify(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("installer entry drift" in failure for failure in result["failures"]))

    def test_verify_detects_deleted_adapter_package_skill(self):
        receipt = self.install()
        adapter_skill = Path(receipt["adapter"]["root"]) / "skills/reverse-workflow/SKILL.md"
        self.assertTrue(adapter_skill.is_file())
        adapter_skill.unlink()
        result = w.verify(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("installer entry drift" in failure for failure in result["failures"]))

    def test_codex_reverse_only_receipt_can_expand_to_spec_kit(self):
        self.args.components = "reverse"
        self.args.client = "codex"
        self.install()
        entry = self.project / ".agents/skills/reverse-workflow/SKILL.md"
        self.assertTrue(entry.is_file())
        self.args.components = "reverse,spec-kit"
        receipt = self.install()
        self.assertEqual(receipt["scope"]["components"], ["reverse", "spec_kit"])
        self.assertTrue((self.project / ".specify").is_dir())
        self.assertTrue((self.project / ".agents/skills/speckit-specify/SKILL.md").is_file())
        self.assertTrue(entry.is_file())
        self.assertTrue(w.verify(self.root)["ok"])

    def test_claude_reverse_only_receipt_can_expand_to_spec_kit(self):
        self.args.components = "reverse"
        self.args.client = "claude"
        self.install()
        entry = self.project / "CLAUDE.md"
        self.assertTrue(entry.is_file())
        self.args.components = "reverse,spec-kit"
        receipt = self.install()
        self.assertEqual(receipt["scope"]["components"], ["reverse", "spec_kit"])
        self.assertTrue((self.project / ".claude/commands/speckit.specify.md").is_file())
        self.assertTrue(entry.is_file())
        self.assertTrue(w.verify(self.root)["ok"])

    def test_verify_ignores_user_spec_and_settings_edits(self):
        self.install()
        atomic(self.project / ".specify/memory/constitution.md", b"my project design")
        settings = load_json(self.agent / "settings.json")
        settings["defaultModel"] = "user-model"
        atomic(self.agent / "settings.json", encode_json(settings))
        self.assertTrue(w.verify(self.root)["ok"])

    def test_expansion_rejects_foreign_project_files(self):
        self.args.components = "reverse"
        self.args.client = "codex"
        self.install()
        atomic(self.project / "notes.txt", b"user notes")
        self.args.components = "reverse,spec-kit"
        with self.assertRaisesRegex(InstallError, "不会覆盖既有项目"):
            self.install()
        self.assertEqual((self.project / "notes.txt").read_bytes(), b"user notes")


    def test_default_node_path_is_canonicalized_for_plan_validation(self):
        node_file = self.base / "node/node.exe"
        self.assertTrue(node_file.is_file())
        uppercase_node = node_file.with_name(node_file.name.upper())
        # On case-sensitive systems this is a distinct valid executable path.
        # Windows resolves the existing file's casing; Linux must preserve it.
        if not uppercase_node.exists():
            atomic(uppercase_node, node_file.read_bytes())
        variants = [str(self.base / "node" / ".." / "node" / "node.exe"), str(uppercase_node)]
        link = self.base / "node-link.exe"
        try:
            link.symlink_to(node_file)
            variants.append(str(link))
        except (OSError, NotImplementedError):
            pass
        self.args.node = None
        for raw in variants:
            with self.subTest(raw=raw):
                expected = str(w.abs_path(raw))
                with patch.object(w.shutil, "which", lambda name, raw=raw: {"node": raw, "uv": str(self.base / "uv"), "git": str(self.base / "git")}.get(name)):
                    self.assertEqual(w.scope(self.args)["node"], expected)
                    plan = w.make_plan(self.args, metadata)
                    self.assertEqual(plan["scope"]["node"], expected)
                    w.validate_plan(plan)
                    w.install(plan, self.args)
                self.assertTrue(w.verify(self.root)["ok"])

    def test_default_node_when_absent_stays_none(self):
        self.args.node = None
        self.args.components = "reverse"
        self.args.client = "none"
        self.args.agent_dir = None
        self.args.client_config = None
        self.args.project = None
        with patch.object(w.shutil, "which", lambda name: None if name == "node" else str(self.base / name)):
            plan = w.make_plan(self.args, metadata)
            self.assertIsNone(plan["scope"]["node"])
            self.assertEqual(plan["missing_prerequisites"], [])
            w.validate_plan(plan)
            w.install(plan, self.args)
        self.assertTrue(w.verify(self.root)["ok"])

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_source_tree_hash_ignores_git_ignored_artifacts(self):
        repo = make_git_reverse(self.base)
        first = w.tree_hash(repo, exclude_git=True)
        atomic(repo / "work/case/evidence.bin", b"runtime artifact")
        atomic(repo / "tool-index.json", b'{"generated": true}')
        self.assertEqual(w.tree_hash(repo, exclude_git=True), first)
        atomic(repo / "RULES.md", b"edited source\n")
        edited = w.tree_hash(repo, exclude_git=True)
        self.assertNotEqual(edited, first)
        atomic(repo / "RULES.md", b"native source\n")
        self.assertEqual(w.tree_hash(repo, exclude_git=True), first)
        atomic(repo / "new-note.md", b"untracked but not ignored")
        self.assertNotEqual(w.tree_hash(repo, exclude_git=True), first)
        git(["add", "-f", "tool-index.json"], repo)
        atomic(repo / "tool-index.json", b'{"generated": "changed"}')
        self.assertNotEqual(w.tree_hash(repo, exclude_git=True), first)
        (repo / "RULES.md").unlink()
        self.assertNotEqual(w.tree_hash(repo, exclude_git=True), first)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_reverse_verify_ignores_ignored_work_and_detects_source_edits(self):
        repo = make_git_reverse(self.base)
        self.args.reverse_root = str(repo)
        self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        atomic(repo / "work/case/evidence.bin", b"case artifact")
        atomic(repo / "tool-index.json", b'{"index": 1}')
        self.assertTrue(w.verify(self.root)["ok"])
        atomic(repo / "new-case/notes.md", b"untracked source note")
        self.assertFalse(w.verify(self.root)["ok"])
        (repo / "new-case/notes.md").unlink()
        self.assertTrue(w.verify(self.root)["ok"])
        atomic(repo / "RULES.md", b"edited rules\n")
        self.assertFalse(w.verify(self.root)["ok"])

    def test_pending_transaction_is_safely_rolled_back_before_next_install(self):
        target = self.root / "owned.txt"
        atomic(target, b"before")
        journal = Journal(self.root / ".installer/transactions/interrupted")
        journal.write(target, b"after")
        self.assertEqual(target.read_bytes(), b"after")
        self.assertEqual(w.recover_pending_transactions(self.root), ["interrupted"])
        self.assertEqual(target.read_bytes(), b"before")
        self.assertEqual(load_json(self.root / ".installer/transactions/interrupted/journal.json")["status"], "recovered")
    def _seed_retired_continuity(self, filtered=False, duplicate=False):
        first = self.install()
        old_root = self.base / "old-continuity-package"
        atomic(old_root / "package.json", encode_json({"name": "@toti/pi-project-continuity", "version": "1.2.0"}))
        settings = load_json(self.agent / "settings.json")
        registration = str(old_root)
        if filtered:
            registration = {"source": registration, "extensions": []}
        settings["packages"].append(registration)
        if duplicate:
            settings["packages"].append(str(old_root))
        atomic(self.agent / "settings.json", encode_json(settings))
        receipt_path = self.root / ".installer/receipt.json"
        receipt = load_json(receipt_path)
        receipt["scope"]["components"].append("project_continuity")
        receipt["paths"]["project_continuity"] = str(old_root)
        receipt["project_continuity"] = {"root": str(old_root), "plugin_dir": "plugins/pi/project-continuity", "name": "@toti/pi-project-continuity"}
        receipt["components"]["project_continuity"] = {"package_name": "@toti/pi-project-continuity"}
        atomic(receipt_path, encode_json(receipt))
        return first, receipt, settings, old_root

    def test_default_plan_does_not_select_retired_component(self):
        plan = self.plan()
        self.assertEqual(plan["scope"]["components"], ["rea", "spec_kit", "reverse"])
        self.assertNotIn("project_continuity", plan["components"])
        self.assertNotIn("project_continuity", plan["scope"])

    def test_update_retires_uniquely_identified_continuity_registration(self):
        first, _, _, old_root = self._seed_retired_continuity()
        plan = self.plan()
        self.assertEqual(plan["retired_project_continuity"]["root"], str(old_root.resolve()))
        updated = w.install(plan, self.args)
        settings = load_json(self.agent / "settings.json")
        self.assertNotIn(str(old_root), settings["packages"])
        self.assertTrue((old_root / "package.json").is_file())
        self.assertNotIn("project_continuity", updated["scope"]["components"])
        self.assertNotIn("project_continuity", updated)
        self.assertNotIn("project_continuity", updated["paths"])
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertNotEqual(updated["transaction"], first["transaction"])

    def test_update_accepts_continuity_already_removed_from_settings(self):
        first, _, _, old_root = self._seed_retired_continuity()
        settings = load_json(self.agent / "settings.json")
        settings["packages"] = [p for p in settings["packages"] if p != str(old_root)]
        atomic(self.agent / "settings.json", encode_json(settings))
        updated = w.install(self.plan(), self.args)
        self.assertNotIn(str(old_root), load_json(self.agent / "settings.json").get("packages", []))
        self.assertNotIn("project_continuity", updated)
        self.assertNotEqual(updated["transaction"], first["transaction"])

    def test_update_refuses_unidentifiable_continuity_registration(self):
        _, _, settings, _ = self._seed_retired_continuity(filtered=True)
        with self.assertRaisesRegex(InstallError, "唯一的精确 Pi 包注册"):
            self.plan()
        self.assertEqual(load_json(self.agent / "settings.json"), settings)

    def test_update_refuses_duplicate_continuity_registration(self):
        _, _, settings, _ = self._seed_retired_continuity(duplicate=True)
        with self.assertRaisesRegex(InstallError, "唯一的精确 Pi 包注册"):
            self.plan()
        self.assertEqual(load_json(self.agent / "settings.json"), settings)

class VersionsAndIdentity(unittest.TestCase):
    def test_stable_non_yanked_and_main_fallback(self):
        result = resolve(load_json(REPO / "components.json"), metadata)
        self.assertEqual(result["spec_kit"]["version"], "1.3.0")
        self.assertEqual(result["reverse"]["commit"], "a" * 40)

    def test_release_tag_resolves_commit_and_not_target_branch(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url.endswith("releases/latest"):
                return {"tag_name": "v1.1.0", "target_commitish": "main"}
            return metadata(url)
        result = resolve(load_json(REPO / "components.json"), fetch)
        self.assertEqual(result["reverse"]["ref"], "v1.1.0")
        self.assertTrue(any(u.endswith("commits/v1.1.0") for u in calls))

    def test_no_silent_fallback_on_http_rate_limit(self):
        def fetch(url):
            if "releases/latest" in url:
                raise InstallError("HTTP 403")
            return metadata(url)
        with self.assertRaisesRegex(InstallError, "403"):
            resolve(load_json(REPO / "components.json"), fetch)

    def test_npm_prerelease_rejected(self):
        def fetch(url):
            result = metadata(url)
            if "npmjs" in url:
                result["version"] = "7.0.0-beta.1"
            return result
        with self.assertRaisesRegex(InstallError, "稳定"):
            resolve(load_json(REPO / "components.json"), fetch)

    def test_auto_uses_host_markers_and_does_not_reveal_values(self):
        self.assertEqual(w.detect_client("auto", env={"PI_CODING_AGENT": "true"})[0], "pi")
        self.assertEqual(w.detect_client("auto", env={"CODEX_THREAD_ID": "private-thread"})[0], "codex")
        for env in ({}, {"AI_AGENT": "codex-model"}, {"PI_CODING_AGENT": "true", "CODEX_THREAD_ID": "private-thread"}):
            with self.assertRaises(InstallError) as caught:
                w.detect_client("auto", env=env)
            self.assertNotIn("private-thread", str(caught.exception))

    def test_http_transport_mock_and_readable_missing_package(self):
        import io
        import urllib.error
        from versions import http_json
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"version":"1.0.0"}')):
            self.assertEqual(http_json("https://registry.npmjs.org/example")["version"], "1.0.0")
        error = urllib.error.HTTPError("https://pypi.org/pypi/specify-cli/json", 404, "missing", {}, None)
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(InstallError, "HTTP 404"):
                http_json(error.url)

    def test_github_token_is_used_without_revealing_it(self):
        import io
        from versions import http_json
        observed = {}
        def fake_urlopen(request, timeout=30):
            observed["authorization"] = request.get_header("Authorization")
            return io.BytesIO(b'{"sha":"fixture"}')
        with patch.dict(os.environ, {"GH_TOKEN": "fixture-secret"}, clear=False):
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                self.assertEqual(http_json("https://api.github.com/repos/example/project/commits/main")["sha"], "fixture")
        self.assertEqual(observed["authorization"], "Bearer fixture-secret")

    def test_codex_merge_retains_unrelated_format_and_rejects_unrelated_mutation(self):
        original = b'# user comment\nmodel = "keep"\n'
        staged = b'model="keep"\n[mcp_servers.rea]\ncommand="node"\n'
        result = codex_merge(original, staged)
        self.assertIn(b"# user comment", result)
        with self.assertRaises(InstallError):
            codex_merge(original, staged.replace(b'"keep"', b'"overwritten"'))


if __name__ == "__main__":
    unittest.main()
