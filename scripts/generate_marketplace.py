#!/usr/bin/env python3
"""Generate .claude-plugin/marketplace.json from apm.yml marketplace block."""

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
APM_YML = ROOT / "apm.yml"
OUT = ROOT / ".claude-plugin" / "marketplace.json"


def main():
    apm = yaml.safe_load(APM_YML.read_text())
    mp = apm["marketplace"]

    manifest = {
        "name": apm["name"],
        "description": apm.get("description", ""),
        "owner": mp["owner"],
        "plugins": mp["plugins"],
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Generated {OUT}")


if __name__ == "__main__":
    main()
