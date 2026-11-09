"""Bounded owned build job. Logs live only inside this executor checkout."""
import os
import json
import shutil
import uuid
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent.parent
mode = sys.argv[1] if len(sys.argv) > 1 else "check"
env = os.environ.copy()
env["PATH"] = os.environ["CRAFT_GNU_BIN"] + os.pathsep + env["PATH"]
env["CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER"] = str(Path(os.environ["CRAFT_GNU_BIN"]) / "gcc.exe")
env["CARGO_BUILD_JOBS"] = "3"
command = ["cargo", "+stable-x86_64-pc-windows-gnu", mode, "--locked", "--offline", "--manifest-path", str(root / "Cargo.toml"), "--target-dir", str(root / "target")]
if mode == "check":
    command += ["--all-targets", "--features", "fixtures"]
if mode == "test":
    command += ["--features", "fixtures", "--", "--test-threads=1", "--nocapture"]
started = time.time()
history = root / "build-history" / (time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
history.mkdir(parents=True)
for name in (f"{mode}.stdout.log", f"{mode}.stderr.log", f"{mode}.result.json"):
    previous = root / name
    if previous.is_file():
        shutil.copy2(previous, history / ("previous-" + name))
with (root / f"{mode}.stdout.log").open("wb") as stdout, (root / f"{mode}.stderr.log").open("wb") as stderr:
    try:
        if mode == "test":
            driver_command = ["cargo", "+stable-x86_64-pc-windows-gnu", "build", "--locked", "--offline", "--manifest-path", str(root.parent / "craft-pi-bridge/Cargo.toml"), "--bin", "pi-rpc-driver", "--target-dir", str(root / "target/bridge-driver")]
            subprocess.run(driver_command, env=env, stdout=stdout, stderr=stderr, timeout=180, check=True)
        proc = subprocess.run(command, env=env, stdout=stdout, stderr=stderr, timeout=1800)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    except subprocess.CalledProcessError as error:
        code = error.returncode
record = {"command": command, "exit_code": code, "seconds": time.time()-started, "history": str(history)}
(root / f"{mode}.result.json").write_text(json.dumps(record), encoding="utf-8")
for name in (f"{mode}.stdout.log", f"{mode}.stderr.log", f"{mode}.result.json"):
    shutil.copy2(root / name, history / name)
sys.exit(code if isinstance(code, int) else 124)
