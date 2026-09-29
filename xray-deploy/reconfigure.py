"""Change the REALITY TLS target while preserving user IDs and key material."""

import argparse
import json
from pathlib import Path

import yaml


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("generated", type=Path)
parser.add_argument("target")
parser.add_argument("--debug", action="store_true")
args = parser.parse_args()
config_path = args.generated / "config.json"
config = json.loads(config_path.read_text(encoding="utf-8"))
reality = config["inbounds"][0]["streamSettings"]["realitySettings"]
reality["target"] = f"{args.target}:443"
reality["serverNames"] = [args.target]
reality["show"] = args.debug
config["log"]["loglevel"] = "debug" if args.debug else "warning"
config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
for profile_path in args.generated.glob("friend*-clash.yaml"):
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    profile["proxies"][0]["servername"] = args.target
    profile_path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
print(f"Updated REALITY target to {args.target}; debug={args.debug}")
