"""
Validate the Hindsight setup assets under hindsight/.

install-client.sh only writes a small JSON fragment (no network, no process
launch), so running it against a throwaway HOME/XDG_CONFIG_HOME fully exercises
it. install-server.sh runs `pip install` and is therefore never executed here --
it is only checked structurally.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HINDSIGHT_DIR = ROOT / "hindsight"
INSTALL_CLIENT_SH = HINDSIGHT_DIR / "install-client.sh"

SHELL_SCRIPTS = [
    "config.sh",
    "install-server.sh",
    "install-client.sh",
    "bin/hindsight-start.sh",
    "bin/hindsight-stop.sh",
]

# config.sh is sourced by the other scripts, not invoked: it needs neither the
# executable bit nor its own `set -euo pipefail` (which would leak to the caller).
EXECUTABLE_SCRIPTS = [s for s in SHELL_SCRIPTS if s != "config.sh"]

DEFAULT_URL = "http://localhost:8888/mcp"


def _run_install_client(home: Path, url: str | None = None):
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        # keep the real sync-mcp.sh out of the way; the fragment is what we assert on
        "PATH": "/usr/bin:/bin",
    }
    if url is not None:
        env["HINDSIGHT_MCP_URL"] = url
    else:
        env.pop("HINDSIGHT_MCP_URL", None)
    return subprocess.run(
        ["bash", str(INSTALL_CLIENT_SH)],
        env=env,
        capture_output=True,
        text=True,
    )


def _fragment_path(home: Path) -> Path:
    return home / ".config" / "mcp" / "master-mcp.d" / "hindsight.json"


@pytest.fixture()
def installed(tmp_path):
    result = _run_install_client(tmp_path)
    assert result.returncode == 0, f"install-client.sh failed:\n{result.stderr}"
    return tmp_path


class TestInstallClient:
    def test_writes_fragment(self, installed):
        assert _fragment_path(installed).is_file(), (
            "install-client.sh must write hindsight.json into master-mcp.d/"
        )

    def test_fragment_shape(self, installed):
        """sync-mcp.sh reads `.servers` from each master-mcp.d/*.json fragment."""
        data = json.loads(_fragment_path(installed).read_text())
        server = data["servers"]["hindsight"]
        assert server["type"] == "http", "Hindsight is served over streamable HTTP"
        assert server["url"] == DEFAULT_URL

    def test_url_override(self, tmp_path):
        url = "https://hindsight.example.ts.net/mcp"
        assert _run_install_client(tmp_path, url).returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["url"] == url, (
            "HINDSIGHT_MCP_URL must override the default local URL"
        )

    def test_idempotent(self, tmp_path):
        """Running twice yields the same valid fragment (no error, no duplication)."""
        assert _run_install_client(tmp_path).returncode == 0
        assert _run_install_client(tmp_path).returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert list(data["servers"]) == ["hindsight"]


class TestScripts:
    @pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda s: s)
    def test_shebang(self, script):
        first = (HINDSIGHT_DIR / script).read_text().splitlines()[0]
        assert first == "#!/usr/bin/env bash", (
            f"{script} must use the repo's shebang convention"
        )

    @pytest.mark.parametrize("script", EXECUTABLE_SCRIPTS, ids=lambda s: s)
    def test_executable(self, script):
        assert os.access(HINDSIGHT_DIR / script, os.X_OK), f"{script} must be executable"

    @pytest.mark.parametrize("script", EXECUTABLE_SCRIPTS, ids=lambda s: s)
    def test_strict_mode(self, script):
        assert "set -euo pipefail" in (HINDSIGHT_DIR / script).read_text(), (
            f"{script} must run under set -euo pipefail"
        )


def test_committed_mcp_json_matches_default_url():
    """hindsight/mcp.json documents the shape install-client.sh generates."""
    data = json.loads((HINDSIGHT_DIR / "mcp.json").read_text())
    assert data["servers"]["hindsight"]["url"] == DEFAULT_URL
    assert data["servers"]["hindsight"]["type"] == "http"
