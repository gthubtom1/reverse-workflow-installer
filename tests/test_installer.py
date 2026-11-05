"""Offline behavioral tests: fake official tools, real transaction/config writes."""
import copy
import json
import os
from pathlib import Path
import shutil
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
            atomic(project / (".pi/prompts/speckit.specify.md" if client == "pi" else ".agents/skills/speckit-specify/SKILL.md"), b"original integration")
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
        with patch.object(w, "resolve", lambda manifest: resolve(manifest, metadata)), contextlib.redirect_stdout(output):
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

    def test_codex_merge_retains_unrelated_format_and_rejects_unrelated_mutation(self):
        original = b'# user comment\nmodel = "keep"\n'
        staged = b'model="keep"\n[mcp_servers.rea]\ncommand="node"\n'
        result = codex_merge(original, staged)
        self.assertIn(b"# user comment", result)
        with self.assertRaises(InstallError):
            codex_merge(original, staged.replace(b'"keep"', b'"overwritten"'))


if __name__ == "__main__":
    unittest.main()
