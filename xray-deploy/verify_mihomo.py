"""Temporarily start Mihomo on the generated profile and check the exit IP."""

import argparse
import subprocess
import time
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("mihomo", type=Path)
parser.add_argument("profile", type=Path)
args = parser.parse_args()

process = subprocess.Popen(
    [str(args.mihomo), "-f", str(args.profile)],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
try:
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError("Test Mihomo exited before the proxy check")
    result = subprocess.run(
        ["curl.exe", "--noproxy", "", "-x", "http://127.0.0.1:7890", "-4", "-fsS",
         "--connect-timeout", "8", "--max-time", "18", "https://api.ipify.org"],
        capture_output=True,
        text=True,
        timeout=22,
    )
    print(f"Exit code: {result.returncode}")
    print(f"Exit IP: {result.stdout.strip()}")
    print(f"Error: {result.stderr.strip()}")
    if result.returncode:
        raise SystemExit(result.returncode)
finally:
    process.terminate()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=4)
