#!/usr/bin/env python3
"""Check and invoke the exact installed Codex Craft owner; never discover a task."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
from configuration import load_json
from versions import InstallError
import craft_codex as craft


def metadata_run(argv, *, cwd, env=None):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    if result.returncode:
        raise InstallError("Codex Craft metadata operation failed")
    return result.stdout.strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        location = load_json(HERE / "receipt-location.json")
        receipt_path = Path(location["receipt"])
        receipt = load_json(receipt_path)
        if receipt_path != Path(receipt["scope"]["root"]) / ".installer/receipt.json" or HERE != Path(receipt["craft"]["resources"]):
            raise InstallError("Codex Craft entry belongs to another receipt/resource root")
        command = craft.entry_command(receipt)
        inspection = craft.inspect_backend(receipt, metadata_run)
        if not args.execute:
            if args.arguments:
                raise InstallError("Entry arguments require --execute")
            print(json.dumps({"ok": True, "command": command, "owner": inspection,
                              "runtime": receipt["craft"][craft.RUNTIME_KEY],
                              "task_admission": "validate/prepare required",
                              "real_model_and_business_acceptance": "not performed by entry check"}))
            return 0
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        return subprocess.run([*command, *arguments], cwd=receipt["craft"]["root"],
                              env=craft.entry_environment(receipt)).returncode
    except (InstallError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
