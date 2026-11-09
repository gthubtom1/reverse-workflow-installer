#!/usr/bin/env python3
"""Portable gate for the exact installed Craft entry; no ambient Pi lookup."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
from configuration import load_json
from versions import InstallError
import craft


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
            raise InstallError("Craft entry belongs to another receipt or resource root")
        command = craft.entry_command(receipt)
        pi = receipt["craft"]["pi_runtime"]
        probe = subprocess.run([pi["node"]["path"], pi["entry"]["path"], "--version"], cwd=pi["distribution"]["root"], env=craft.clean_node_env(), capture_output=True, text=True, timeout=30)
        if probe.returncode or probe.stdout.strip() != pi["version"]:
            raise InstallError("Craft explicit standalone Pi version probe failed")
        if not args.execute:
            if args.arguments:
                raise InstallError("Entry arguments require --execute")
            print(json.dumps({"ok": True, "command": command, "runtime": pi, "runtime_qualification": "unverified"}))
            return 0
        arguments = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        env = craft.clean_node_env()
        env.update({"CRAFT_BUNDLE_ROOT": receipt["craft"]["root"], "CRAFT_PI_NODE": pi["node"]["path"],
                    "CRAFT_PI_ENTRY": pi["entry"]["path"], "CRAFT_PI_VERSION": pi["version"],
                    "CRAFT_PI_DISTRIBUTION": pi["distribution"]["root"],
                    "CRAFT_BUILDER_INSTRUCTIONS": str(HERE / "builder-instructions.md")})
        return subprocess.run([*command, *arguments], cwd=receipt["craft"]["root"], env=env).returncode
    except (InstallError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
