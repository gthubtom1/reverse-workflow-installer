"""Directed offline installer fixtures; fake native bytes are not qualified binaries."""
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_installer as fixtures
import craft as pi
import craft_codex as cc
import install as cli
import workflow as w
from configuration import Journal, atomic, digest, encode_json, load_json
from versions import InstallError

REPO = fixtures.REPO
FIXTURE_CLI_BYTES = b"offline native CLI fixture"
# Substitute only the binary pin in a separate reviewed fixture source. This is
# not a claim that fixture configuration proves real native effect permissions.
_fixture_profile = json.loads((REPO / cc.PROFILE_SOURCE).read_bytes())
_fixture_profile["runtime"]["cli_sha256"] = digest(FIXTURE_CLI_BYTES)
FIXTURE_PROFILE_RAW = encode_json(_fixture_profile)


def toy_bundle(root, marker="first"):
    files = {name: ("fixture " + name).encode() for name in pi.REQUIRED}
    files.update({"bin/craft-codex-executor.exe": ("fixture owner " + marker).encode(),
                  "bin/codex-app-server-driver.exe": b"fixture driver, no provider",
                  cc.CODEX_PROFILE_ENTRY: FIXTURE_PROFILE_RAW,
                  "entry-protocol.json": b'{"fixture":true}', "licenses/fixture.txt": b"fixture license",
                  "source/fixture.rs": b"// fixture source", "provenance/source.json": b'{"fixture":true}'})
    for name, data in files.items():
        atomic(root / name, data)
    value = {"name": "craft-codex-bundle", "version": "0.1.0", "contract": copy.deepcopy(cc.CONTRACT),
             "codex": {"version": cc.CODEX_VERSION, "protocol": cc.CODEX_PROTOCOL},
             "codex_profile": {"id": cc.CODEX_PROFILE_ID, "path": cc.CODEX_PROFILE_ENTRY,
                               "sha256": digest(FIXTURE_PROFILE_RAW)},
             "base_commit": pi.BASE_COMMIT, "backend_id": cc.BACKEND_ID, "permission_contract": cc.PERMISSION_CONTRACT,
             "artifact": {"os": "windows", "arch": "x86_64", "target": "x86_64-pc-windows-gnu", "profile": "release", "source_commit": "a" * 40, "build_source": "offline fixture; never a product artifact"},
             "runtime": {"entry": "bin/craft-codex-executor.exe", "entry_kind": "native", "driver": "bin/codex-app-server-driver.exe", "driver_kind": "native", "entry_protocol": "entry-protocol.json", "required_files": ["entry-protocol.json"]},
             "files": {name: digest(data) for name, data in files.items()}}
    atomic(root / cc.MANIFEST, encode_json(value))
    return value


def toy_reverse(root):
    for name in set(cc.REVERSE_FILES) | {"RULES.md", "skills/SKILL.md", "skills/MASTER-ROUTING.md", "skills/config/routing.json", "skills/ops/scope-contract.md", "skills/ops/evidence-finding-path.md", "skills/scripts/master-route.sh"}:
        atomic(root / name, ("offline fixture " + name).encode())
    atomic(root / "VERSION", b"1.9.0\n")
    value = {"schema_version": 1, "contract_id": "reverse.r46.codex-execution-backend", "contract_version": 1,
             "min_reverse_version": "1.9.0", "capabilities": cc.REVERSE_CAPABILITIES,
             "required_files": [{"path": name, "sha256": digest((root / name).read_bytes())} for name in cc.REVERSE_FILES]}
    atomic(root / cc.REVERSE_DESCRIPTOR, encode_json(value))
    return value


class CraftCodexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=fixtures.LOCAL)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        # Copy only the small host templates; never enumerate/copy frozen runtime/vendor.
        shutil.copytree(REPO / "adapters/codex", self.source / "adapters/codex")
        atomic(self.source / "components.json", (REPO / "components.json").read_bytes())
        atomic(self.source / cc.PROFILE_SOURCE, FIXTURE_PROFILE_RAW)
        for name in ("craft_codex.py", "craft.py", "configuration.py", "versions.py"):
            atomic(self.source / "scripts" / name, (REPO / "scripts" / name).read_bytes())
        resources = {"entry.py": b"# inert offline entry fixture; no execution qualification\n",
                     "builder-instructions.md": b"fixture instructions",
                     "skills/reconstruction-execution/SKILL.md": b"fixture restricted skill",
                     "skills/reconstruction-execution/references/execution.md": b"fixture reference"}
        for name, data in resources.items():
            atomic(self.source / "adapters/craft-codex" / name, data)
        self.root, self.agent, self.reverse = (self.base / n for n in ("stack", "agent", "reverse"))
        self.bundle = self.base / "bundle"
        self.manifest = toy_bundle(self.bundle)
        self.descriptor = toy_reverse(self.reverse)
        self.codex = self.base / "native/codex.exe"
        atomic(self.codex, FIXTURE_CLI_BYTES)
        self.codex.chmod(0o755)
        self.before = b'model = "gpt/gpt-6.1-sol"\nmodel_provider = "magpie"\nmodel_reasoning_effort = "high"\n[node_repl]\nenabled = true\n'
        atomic(self.agent / "config.toml", self.before)
        atomic(self.agent / "AGENTS.md", b"user instructions\n")
        self.args = cli.parser().parse_args(["install", "--root", str(self.root), "--agent-dir", str(self.agent), "--client", "codex", "--reverse-root", str(self.reverse), "--components", "reverse,spec-kit", "--with-craft", "--craft-bundle", str(self.bundle), "--craft-codex-cli", str(self.codex), "--apply"])
        self.calls, self.failure = [], None
        for p in (patch.object(w, "REPO", self.source), patch.object(w, "run", self.fake_run),
                  patch.object(cc, "profile_bytes", self.fixture_profile_bytes),
                  patch.object(w.ro, "_user_home", lambda: self.base / "fixture-home"),
                  patch.object(w.shutil, "which", lambda name: str(self.base / name)),
                  patch.object(pi, "host", lambda: {"os": "windows", "arch": "x86_64"})):
            p.start()
            self.addCleanup(p.stop)

    def fixture_profile_bytes(self, repo=None):
        return cc.no_links((Path(repo) if repo is not None else self.source) / cc.PROFILE_SOURCE).read_bytes()

    def fake_run(self, argv, *, cwd, env=None):
        argv = [str(x) for x in argv]
        if argv == [str(self.codex.resolve()), "--version"]:
            self.calls.append(argv)
            return "codex-cli " + cc.CODEX_VERSION
        if argv[-1:] == ["--inspect"]:
            self.calls.append(argv)
            return json.dumps({"name": "craft-codex-executor", "contract_version": 1, "backend_id": cc.BACKEND_ID,
                               "permission_contract": cc.PERMISSION_CONTRACT, "commands": ["--inspect", "--version", "--validate", "--prepare", "--run"]})
        return fixtures.Fixture.fake_run(self, argv, cwd=cwd, env=env)

    def plan(self):
        return w.make_plan(self.args, fixtures.metadata)

    def install(self):
        return w.install(self.plan(), self.args)

    def test_source_profile_cannot_be_reclaimed_by_refreshing_only_file_inventory(self):
        name = self.manifest["codex_profile"]["path"]
        changed = FIXTURE_PROFILE_RAW + b"\n"
        atomic(self.bundle / name, changed)
        self.manifest["files"][name] = digest(changed)
        atomic(self.bundle / cc.MANIFEST, encode_json(self.manifest))
        with self.assertRaisesRegex(InstallError, "source profile not covered"):
            self.plan()
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / ".installer").exists())

    def test_codex_profile_is_local_and_pi_contract_unchanged(self):
        before = copy.deepcopy(pi.CONTRACT)
        self.assertIs(w.craft_profile({"client": "pi"}, pi.CONTRACT), pi)
        self.assertIs(w.craft_profile({"client": "codex"}, cc.CONTRACT), cc)
        for client, contract in (("pi", cc.CONTRACT), ("codex", pi.CONTRACT), ("claude", cc.CONTRACT)):
            with self.subTest(client=client), self.assertRaises(InstallError):
                w.craft_profile({"client": client}, contract)
        self.assertEqual(pi.CONTRACT, before)

    def test_explicit_cli_required_no_pi_or_path_fallback(self):
        self.args.craft_codex_cli = None
        with self.assertRaisesRegex(InstallError, "craft-codex-cli"):
            self.plan()
        self.assertEqual(self.calls, [])
        self.args.craft_codex_cli = str(self.codex)
        self.args.craft_pi_node = str(self.codex)
        with self.assertRaisesRegex(InstallError, "do not match"):
            self.plan()

    def test_install_copies_exact_bundle_resources_without_global_craft_skill(self):
        receipt = self.install()
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual((self.agent / "config.toml").read_bytes(), self.before)
        self.assertTrue((self.agent / "AGENTS.md").read_bytes().startswith(b"user instructions\n"))
        self.assertEqual(cc.inventory(receipt["craft"]["root"]), cc.inventory(self.bundle))
        self.assertEqual(Path(receipt["craft"]["resources"]).name, "craft-codex")
        self.assertEqual(receipt["craft"]["entry"], str(Path(receipt["craft"]["resources"]) / "entry.py"))
        self.assertNotIn("pi_runtime", receipt["craft"])
        self.assertEqual(receipt["craft"]["codex_runtime"], {"version": cc.CODEX_VERSION, "cli": cc.cli_identity(self.codex), "config_root": str(self.agent), "protocol": cc.CODEX_PROTOCOL,
                                                              "profile": cc.profile_identity(receipt["components"]["craft"])})
        self.assertNotIn("host", receipt["craft"]["codex_runtime"])
        self.assertEqual({name for name in receipt["craft"]["files"] if name.startswith("bin/")},
                         {"bin/craft-codex-executor.exe", "bin/codex-app-server-driver.exe"})
        self.assertEqual(list((self.agent / "skills").glob("*/SKILL.md")), [self.agent / "skills/reverse-workflow/SKILL.md"])
        self.assertFalse((self.agent / "settings.json").exists())
        self.assertFalse((Path(receipt["craft"]["resources"]) / "runtime").exists())
        self.assertNotIn("CRAFT_PI_", str(cc.entry_environment(receipt)))

    def test_native_entry_gate_and_offline_inspect_are_callable(self):
        receipt = self.install()
        command = cc.entry_command(receipt)
        self.assertEqual(command, [str(Path(receipt["craft"]["root"]) / "bin/craft-codex-executor.exe")])
        result = cc.inspect_backend(receipt, self.fake_run)
        self.assertEqual(result["backend_id"], cc.BACKEND_ID)
        self.assertEqual(self.calls[-1], [*command, "--inspect"])
        env = cc.entry_environment(receipt)
        self.assertEqual(env["CRAFT_CODEX_CLI"], str(self.codex))
        self.assertEqual(env["CRAFT_CODEX_HOME"], env["CODEX_HOME"])
        self.assertEqual(env["CRAFT_CODEX_RUNTIME_PROFILE_SHA256"], digest(FIXTURE_PROFILE_RAW))
        self.assertEqual(Path(env["CRAFT_CODEX_RUNTIME_PROFILE"]).read_bytes(), FIXTURE_PROFILE_RAW)
        self.assertEqual(digest(Path(env["CRAFT_CODEX_RUNTIME_PROFILE"]).read_bytes()), env["CRAFT_CODEX_RUNTIME_PROFILE_SHA256"])
        self.assertFalse(any(key.startswith("CRAFT_CODEX_SERVER") for key in env))
        with patch.dict(os.environ, {"CRAFT_PI_ENTRY": "must-not-propagate"}):
            self.assertNotIn("CRAFT_PI_ENTRY", cc.entry_environment(receipt))
        bad = lambda command, **kw: "codex-cli " + cc.CODEX_VERSION if command[-1] == "--version" else json.dumps({"name": "craft-pi-executor"})
        with self.assertRaisesRegex(InstallError, "inspection contract"):
            cc.inspect_backend(receipt, bad)

    def test_bundle_manifest_contract_and_provenance_fail_closed(self):
        changes = [lambda m: m.update(name="craft-pi-bundle"), lambda m: m.update(version="0.2.0"),
                   lambda m: m.update(backend_id="craft-pi-rpc-v1"), lambda m: m.update(permission_contract="unknown"),
                   lambda m: m["contract"].update(min_reader=2), lambda m: m["contract"].update(version=True),
                   lambda m: m["artifact"].update(target="unknown"), lambda m: m["artifact"].update(profile="debug"),
                   lambda m: m["runtime"].update(entry="../escape"), lambda m: m["runtime"].update(entry_kind="python"),
                   lambda m: m["runtime"].update(entry_protocol="missing"), lambda m: m.update(pi={"version": "1.5.0"}),
                   lambda m: m["codex"].update(version="0.167.0"), lambda m: m["codex"].update(protocol="app-server")]
        for change in changes:
            value = copy.deepcopy(self.manifest)
            change(value)
            atomic(self.bundle / cc.MANIFEST, encode_json(value))
            with self.subTest(value=value), self.assertRaises(InstallError):
                cc.bundle(self.bundle)
        atomic(self.bundle / cc.MANIFEST, encode_json(self.manifest))
        with patch.object(pi, "host", lambda: {"os": "linux", "arch": "x86_64"}), self.assertRaisesRegex(InstallError, "unsupported on this host"):
            cc.bundle(self.bundle)

    def test_plan_bundle_cli_resource_drift_rejected_before_mutation(self):
        targets = [self.bundle / "bin/codex-app-server-driver.exe", self.bundle / cc.CODEX_PROFILE_ENTRY, self.codex,
                   self.source / "adapters/craft-codex/builder-instructions.md"]
        for target in targets:
            plan = self.plan()
            before = target.read_bytes()
            atomic(target, before + b"changed")
            self.calls.clear()
            with self.subTest(target=target), self.assertRaises(InstallError):
                w.install(plan, self.args)
            self.assertFalse((self.root / ".installer/receipt.json").exists())
            atomic(target, before)

    def test_codex_descriptor_rejects_pi_caps_and_freezes_common_files(self):
        self.assertEqual(cc.reverse_contract(self.reverse)["descriptor"], cc.REVERSE_DESCRIPTOR)
        descriptor = copy.deepcopy(self.descriptor)
        descriptor["capabilities"] = pi.REVERSE_CAPABILITIES
        atomic(self.reverse / cc.REVERSE_DESCRIPTOR, encode_json(descriptor))
        with self.assertRaisesRegex(InstallError, "Codex descriptor capabilities"):
            self.plan()
        atomic(self.reverse / cc.REVERSE_DESCRIPTOR, encode_json(self.descriptor))
        plan = self.plan()
        target = self.reverse / cc.REVERSE_FILES[0]
        atomic(target, target.read_bytes() + b"changed")
        with self.assertRaisesRegex(InstallError, "needs-contract"):
            w.install(plan, self.args)

    def test_runtime_and_installed_resource_drift_deny_verify_and_entry(self):
        receipt = self.install()
        for target in (self.codex, Path(receipt["craft"]["resources"]) / "builder-instructions.md", Path(receipt["craft"]["root"]) / "bin/codex-app-server-driver.exe", Path(receipt["craft"]["root"]) / cc.CODEX_PROFILE_ENTRY):
            before = target.read_bytes()
            atomic(target, before + b"changed")
            with self.subTest(target=target):
                self.assertFalse(w.verify(self.root)["ok"])
                with self.assertRaisesRegex(InstallError, "entry denied"):
                    cc.entry_command(receipt)
            atomic(target, before)

    def test_update_reuses_explicit_cli_and_restore_preserves_user_config(self):
        first = self.install()
        old_receipt = (self.root / ".installer/receipt.json").read_bytes()
        candidate = self.base / "candidate"
        toy_bundle(candidate, "second")
        self.args.craft_bundle = str(candidate)
        self.args.craft_codex_cli = None
        plan = self.plan()
        self.assertEqual(plan["scope"]["craft_codex_cli"], str(self.codex))
        second = w.install(plan, self.args)
        self.assertNotEqual(first["craft"]["root"], second["craft"]["root"])
        self.assertEqual(first["craft"]["codex_runtime"]["profile"], second["craft"]["codex_runtime"]["profile"])
        self.assertEqual(cc.entry_environment(second)["CRAFT_CODEX_RUNTIME_PROFILE_SHA256"], digest(FIXTURE_PROFILE_RAW))
        atomic(self.agent / "config.toml", self.before + b'user_setting = "later"\n')
        restored = w.restore(self.root, apply=True)
        self.assertFalse(any(x["conflicts"] for x in restored["files"]))
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), old_receipt)
        self.assertIn(b'user_setting = "later"', (self.agent / "config.toml").read_bytes())
        self.assertEqual(cc.entry_environment(first)["CRAFT_CODEX_RUNTIME_PROFILE_SHA256"], first["craft"]["codex_runtime"]["profile"]["sha256"])
        self.assertTrue(w.verify(self.root)["ok"])

    def test_late_failure_rolls_back_host_resources_and_retains_previous_receipt(self):
        first = self.install()
        old_receipt = (self.root / ".installer/receipt.json").read_bytes()
        old_agents = (self.agent / "AGENTS.md").read_bytes()
        candidate = self.base / "candidate"
        toy_bundle(candidate, "second")
        self.args.craft_bundle = str(candidate)
        original = Journal.write
        def fail(journal, target, data, *args, **kwargs):
            if Path(target) == self.root / ".installer/receipt.json":
                raise InstallError("fixture activation failure")
            return original(journal, target, data, *args, **kwargs)
        with patch.object(Journal, "write", fail), self.assertRaisesRegex(InstallError, "activation failure"):
            self.install()
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), old_receipt)
        self.assertEqual((self.agent / "AGENTS.md").read_bytes(), old_agents)
        self.assertEqual(cc.entry_command(first)[0], str(Path(first["craft"]["root"]) / "bin/craft-codex-executor.exe"))

    def test_recovery_and_restore_use_journal_contract_and_reject_unknown_reader(self):
        target = self.root / "versions/interrupted/craft-codex/entry.py"
        journal = Journal(self.root / ".installer/transactions/interrupted")
        journal.data.update(craft_contract=copy.deepcopy(cc.CONTRACT), craft_client="codex")
        journal.write(target, b"managed fixture")
        self.assertEqual(w.recover_pending_transactions(self.root), ["interrupted"])
        self.assertFalse(target.exists())
        other = Journal(self.root / ".installer/transactions/unknown")
        other.data.update(craft_contract={**cc.CONTRACT, "min_reader": 999}, craft_client="codex")
        other.write(target, b"must preserve")
        with self.assertRaisesRegex(InstallError, "unsupported"):
            w.recover_pending_transactions(self.root)
        with self.assertRaisesRegex(InstallError, "unsupported"):
            w.restore(self.root, "unknown", apply=True)
        self.assertEqual(target.read_bytes(), b"must preserve")

    def test_restore_conflict_keeps_receipt(self):
        receipt = self.install()
        before = (self.root / ".installer/receipt.json").read_bytes()
        target = Path(receipt["craft"]["resources"]) / "builder-instructions.md"
        atomic(target, b"later user edits")
        result = w.restore(self.root, apply=True)
        self.assertTrue(any(x["conflicts"] for x in result["files"]))
        self.assertEqual((self.root / ".installer/receipt.json").read_bytes(), before)
        self.assertEqual(target.read_bytes(), b"later user edits")

    def test_reviewed_profile_manifest_and_complete_file_coverage_are_required(self):
        changes = [lambda m: m.pop("codex_profile"),
                   lambda m: m["codex_profile"].update(id="unreviewed"),
                   lambda m: m["codex_profile"].update(sha256="f" * 64),
                   lambda m: m["codex_profile"].update(path="../unreviewed"),
                   lambda m: m["codex_profile"].update(listener="127.0.0.1:1234"),
                   lambda m: m.update(codex_host={"profile": "obsolete"}),
                   lambda m: m["runtime"].update(host="bin/obsolete.exe", host_kind="native"),
                   lambda m: m["runtime"].update(args=["--listen", "tcp://127.0.0.1:1234"])]
        for change in changes:
            value = copy.deepcopy(self.manifest)
            change(value)
            atomic(self.bundle / cc.MANIFEST, encode_json(value))
            with self.subTest(value=value), self.assertRaises(InstallError):
                cc.bundle(self.bundle)
        for mode in ("missing", "empty", "uncovered"):
            value = toy_bundle(self.bundle)
            profile = self.bundle / cc.CODEX_PROFILE_ENTRY
            if mode == "empty":
                atomic(profile, b"")
                value["files"][cc.CODEX_PROFILE_ENTRY] = digest(b"")
            else:
                value["files"].pop(cc.CODEX_PROFILE_ENTRY)
                if mode == "missing":
                    profile.unlink()
            atomic(self.bundle / cc.MANIFEST, encode_json(value))
            with self.subTest(mode=mode), self.assertRaises(InstallError):
                cc.bundle(self.bundle)

    def test_controls_and_cli_pin_cannot_be_reclaimed_by_rehashing_profile_and_manifest(self):
        changes = [lambda p: p["runtime"].update(cli_sha256="f" * 64),
                   lambda p: p["startup"]["config"].update({"agents.enabled": True}),
                   lambda p: p["startup"]["disable_features"].remove("code_mode_host"),
                   lambda p: p["thread"].update(environments=[{"unreviewed": True}]),
                   lambda p: p["turn"].update(approvalPolicy="on-request"),
                   lambda p: p["operations"].append("research_start")]
        for change in changes:
            profile = json.loads(FIXTURE_PROFILE_RAW)
            change(profile)
            changed = encode_json(profile)
            value = copy.deepcopy(self.manifest)
            value["codex_profile"]["sha256"] = value["files"][cc.CODEX_PROFILE_ENTRY] = digest(changed)
            atomic(self.bundle / cc.CODEX_PROFILE_ENTRY, changed)
            atomic(self.bundle / cc.MANIFEST, encode_json(value))
            with self.subTest(profile=profile), self.assertRaisesRegex(InstallError, "differs from reviewed reader profile"):
                self.plan()
        self.assertEqual(self.calls, [])

    def test_profile_reader_and_inspection_survive_deleted_source_bundle(self):
        receipt = self.install()
        profile = receipt["craft"]["codex_runtime"]["profile"]
        self.assertEqual(set(profile), {"id", "path", "sha256"})
        self.assertEqual(profile["path"], cc.CODEX_PROFILE_ENTRY)
        shutil.rmtree(self.bundle)
        self.assertEqual(cc.profile_identity(receipt["components"]["craft"]), profile)
        self.assertTrue(w.verify(self.root)["ok"])
        self.assertEqual(cc.inspect_backend(receipt, self.fake_run)["backend_id"], cc.BACKEND_ID)
        stale = {"CRAFT_CODEX_SERVER": str(self.codex), "CRAFT_CODEX_SERVER_SHA256": "f" * 64,
                 "CRAFT_CODEX_SERVER_SOURCE_SHA256": "0" * 64, "CRAFT_CODEX_HOST_PROFILE": "obsolete",
                 "TOOL_POLICY_TAG": "obsolete", "CRAFT_CODEX_LISTEN": "tcp://127.0.0.1:1234",
                 "CRAFT_CODEX_SHA256": "obsolete"}
        with patch.dict(os.environ, {**stale, "CRAFT_CODEX_RUNTIME_PROFILE": str(self.bundle / cc.CODEX_PROFILE_ENTRY),
                                     "CRAFT_CODEX_RUNTIME_PROFILE_SHA256": "0" * 64}):
            env = cc.entry_environment(receipt)
            self.assertEqual(env["CRAFT_CODEX_RUNTIME_PROFILE_SHA256"], profile["sha256"])
            self.assertEqual(env["CRAFT_CODEX_CLI_SHA256"], receipt["craft"]["codex_runtime"]["cli"]["sha256"])
            self.assertEqual(env["CRAFT_CODEX_RUNTIME_PROFILE"], str(Path(receipt["craft"]["root"]) / profile["path"]))
            self.assertEqual(digest(Path(env["CRAFT_CODEX_RUNTIME_PROFILE"]).read_bytes()), profile["sha256"])
            for key in stale:
                self.assertNotIn(key, env)
                self.assertNotIn(key, cc.entry_environment())
        library = Path(receipt["craft"]["resources"]) / "lib"
        code = 'import sys;sys.path.insert(0,sys.argv[1]);import craft_codex as cc;print(cc.digest(cc.profile_bytes()));print(cc.reviewed_profile()[1]["id"])'
        result = subprocess.run([sys.executable, "-B", "-c", code, str(library)], cwd=self.base,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [digest(FIXTURE_PROFILE_RAW), cc.CODEX_PROFILE_ID])
        self.assertEqual((library / "codex-profile.json").read_bytes(), FIXTURE_PROFILE_RAW)
        self.assertEqual((self.agent / "config.toml").read_bytes(), self.before)

    def test_profile_receipt_identity_and_installed_bytes_fail_before_entry_dispatch(self):
        receipt = self.install()
        original = (self.root / ".installer/receipt.json").read_bytes()
        for key, value in (("path", str(self.bundle / cc.CODEX_PROFILE_ENTRY)), ("sha256", "f" * 64), ("id", "unreviewed")):
            bad = copy.deepcopy(receipt)
            bad["craft"]["codex_runtime"]["profile"][key] = value
            atomic(self.root / ".installer/receipt.json", encode_json(bad))
            with self.subTest(key=key):
                self.assertFalse(w.verify(self.root)["ok"])
                with self.assertRaisesRegex(InstallError, "profile receipt identity"):
                    cc.entry_environment(bad)
        atomic(self.root / ".installer/receipt.json", original)
        target = Path(receipt["craft"]["root"]) / cc.CODEX_PROFILE_ENTRY
        atomic(target, b"changed runtime profile")
        self.calls.clear()
        with self.assertRaisesRegex(InstallError, "source profile bytes drift"):
            cc.entry_environment(receipt)
        with self.assertRaisesRegex(InstallError, "entry denied"):
            cc.inspect_backend(receipt, self.fake_run)
        self.assertEqual(self.calls, [])
        self.assertFalse(w.verify(self.root)["ok"])

    def test_cli_bytes_must_match_reviewed_profile_even_when_version_would_match(self):
        atomic(self.codex, b"unreviewed binary with the same claimed version")
        with self.assertRaisesRegex(InstallError, "CLI binary differs from reviewed stock profile"):
            self.plan()
        self.assertFalse(any(command[-1:] == ["--version"] for command in self.calls))
        self.assertFalse((self.root / ".installer/receipt.json").exists())

    def test_reader_profile_source_and_installed_copy_are_frozen(self):
        plan = self.plan()
        source = self.source / cc.PROFILE_SOURCE
        atomic(source, FIXTURE_PROFILE_RAW + b"\n")
        with self.assertRaises(InstallError):
            w.install(plan, self.args)
        atomic(source, FIXTURE_PROFILE_RAW)
        receipt = self.install()
        installed = Path(receipt["craft"]["resources"]) / "lib/codex-profile.json"
        atomic(installed, FIXTURE_PROFILE_RAW + b"\n")
        self.assertFalse(w.verify(self.root)["ok"])
        with self.assertRaisesRegex(InstallError, "entry denied"):
            cc.entry_command(receipt)

    def test_adding_stock_profile_to_core_codex_receipt_keeps_scope_identity(self):
        self.args.with_craft = False
        self.args.craft_bundle = self.args.craft_codex_cli = None
        before = self.install()
        self.assertIsNone(before["craft"])
        self.args.with_craft = True
        self.args.craft_bundle, self.args.craft_codex_cli = str(self.bundle), str(self.codex)
        plan = self.plan()
        self.assertTrue(w.identity_compatible(before["scope"], before["scope"]["components"], plan["scope"]))
        receipt = w.install(plan, self.args)
        self.assertEqual(w.normalized_identity(before["scope"]), w.normalized_identity(receipt["scope"]))
        self.assertEqual(receipt["previous_transaction"], before["transaction"])
        self.assertEqual(receipt["craft"]["codex_runtime"]["config_root"], str(self.agent))
        self.assertEqual((self.agent / "config.toml").read_bytes(), self.before)
        self.assertEqual(self.codex.read_bytes(), b"offline native CLI fixture")
        self.assertTrue(w.verify(self.root)["ok"])

    def test_profileless_draft_receipt_denies_update_but_still_allows_conditional_restore(self):
        original_write = Journal.write
        def write_draft(journal, target, data, *args, **kwargs):
            if Path(target) == self.root / ".installer/receipt.json":
                receipt = json.loads(data)
                receipt["craft"]["codex_runtime"].pop("profile")
                data = encode_json(receipt)
            return original_write(journal, target, data, *args, **kwargs)
        # Model an older writer's actual journaled receipt, not a later user edit.
        with patch.object(Journal, "write", write_draft):
            self.install()
        self.assertFalse(w.verify(self.root)["ok"])
        with self.assertRaisesRegex(InstallError, "Active Craft drift"):
            self.install()
        self.assertEqual((self.agent / "config.toml").read_bytes(), self.before)
        result = w.restore(self.root, apply=True)
        self.assertFalse(any(item["conflicts"] for item in result["files"]))
        self.assertEqual((self.agent / "config.toml").read_bytes(), self.before)

    def test_exact_prerelease_version_is_preserved_and_mismatch_denied(self):
        plan = self.plan()
        self.assertEqual(plan["craft_runtime"]["version"], "0.167.0-alpha.4.1")
        self.assertEqual(plan["craft_runtime"]["protocol"], "app-server-v2")
        for version in ("0.167.0", "0.167.0-alpha.4.2", "anything", "0.167.0-alpha.4.1\nother"):
            with self.subTest(version=version), self.assertRaisesRegex(InstallError, "version/hash mismatch"):
                cc.runtime_identity(plan["scope"], plan["components"]["craft"], lambda *a, **kw: "codex-cli " + version)

    def test_publication_records_artifact_evidence_without_claiming_live_verification(self):
        current = cc.bundle(self.bundle)
        self.assertEqual(cc.update_record({}, current)["publication"]["status"], "pending")
        evidence = {"tag": "craft-codex-v0.1.0", "release_id": 123, "asset_id": 456}
        current["manifest"]["artifact"]["publication"] = evidence
        result = cc.update_record({}, current)["publication"]
        self.assertEqual(result["status"], "artifact-evidence-recorded")
        self.assertEqual(result["evidence"], evidence)

    def test_accept_reports_only_offline_contract_and_retains_qualification_gaps(self):
        self.install()
        def fake_subprocess(command, **kwargs):
            flag = "-OutDir" if "-OutDir" in command else "--out-dir"
            atomic(Path(command[command.index(flag) + 1]) / "route-scope.md", b"offline route fixture")
            return type("Result", (), {"returncode": 0})()
        temporary = tempfile.TemporaryDirectory
        with patch.object(w.subprocess, "run", fake_subprocess), patch.object(w.tempfile, "TemporaryDirectory", lambda **kwargs: temporary(dir=self.base, **kwargs)):
            result = w.accept(self.root)
        self.assertTrue(result["ok"], result)
        check = next(item for item in result["checks"] if item["name"] == "craft_codex_offline_entry_contract")
        self.assertTrue(check["ok"])
        self.assertIn("live execution unverified", check["detail"]["qualification"])
        self.assertTrue(any("provider/model/effort" in item for item in result["unverified"]))

    @unittest.skipUnless(os.name == "nt", "Windows path budget")
    def test_codex_path_budget_uses_actual_resource_and_config_targets(self):
        selected = w.scope(self.args)
        selected["root"] = str(self.base / ("x" * 150))
        resources = cc.resource_identity(cc.resource_files(self.source, Path(selected["root"]) / ".installer/receipt.json"))
        with self.assertRaisesRegex(InstallError, "craft-path-too-long"):
            w._craft_target_path_preflight(selected, {"craft": cc.bundle(self.bundle)}, resources)

    def test_frozen_cli_replay_and_mismatched_cli_rejection(self):
        plan = self.plan()
        path = self.base / "plan.json"
        atomic(path, encode_json(plan))
        argv = ["install", "--root", str(self.root), "--plan-file", str(path), "--apply"]
        with patch.object(w, "resolve", side_effect=AssertionError("unexpected lookup")), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli.main(argv), 0)
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli.main([*argv, "--craft-codex-cli", str(self.base / "other.exe")]), 1)
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli.main(["verify", "--root", str(self.root), "--craft-codex-cli", str(self.codex)]), 1)


if __name__ == "__main__":
    unittest.main()
