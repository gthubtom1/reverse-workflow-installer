#!/usr/bin/env python3
"""Offline Codex owner-loop fixture.

This fixture owns every authority/source/baseline byte under --stage. It uses the
real prepared Handoff/AcceptedResearch path and the real stock Codex app-server
bridge. The only model substitute is a localhost Responses SSE server.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import uuid
from typing import Any

RAW_TOOLS = [
    "build_files_list", "build_file_read", "build_file_write", "build_file_edit",
    "build_command_run", "build_checklist",
]
PROFILE_ID = "codex-stock-bounded-v1"
BACKEND = "craft-codex-app-server-v1"
PERMISSION = "codex-dynamic-bounded-v1"
VERSION = "0.167.0-alpha.4.1"
GOOD_SOURCE = '''use std::io::{self, Read};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).unwrap();
    let name = input.trim();
    std::fs::write("state.txt", name).unwrap();
    let saved = std::fs::read_to_string("state.txt").unwrap();
    println!("saved: {saved}");
}
'''
BAD_SOURCE = 'fn main(){println!("unimplemented");}\n'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ref(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha(path)}


def write_json(path: Path, value: Any) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8", newline="\n")
    return ref(path)


def load_entry_env(path: Path) -> dict[str, str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("entry environment JSON must be an object")
    allowed = {
        "CRAFT_CODEX_CLI", "CRAFT_CODEX_CLI_SHA256", "CRAFT_CODEX_VERSION",
        "CRAFT_CODEX_HOME", "CODEX_HOME", "CRAFT_BUNDLE_ROOT",
        "CRAFT_CODEX_RUNTIME_PROFILE", "CRAFT_CODEX_RUNTIME_PROFILE_SHA256",
        "CRAFT_BUILDER_INSTRUCTIONS",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"entry environment contains unsupported keys: {unknown}")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ValueError("entry environment values must be strings")
    required = {"CRAFT_CODEX_CLI", "CRAFT_CODEX_CLI_SHA256", "CRAFT_CODEX_VERSION",
                "CRAFT_CODEX_RUNTIME_PROFILE", "CRAFT_CODEX_RUNTIME_PROFILE_SHA256",
                "CRAFT_BUILDER_INSTRUCTIONS", "CRAFT_BUNDLE_ROOT"}
    if not required.issubset(value):
        raise ValueError(f"entry environment is missing: {sorted(required - set(value))}")
    if "CRAFT_CODEX_HOME" not in value and "CODEX_HOME" not in value:
        raise ValueError("entry environment requires CRAFT_CODEX_HOME or CODEX_HOME")
    return value


def safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:2000]

def source_digest(root: Path) -> str:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in {"target", "node_modules", ".git"} for part in rel.parts):
            continue
        if path.name == ".craft-owner.lock":
            continue
        files.append(path)
    files.sort(key=lambda p: p.relative_to(root).as_posix())
    h = hashlib.sha256()
    for path in files:
        h.update(path.relative_to(root).as_posix().encode())
        h.update(b"\0")
        h.update(sha(path).encode())
        h.update(b"\0")
    return h.hexdigest()


def approved_execution(h: dict[str, Any]) -> dict[str, Any]:
    return {
        "original": h["original"], "baseline": h["baseline"],
        "driver": h["driver"], "instructions": h["instructions"],
        "provider_manifest": h["provider_manifest"],
        "credential_env_keys": h["credential_env_keys"],
        "owner_output": h["owner_output"], "owner_id": h["owner_id"],
        "stop_marker": h["stop_marker"], "message": h["message"],
        "writable_relative": h["writable_relative"],
        "protected_relative": h["protected_relative"],
        "read_references": h["read_references"], "workspace": h["workspace"],
        "application": h["application"], "target": h["original"]["target"],
        "target_identity": h["original"]["target_identity"], "stack": h["stack"],
        "check_plan": h["check_plan"], "model": h["model"],
        "commands": h["commands"], "build": h["build"], "budget": h["budget"],
    }


def make_handoff(root: Path, profile: Path, driver: Path, mode: str, instruction_path: Path | None = None, cargo: Path | None = None) -> tuple[Path, dict[str, Any]]:
    authority = root / "authority"
    source = root / "source"
    baseline_root = root / "baseline"
    source.mkdir(parents=True)
    baseline_root.mkdir(parents=True)
    (source / "src").mkdir()
    (source / "Cargo.toml").write_text(
        '[package]\nname="offline-persistence-fixture"\nversion="0.1.0"\nedition="2024"\n',
        encoding="utf-8",
    )
    (source / "Cargo.lock").write_text(
        '# This file is automatically @generated by Cargo.\n'
        '# It is not intended for manual editing.\n'
        'version = 4\n\n'
        '[[package]]\n'
        'name = "offline-persistence-fixture"\n'
        'version = "0.1.0"\n',
        encoding="utf-8",
    )
    (source / "rust-toolchain.toml").write_text(
        '[toolchain]\nchannel="stable-x86_64-pc-windows-gnu"\n', encoding="utf-8"
    )
    (source / "src/main.rs").write_text(BAD_SOURCE, encoding="utf-8")
    cargo = cargo or Path("cargo")
    cargo_q = str(cargo).replace('"', '""')
    (source / "build.cmd").write_text(
        f'@echo off\r\n"{cargo_q}" build --quiet --offline\r\n', encoding="utf-8"
    )

    original_path = authority / "original.txt"
    original_path.parent.mkdir(parents=True)
    original_path.write_text("Offline owner fixture original identity.\n", encoding="utf-8")
    bundle_path = authority / "bundle.json"
    bundle_path.write_text(json.dumps({"kind": "owned-console-bundle", "version": 1}), encoding="utf-8")
    external_path = authority / "external-observation.json"
    external_path.write_text(json.dumps({"kind": "offline-owned-observation", "expected_name": "Ada"}), encoding="utf-8")
    scenario_path = baseline_root / "scenario.json"
    state_hash = hashlib.sha256(b"Ada").hexdigest()
    scenario = {
        "version": 2, "task_id": "T002", "evidence_id": "offline-owned-observation-1",
        "harness": "direct-exec-v1", "reset": "fresh-copy-v1", "runtime_files": [],
        "seed_files": [{"relative_path": "state.txt", "content": None}],
        "program": "target/debug/offline-persistence-fixture.exe", "arguments": [],
        "stdin": "Ada\n", "environment": {}, "timeout_secs": 10, "exit_code": 0,
        "stdout": "saved: Ada\n", "stderr": "",
        "state_files": [{"relative_path": "state.txt", "sha256": state_hash}],
    }
    write_json(scenario_path, scenario)

    authority_bytes = {
        "case": b"Controlled owned console fixture case; no production Evidence.\n",
        "scope": b"Implement T002 only in the approved source copy. Preserve authority bytes.\n",
        "workitem": b"W-console: persist supplied name; dependency T001 ready.\n",
        "feature": b"F-console: local persisted console response.\n",
        "spec": b"Input Ada; output saved: Ada newline and state bytes Ada.\n",
        "plan": b"Use supplied Rust project and frozen offline build command.\n",
        "tasks": b"# Tasks\n- [X] T001 Freeze designed console observation\n- [ ] T002 Implement persistence\n",
        "acceptance": b"Candidate only; original primary retains semantic acceptance.\n",
    }
    authority_refs: dict[str, dict[str, Any]] = {}
    for name, data in authority_bytes.items():
        path = authority / f"{name}.md"
        path.write_bytes(data)
        authority_refs[name] = ref(path)
    selection = {
        "version": 1, "spec": authority_refs["spec"], "tasks": authority_refs["tasks"],
        "selected_tasks": [{"id": "T002", "depends_on": ["T001"]}],
        "dependencies_ready": ["T001"],
    }
    selection_ref = write_json(authority / "selection.json", selection)
    plan = [
        {"id": "build", "implementation": "bounded-command-build-v1", "required": True,
         "baseline": None, "kind": None, "depends_on": []},
        {"id": "external-scenario", "implementation": "external-scenario-v2", "required": True,
         "baseline": "persist", "kind": "scenario", "depends_on": ["build"]},
    ]
    plan_ref = write_json(authority / "check-plan.json", plan)
    profile_ref = ref(profile)
    driver_ref = ref(driver)
    if instruction_path is None:
        instruction_path = authority / "instructions.md"
        instruction_path.write_text(
            "Implement T002 persistence in app/src/main.rs only using the bounded tools.\n",
            encoding="utf-8",
        )
    elif not instruction_path.is_file():
        raise FileNotFoundError(instruction_path)
    instructions_ref = ref(instruction_path)
    source_ref = source_digest(source)
    target = {"kind": "local", "path": str(original_path)}
    model = {"allowed": True, "expected": {"provider": "gpt", "model": "gpt-6.1-sol", "effort": "high"},
             "backend_id": BACKEND, "permission_contract": PERMISSION}
    check_plan = plan_ref
    artifact = {
        "key": "persist", "kind": "scenario", "origin_kind": "external/observation",
        "evidence_id": "offline-owned-observation-1", "operation": "offline-test-export",
        "provider": "offline-owned-fixture", "environment": "isolated Windows GNU fixture",
        "authority": "raw-observation", "limitations": ["No production Evidence or real model."],
        "source": ref(external_path), "output": ref(scenario_path),
        "converter_version": "owned-fixture-v1", "parameters": {},
        "field_mapping": {"state": "sha256"}, "losses": [],
    }
    baseline = {"version": 1, "root": str(baseline_root), "bundle_sha256": sha(bundle_path), "artifacts": [artifact]}
    h: dict[str, Any] = {
        "version": 1,
        "authority": authority_refs,
        "lead_decision": str(authority / "selection.json"),
        "selection": selection_ref,
        "original": {
            "target": target, "target_identity": sha(original_path),
            "bundle": ref(bundle_path), "traceability": authority_refs["plan"],
            "scenarios": authority_refs["spec"], "qualifications": authority_refs["acceptance"],
            "environment": authority_refs["case"],
        },
        "baseline": baseline, "check_plan": check_plan,
        "workspace": str(root / "workspace"),
        "application": {"mode": "copy", "root": str(source), "source_sha256": source_ref},
        "owner_output": str(root / "owner-output"),
        "writable_relative": ["."],
        "protected_relative": ["Cargo.toml", "rust-toolchain.toml"],
        "read_references": [], "stack": "Rust (console)",
        "commands": [{"command": "build.cmd", "timeout_secs": 60}],
        "build": {"command_index": 0, "artifacts": ["target/debug/offline-persistence-fixture.exe"]},
        "model": model, "driver": driver_ref, "instructions": instructions_ref,
        "provider_manifest": profile_ref, "credential_env_keys": [],
        "owner_id": "owner-" + uuid.uuid4().hex,
        "budget": {"wall_secs": 180, "max_refinements": 2, "response_max_tokens": 4096,
                   "response_hard_cap": False, "aggregate": "audit-only",
                   "coordination_usage": {"status": "unknown", "reason": "offline owner fixture; no total-cost enforcement claim"}},
        "stop_marker": str(root / "stop"),
        "message": "Implement T002 persistence in app/src/main.rs only; return typed evidence when authority changes.",
    }
    lead_path = authority / "lead.md"
    lead_path.write_text("Controlled fixture lead decision: accept T002 designed source/behavior refs only.\n", encoding="utf-8")
    lead_ref = ref(lead_path)
    decision = {
        "version": 1, "decision": "accepted", "authority": h["authority"],
        "selection": h["selection"], "selected_task_ids": ["T002"],
        "lead_ref": lead_ref, "approved": approved_execution(h),
    }
    decision_ref = write_json(authority / "lead-decision.json", decision)
    h["lead_decision"] = decision_ref
    handoff = root / "handoff.json"
    write_json(handoff, h)
    if mode == "evidence":
        # The server mutates this authority file immediately before its first final response.
        pass
    return handoff, h


class FakeProvider(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    def __init__(self, address: tuple[str, int], root: Path | None = None):
        self.requests: list[dict[str, Any]] = []
        self.root = root
        self.lock = threading.Lock()
        super().__init__(address, FakeHandler)


class FakeHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, _format: str, *_args: Any) -> None:
        return
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        server: FakeProvider = self.server  # type: ignore[assignment]
        with server.lock:
            server.requests.append(payload)
            index = len(server.requests)
        response = response_call(index) if index in (1, 3) else response_final(index)
        if index == 2 and server.root is not None:
            # Mutate an authority input before the first turn can settle. The driver still
            # receives a valid final response; executor handoff revalidation must route typed
            # NeedsEvidence/OriginalPrimary and must not begin refinement.
            scope = server.root / "authority/scope.md"
            scope.write_text("authority changed during owner turn\n", encoding="utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)
        self.wfile.flush()


def sse(events: list[dict[str, Any]]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e, separators=(',', ':'))}\n\n" for e in events).encode()


def completed(response_id: str) -> dict[str, Any]:
    return {"type": "response.completed", "response": {"id": response_id,
        "usage": {"input_tokens": 13, "input_tokens_details": None, "output_tokens": 5,
                   "output_tokens_details": None, "total_tokens": 18}}}


def response_call(index: int) -> bytes:
    content = BAD_SOURCE if index == 1 else GOOD_SOURCE
    return sse([
        {"type": "response.created", "response": {"id": f"owner-call-{index}"}},
        {"type": "response.output_item.done", "item": {
            "type": "function_call", "call_id": f"owner-write-{index}",
            "namespace": "craft_host", "name": "build_file_write",
            "arguments": json.dumps({"path": "app/src/main.rs", "content": content}),
        }},
        completed(f"owner-call-{index}"),
    ])


def response_final(index: int) -> bytes:
    return sse([
        {"type": "response.created", "response": {"id": f"owner-final-{index}"}},
        {"type": "response.output_item.done", "item": {
            "type": "message", "role": "assistant", "id": f"owner-final-message-{index}",
            "content": [{"type": "output_text", "text": "owner fixture final"}],
        }},
        completed(f"owner-final-{index}"),
    ])


def run_process(exe: Path, args: list[str], env: dict[str, str], cwd: Path) -> tuple[int, str, str]:
    p = subprocess.run([str(exe), *args], env=env, cwd=cwd, text=True,
                       capture_output=True, timeout=240)
    return p.returncode, p.stdout, p.stderr


def parse_last_json(text: str) -> dict[str, Any]:
    for line in reversed([line for line in text.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"no JSON output: {text[-2000:]}")


def snapshot_refs(h: dict[str, Any]) -> dict[str, str]:
    refs: dict[str, str] = {}
    def add(label: str, value: Any) -> None:
        if isinstance(value, dict) and "path" in value and "sha256" in value:
            path = Path(value["path"])
            refs[label] = sha(path)
    for name, value in h["authority"].items():
        add(f"authority.{name}", value)
    for name, value in h["original"].items():
        add(f"original.{name}", value)
    add("lead_decision", h["lead_decision"])
    decision_value = json.loads(Path(h["lead_decision"]["path"]).read_text(encoding="utf-8"))
    add("lead_ref", decision_value["lead_ref"])
    add("selection", h["selection"])
    add("check_plan", h["check_plan"])
    add("driver", h["driver"])
    add("instructions", h["instructions"])
    add("provider_manifest", h["provider_manifest"])
    for index, artifact in enumerate(h["baseline"]["artifacts"]):
        add(f"baseline.{index}.source", artifact["source"])
        add(f"baseline.{index}.output", artifact["output"])
    return refs


def json_has_successful_write(value: Any) -> bool:
    text = json.dumps(value, sort_keys=True)
    return (
        "build_file_write" in text
        and "app/src/main.rs" in text
        and "written" in text
        and '"isError": true' not in text
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_cleanup(result: dict[str, Any]) -> None:
    cleanup = result.get("cleanup", {})
    require(cleanup.get("closed") is True, "owner cleanup is not closed")
    require(cleanup.get("worker_joined") is True, "owner worker did not join")
    require(cleanup.get("all_driver_cleanups_closed") is True, "driver cleanup is not closed")
    require(cleanup.get("all_driver_jobs_verified") is True, "driver Job cleanup is not verified")
    require(cleanup.get("owner_resources", {}).get("status") == "observed-empty", "owner resources are not empty")


def assert_refine(result: dict[str, Any], provider: FakeProvider, h: dict[str, Any], stage: Path) -> dict[str, Any]:
    require(result.get("state") == "candidate", f"refine state is {result.get('state')}")
    require(result.get("accepted") is False, "candidate unexpectedly accepted")
    turns = result.get("actual_turns", [])
    require(len(turns) == 2, f"expected two actual turns, got {len(turns)}")
    checks = result.get("checks", [])
    required_external = any(c.get("id") == "external-scenario" and c.get("required") is True for c in json.loads(Path(h["check_plan"]["path"]).read_text(encoding="utf-8")))
    require(required_external, "fixture check plan does not mark external-scenario required")
    failed = [c for c in checks if c.get("check") == "external-scenario" and c.get("passed") is False]
    passed = [c for c in checks if c.get("check") == "external-scenario" and c.get("passed") is True]
    require(failed, "missing required failed external-scenario record")
    require(passed, "missing required passed external-scenario record")
    require(result.get("typed_check_report_valid") is True, "typed check report was not valid")
    require(len(provider.requests) == 4, f"expected four provider requests, got {len(provider.requests)}")
    write_successes = [json_has_successful_write(provider.requests[i]) for i in (1, 3)]
    require(write_successes == [True, True], f"provider followups do not prove two successful MCP writes: {write_successes}")
    app_main = Path(h["workspace"]) / "app/src/main.rs"
    require(app_main.read_text(encoding="utf-8") == GOOD_SOURCE, "final app/src/main.rs is not the refined source")
    tasks = Path(h["authority"]["tasks"]["path"]).read_bytes()
    require(tasks == b"# Tasks\n- [X] T001 Freeze designed console observation\n- [ ] T002 Implement persistence\n", "tasks authority changed")
    require(result.get("return_summary") is None, "refine unexpectedly produced a return summary")
    require(not (Path(h["workspace"]) / ".craft-codex-executor-owner.json").exists(), "owner lease remains after clean refine")
    assert_cleanup(result)
    round_one = list((Path(h["workspace"]) / "checks/round-1").glob("scenario-*"))
    round_two = list((Path(h["workspace"]) / "checks/round-2").glob("scenario-*"))
    require(round_one and round_two, "missing isolated scenario check directories")
    require(all(not (p / "state.txt").exists() or (p / "state.txt").read_text(encoding="utf-8") != "Ada" for p in round_one), "failed check unexpectedly left state Ada")
    require(any((p / "state.txt").is_file() and (p / "state.txt").read_text(encoding="utf-8") == "Ada" for p in round_two), "passed check did not observe state Ada")
    return {"mcp_write_successes": write_successes, "failed_checks": len(failed), "passed_checks": len(passed)}


def assert_evidence(result: dict[str, Any], provider: FakeProvider, h: dict[str, Any]) -> dict[str, Any]:
    require(result.get("state") != "candidate", "evidence mutation produced candidate")
    require(result.get("accepted") is False, "evidence mutation accepted result")
    summary = result.get("return_summary") or {}
    require(summary.get("disposition") == "needs-evidence", f"unexpected evidence disposition: {summary}")
    require(summary.get("return_to") == "original-primary", f"unexpected evidence return target: {summary}")
    require(len(result.get("actual_turns", [])) == 1, "evidence case refined after authority mutation")
    require(len(provider.requests) == 2, f"evidence case expected two provider requests, got {len(provider.requests)}")
    require(not (Path(h["workspace"]) / "checks/round-2").exists(), "evidence case started refinement")
    require((Path(h["workspace"]) / ".craft-codex-executor-owner.json").exists() is False, "evidence lease remains after verified cleanup")
    assert_cleanup(result)
    return {"mcp_write_successes": [json_has_successful_write(provider.requests[1])]}


def run_case(args: argparse.Namespace, mode: str) -> dict[str, Any]:
    stage = Path(args.stage).absolute() / ("owner-evidence" if mode == "evidence" else "owner-refine")
    if stage.exists():
        raise FileExistsError(f"attempt directory already exists; choose a new --stage: {stage}")
    stage.mkdir(parents=True)
    report_path = stage / "owner-fixture-report.json"
    report: dict[str, Any] = {"mode": mode, "status": "failed", "stage": str(stage)}
    provider: FakeProvider | None = None
    try:
        profile_arg = Path(args.profile).absolute()
        driver = Path(args.driver).absolute()
        executor = Path(args.executor).absolute()
        cargo = Path(args.cargo).absolute() if args.cargo else Path(args.rustc).absolute().with_name("cargo.exe")
        cli_arg = Path(args.codex_cli).absolute()
        for path in [profile_arg, driver, executor, cli_arg, cargo]:
            if not path.is_file():
                raise FileNotFoundError(path)
        if args.entry_env_json:
            entry_env = load_entry_env(Path(args.entry_env_json).absolute())
            cli = Path(entry_env["CRAFT_CODEX_CLI"]).absolute()
            profile = Path(entry_env["CRAFT_CODEX_RUNTIME_PROFILE"]).absolute()
            home = Path(entry_env.get("CRAFT_CODEX_HOME", entry_env.get("CODEX_HOME", ""))).absolute()
            bundle = Path(entry_env["CRAFT_BUNDLE_ROOT"]).absolute()
            instruction_path = Path(entry_env["CRAFT_BUILDER_INSTRUCTIONS"]).absolute()
            require(cli == cli_arg, "entry environment CLI differs from --codex-cli")
            require(profile == profile_arg, "entry environment profile differs from --profile")
            # Managed inputs are prepared by the real entry producer under the owned
            # container before this fresh, exclusive per-case output directory exists.
            container = Path(args.stage).resolve()
            require(home.resolve().is_relative_to(container), "entry environment CODEX_HOME must be inside the owned fixture container")
            require(bundle.resolve().is_relative_to(container), "entry environment bundle root must be inside the owned fixture container")
            require(instruction_path.resolve().is_relative_to(container), "entry instructions must be inside the owned fixture container")
            env = dict(os.environ)
            env.update(entry_env)
            environment_scope = "main-entry-environment-json"
        elif args.direct_fixture_env:
            cli, profile = cli_arg, profile_arg
            home, bundle = stage / "codex-home", stage / "bundle"
            home.mkdir()
            bundle.mkdir()
            instruction_path = None
            env = dict(os.environ)
            env.update({
                "CRAFT_CODEX_CLI": str(cli), "CRAFT_CODEX_CLI_SHA256": sha(cli),
                "CRAFT_CODEX_VERSION": VERSION, "CRAFT_CODEX_RUNTIME_PROFILE": str(profile),
                "CRAFT_CODEX_RUNTIME_PROFILE_SHA256": sha(profile), "CODEX_HOME": str(home),
                "CRAFT_BUNDLE_ROOT": str(bundle),
            })
            environment_scope = "explicit-direct-fixture-environment"
        else:
            raise ValueError("provide --entry-env-json, or explicitly use --direct-fixture-env for development")
        for key in list(env):
            if key.startswith("CRAFT_CODEX_") or key in {"CODEX_HOME", "CODEX_API_KEY", "OPENAI_API_KEY"}:
                env.pop(key, None)
        if args.entry_env_json:
            env.update(load_entry_env(Path(args.entry_env_json).absolute()))
        else:
            env.update({
                "CRAFT_CODEX_CLI": str(cli), "CRAFT_CODEX_CLI_SHA256": sha(cli),
                "CRAFT_CODEX_VERSION": VERSION, "CRAFT_CODEX_RUNTIME_PROFILE": str(profile),
                "CRAFT_CODEX_RUNTIME_PROFILE_SHA256": sha(profile), "CODEX_HOME": str(home),
                "CRAFT_BUNDLE_ROOT": str(bundle),
            })
        require(home.is_dir(), f"isolated CODEX_HOME does not exist: {home}")
        require(bundle.is_dir(), f"isolated bundle root does not exist: {bundle}")
        handoff, h = make_handoff(stage, profile, driver, mode, instruction_path, cargo)
        before_refs = snapshot_refs(h)
        provider = FakeProvider(("127.0.0.1", 0), stage if mode == "evidence" else None)
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        home.joinpath("config.toml").write_text("\n".join([
            'model = "gpt-6.1-sol"', 'model_provider = "gpt"', 'model_reasoning_effort = "high"',
            'approval_policy = "never"', 'sandbox_mode = "read-only"', 'web_search = "disabled"',
            '', '[features]', 'goals = false', 'code_mode_host = false',
            'skip_host_skill_discovery = true', 'omit_skill_descriptions = true',
            '', '[skills]', 'include_instructions = false', 'config = []',
            '[skills.bundled]', 'enabled = false', '', '[model_providers.gpt]',
            'name = "Local owner fixture fake provider"',
            f'base_url = "http://127.0.0.1:{provider.server_address[1]}/v1"',
            'wire_api = "responses"', 'request_max_retries = 0', 'stream_max_retries = 0',
            'supports_websockets = false', '',
        ]), encoding="utf-8")
        for key in ["CODEX_API_KEY", "OPENAI_API_KEY", "CRAFT_CODEX_SERVER", "CRAFT_CODEX_SERVER_URL"]:
            env.pop(key, None)
        env["CRAFT_BUILDER_INSTRUCTIONS"] = str(Path(h["instructions"]["path"]))
        rc, out, err = run_process(executor, ["--validate", str(handoff)], env, stage)
        report["validate_raw_stdout_tail"] = out[-4000:]
        report["validate_raw_stderr_head"] = err[:4000]
        report["validate_raw_stderr_tail"] = err[-4000:]
        validate = parse_last_json(out) if out.strip() else {"stderr_tail": err[-2000:]}
        report["validate"] = {"returncode": rc, "json": validate}
        require(rc == 0 and validate.get("state") == "validated" and validate.get("model_calls") == 0, f"validate contract failed: {validate}")
        require(not Path(h["workspace"]).exists(), "validate created workspace")
        if args.validate_only:
            report["status"] = "passed"
            return report
        rc, out, err = run_process(executor, ["--prepare", str(handoff)], env, stage)
        report["prepare_raw_stdout_tail"] = out[-4000:]
        report["prepare_raw_stderr_head"] = err[:4000]
        report["prepare_raw_stderr_tail"] = err[-4000:]
        prepared = parse_last_json(out) if out.strip() else {"stderr_tail": err[-2000:]}
        report["prepare"] = {"returncode": rc, "json": prepared}
        require(rc == 0 and prepared.get("state") == "prepared" and prepared.get("model_calls") == 0, f"prepare contract failed: {prepared}")
        execution = Path(h["owner_output"]) / "execution.json"
        require(execution.is_file(), "prepare did not publish execution.json")
        rc, out, err = run_process(executor, ["--run", str(execution)], env, stage)
        report["run_raw_stdout_tail"] = out[-8000:]
        report["run_raw_stderr_head"] = err[:4000]
        report["run_raw_stderr_tail"] = err[-4000:]
        result = parse_last_json(out) if out.strip() else {"stderr_tail": err[-4000:]}
        report["run"] = {"returncode": rc, "json": result}
        require(rc in (0, 1), f"unexpected run returncode: {rc}")
        report["provider_request_count"] = len(provider.requests)
        report["provider_request_hashes"] = [hashlib.sha256(json.dumps(x, sort_keys=True).encode()).hexdigest() for x in provider.requests]
        report["provider_write_successes"] = [json_has_successful_write(x) for x in provider.requests]
        report["refs_before"] = before_refs
        report["refs_after"] = snapshot_refs(h)
        report["tasks_bytes"] = Path(h["authority"]["tasks"]["path"]).read_bytes().decode()
        report["baseline_ref"] = h["original"]["bundle"]
        report["lease_exists"] = Path(h["workspace"]).joinpath(".craft-codex-executor-owner.json").exists()
        report["environment_scope"] = environment_scope
        if mode == "refine":
            report["assertions"] = assert_refine(result, provider, h, stage)
            require(report["refs_before"] == report["refs_after"], "refine changed an authority/baseline reference")
        else:
            report["assertions"] = assert_evidence(result, provider, h)
            changed = [k for k in before_refs if before_refs[k] != report["refs_after"].get(k)]
            require(changed == ["authority.scope"], f"evidence mutation changed unexpected refs: {changed}")
        report["status"] = "passed"
        return report
    except BaseException as exc:
        report["status"] = "failed"
        report["error"] = safe_error(exc)
        return report
    finally:
        if provider is not None:
            provider.shutdown()
            provider.server_close()
        write_json(report_path, report)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-cli", required=True)
    parser.add_argument("--driver", required=True)
    parser.add_argument("--executor", required=True)
    parser.add_argument("--cargo")
    parser.add_argument("--rustc")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--entry-env-json")
    parser.add_argument("--direct-fixture-env", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--case", choices=["refine", "evidence", "both"], default="both")
    args = parser.parse_args()
    if not args.cargo and not args.rustc:
        parser.error("one of --cargo or --rustc is required")
    if args.entry_env_json and args.direct_fixture_env:
        parser.error("choose --entry-env-json or --direct-fixture-env")
    cases = ["refine", "evidence"] if args.case == "both" else [args.case]
    reports: list[dict[str, Any]] = []
    for case in cases:
        try:
            reports.append(run_case(args, case))
        except BaseException as exc:
            report = {"mode": case, "status": "failed", "error": safe_error(exc), "stage": str(Path(args.stage).absolute() / ("owner-evidence" if case == "evidence" else "owner-refine"))}
            refused = Path(args.stage).absolute() / f"owner-{case}-refused.json"
            write_json(refused, report)
            reports.append(report)
    status = "passed" if all(report.get("status") == "passed" for report in reports) else "failed"
    aggregate = {"status": status, "cases": reports}
    if args.report:
        write_json(Path(args.report).absolute(), aggregate)
    print(json.dumps(aggregate, indent=2))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
