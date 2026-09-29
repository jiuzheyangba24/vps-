#!/usr/bin/env python3
"""Create and exercise a temporary local Xray SOCKS client for the rollout."""

import argparse
import json
import subprocess
import time
from pathlib import Path

import yaml


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated", type=Path)
    parser.add_argument("xray", type=Path)
    args = parser.parse_args()

    proxy = yaml.safe_load((args.generated / "friend3-clash.yaml").read_text())["proxies"][0]
    client_config = {
        "log": {"loglevel": "debug"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": 10888,
                "protocol": "socks",
                "settings": {"udp": False},
            }
        ],
        "outbounds": [
            {
                "protocol": "vless",
                "settings": {
                    "vnext": [
                        {
                            "address": proxy["server"],
                            "port": proxy["port"],
                            "users": [
                                {
                                    "id": proxy["uuid"],
                                    "encryption": "none",
                                    "flow": proxy["flow"],
                                }
                            ],
                        }
                    ]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "fingerprint": proxy["client-fingerprint"],
                        "serverName": proxy["servername"],
                        "publicKey": proxy["reality-opts"]["public-key"],
                        "shortId": proxy["reality-opts"]["short-id"],
                    },
                },
            }
        ],
    }
    config_path = args.generated / "test-client.json"
    config_path.write_text(json.dumps(client_config, indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(args.xray), "run", "-test", "-config", str(config_path)], check=True)
    log_path = args.generated / "client-test.log"
    log_file = log_path.open("wb")
    process = subprocess.Popen(
        [str(args.xray), "run", "-config", str(config_path)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        time.sleep(1)
        if process.poll() is not None:
            raise RuntimeError("Local Xray exited early")
        request = subprocess.run(
            [
                "curl.exe", "--noproxy", "", "--socks5-hostname", "127.0.0.1:10888",
                "-4", "-fsS", "--connect-timeout", "8", "--max-time", "18",
                "https://api.ipify.org",
            ],
            capture_output=True,
            text=True,
            timeout=22,
        )
        print(f"Exit code: {request.returncode}")
        print(f"Exit IP: {request.stdout.strip()}")
        print(f"Error: {request.stderr.strip()}")
        if request.returncode:
            raise SystemExit(request.returncode)
    finally:
        process.terminate()
        try:
            process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=4)
        log_file.close()
        print("Client log:")
        print(log_path.read_text(encoding="utf-8", errors="replace")[-5000:])


if __name__ == "__main__":
    main()
