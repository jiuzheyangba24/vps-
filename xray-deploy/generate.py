#!/usr/bin/env python3
"""Generate a domainless VLESS REALITY server and per-user Mihomo profiles."""

import argparse
import base64
import json
import os
import secrets
import uuid
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519


SERVER = os.environ.get("SERVER_IP", "YOUR_SERVER_IP")
PORT = int(os.environ.get("SERVER_PORT", "443"))
SNI = "www.cloudflare.com"
FRIENDS = range(2, 8)


def raw_url_key(key_bytes):
    return base64.urlsafe_b64encode(key_bytes).rstrip(b"=").decode("ascii")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--server", default=SERVER, help="Server IP or domain")
    args = parser.parse_args()
    server_ip = args.server
    args.output.mkdir(parents=True, exist_ok=False)

    private_key = x25519.X25519PrivateKey.generate()
    server_private = raw_url_key(
        private_key.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )
    server_public = raw_url_key(
        private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    )
    short_id = secrets.token_hex(8)
    clients = {f"friend{number}": str(uuid.uuid4()) for number in FRIENDS}

    server_config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "vless-reality",
                "listen": "0.0.0.0",
                "port": PORT,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {"id": client_id, "flow": "xtls-rprx-vision", "email": name}
                        for name, client_id in clients.items()
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "target": f"{SNI}:443",
                        "xver": 0,
                        "serverNames": [SNI],
                        "privateKey": server_private,
                        "shortIds": [short_id],
                    },
                },
            }
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
    }
    (args.output / "config.json").write_text(
        json.dumps(server_config, indent=2) + "\n", encoding="utf-8"
    )

    for number in FRIENDS:
        name = f"friend{number}"
        node = f"US-VLESS-{number}"
        profile = {
            "mixed-port": 7890,
            "allow-lan": False,
            "mode": "rule",
            "ipv6": False,
            "dns": {
                "enable": True,
                "ipv6": False,
                "nameserver": ["1.1.1.1", "8.8.8.8"],
            },
            "proxies": [
                {
                    "name": node,
                    "type": "vless",
                    "server": server_ip,
                    "port": PORT,
                    "uuid": clients[name],
                    "network": "tcp",
                    "tls": True,
                    "servername": SNI,
                    "client-fingerprint": "chrome",
                    "reality-opts": {
                        "public-key": server_public,
                        "short-id": short_id,
                    },
                    "flow": "xtls-rprx-vision",
                    "udp": True,
                }
            ],
            "proxy-groups": [
                {"name": "PROXY", "type": "select", "proxies": [node]}
            ],
            "rules": ["MATCH,PROXY"],
        }
        (args.output / f"{name}-clash.yaml").write_text(
            yaml.safe_dump(profile, sort_keys=False, allow_unicode=False), encoding="utf-8"
        )
    print(f"Generated server config and {len(clients)} client profiles in {args.output}")


if __name__ == "__main__":
    main()
