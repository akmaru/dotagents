"""
End-to-end test of the marketplace consumer UX using the real `apm` CLI.

Exercises the documented flow: `apm marketplace add <repo>` (reads the committed
.claude-plugin/marketplace.json) -> `apm install <pkg>@dotagents` -> skill deployed.
This validates that marketplace.json actually resolves and installs, which no other
test covers.

Skipped when `apm` is not on PATH, so `uv run pytest` still passes without apm. CI
installs apm via microsoft/apm-action, and locally apm is already on PATH.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
GRILL_SKILL = ROOT / "packages" / "grill-me" / ".apm" / "skills" / "grill-me" / "SKILL.md"

pytestmark = pytest.mark.skipif(shutil.which("apm") is None, reason="apm CLI not on PATH")


def _apm(args, home, cwd=None):
    # Isolate all apm state (marketplaces, install cache) under a throwaway HOME
    # so the real ~/.apm is never touched.
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["apm", *args], env=env, cwd=cwd, capture_output=True, text=True
    )


def test_marketplace_add_then_install_deploys_skill(tmp_path):
    home = tmp_path / "home"
    consumer = tmp_path / "consumer"
    home.mkdir()
    consumer.mkdir()

    add = _apm(["marketplace", "add", str(ROOT)], home)
    assert add.returncode == 0, f"marketplace add failed:\n{add.stderr or add.stdout}"

    install = _apm(
        ["install", "grill-me@dotagents", "--target", "claude"], home, cwd=consumer
    )
    assert install.returncode == 0, f"install failed:\n{install.stderr or install.stdout}"

    deployed = consumer / ".claude" / "skills" / "grill-me" / "SKILL.md"
    assert deployed.is_file(), f"skill not deployed:\n{install.stdout}"
    assert deployed.read_text() == GRILL_SKILL.read_text(), (
        "deployed SKILL.md differs from packages/grill-me source"
    )
