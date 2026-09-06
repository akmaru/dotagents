"""
Validate mcp/sync-mcp.sh and mcp/install.sh.

Both are run against a throwaway HOME/XDG_CONFIG_HOME so the real MCP configs are
never touched. sync-mcp.sh only reads the master config and writes per-tool config
files under $HOME, so sandboxing those two variables fully contains it.

Ported from the shell-based test that used to live in the dotfiles repo.
"""

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
MCP_DIR = ROOT / "mcp"
SYNC_SH = MCP_DIR / "sync-mcp.sh"
INSTALL_SH = MCP_DIR / "install.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="sync-mcp.sh requires jq"
)

# A stdio server (spawns a process) and an HTTP server (reached over a URL).
# The two are enriched differently, which is what most of these tests pin down.
MASTER_CONFIG = {
    "servers": {
        "memory": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
            "env": {"MEMORY_FILE": "${HOME}/.config/mcp/shared-memory.json"},
        },
        "test-server": {"command": "echo", "args": ["test"]},
        "remote": {"type": "http", "url": "http://localhost:8888/mcp"},
    }
}


def _env(home: Path) -> dict:
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_BIN_HOME": str(home / ".local" / "bin"),
    }


def _write_master(home: Path, config: dict) -> None:
    path = home / ".config" / "mcp" / "master-mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config))


def _sync(home: Path, target: str = "claude"):
    return subprocess.run(
        ["bash", str(SYNC_SH), target],
        env=_env(home),
        capture_output=True,
        text=True,
    )


def _vscode_config(home: Path) -> Path:
    if platform.system() == "Darwin":
        return home / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
    return home / ".config" / "Code" / "User" / "mcp.json"


@pytest.fixture()
def synced(tmp_path):
    _write_master(tmp_path, MASTER_CONFIG)
    result = _sync(tmp_path)
    assert result.returncode == 0, f"sync-mcp.sh failed:\n{result.stderr}"
    return json.loads((tmp_path / ".claude.json").read_text())["mcpServers"]


class TestEnrichment:
    def test_command_path_is_resolved(self, synced):
        """Claude Code gets no shell PATH, so bare commands must be made absolute."""
        assert synced["test-server"]["command"].endswith("/echo"), (
            "a bare command must be resolved to an absolute path"
        )

    def test_path_injected_for_stdio(self, synced):
        assert "PATH" in synced["test-server"]["env"], (
            "stdio servers spawn a process and need PATH"
        )

    def test_existing_env_preserved(self, synced):
        assert (
            synced["memory"]["env"]["MEMORY_FILE"]
            == "${HOME}/.config/mcp/shared-memory.json"
        ), "injecting PATH must not drop the server's own env entries"

    def test_no_env_for_http(self, synced):
        """HTTP servers never spawn a process, so PATH would have nothing to act on."""
        assert "env" not in synced["remote"], "HTTP servers must not be given env"

    def test_http_fields_untouched(self, synced):
        assert synced["remote"] == {
            "type": "http",
            "url": "http://localhost:8888/mcp",
        }


class TestIncludes:
    @pytest.fixture()
    def overridden(self, tmp_path):
        _write_master(tmp_path, MASTER_CONFIG)
        include_dir = tmp_path / ".config" / "mcp" / "master-mcp.d"
        include_dir.mkdir(parents=True, exist_ok=True)
        (include_dir / "override.json").write_text(
            json.dumps({"servers": {"test-server": {"command": "ls", "args": ["-la"]}}})
        )
        assert _sync(tmp_path).returncode == 0
        return json.loads((tmp_path / ".claude.json").read_text())["mcpServers"]

    def test_include_overrides_master(self, overridden):
        assert overridden["test-server"]["command"].endswith("/ls")

    def test_override_replaces_entirely(self, overridden):
        """Includes replace a server wholesale rather than shallow-merging it."""
        assert overridden["test-server"]["args"] == ["-la"]

    def test_other_servers_survive(self, overridden):
        assert "memory" in overridden, "an include must not drop unrelated servers"


class TestTargets:
    def test_claude_uses_mcp_servers_key(self, tmp_path):
        _write_master(tmp_path, MASTER_CONFIG)
        assert _sync(tmp_path, "claude").returncode == 0
        assert "mcpServers" in json.loads((tmp_path / ".claude.json").read_text())

    def test_vscode_uses_servers_key(self, tmp_path):
        _write_master(tmp_path, MASTER_CONFIG)
        assert _sync(tmp_path, "vscode").returncode == 0
        assert "servers" in json.loads(_vscode_config(tmp_path).read_text())

    def test_gitlab_uses_mcp_servers_key(self, tmp_path):
        _write_master(tmp_path, MASTER_CONFIG)
        assert _sync(tmp_path, "gitlab").returncode == 0
        config = tmp_path / ".gitlab" / "duo" / "mcp.json"
        assert "mcpServers" in json.loads(config.read_text())

    def test_all_writes_every_target(self, tmp_path):
        _write_master(tmp_path, MASTER_CONFIG)
        assert _sync(tmp_path, "all").returncode == 0
        for path in (
            tmp_path / ".claude.json",
            _vscode_config(tmp_path),
            tmp_path / ".gitlab" / "duo" / "mcp.json",
        ):
            assert path.is_file(), f"{path} must be written by `sync-mcp.sh all`"


class TestInstall:
    def test_links_master_and_cli(self, tmp_path):
        result = subprocess.run(
            ["bash", str(INSTALL_SH)],
            env=_env(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"install.sh failed:\n{result.stderr}"

        master = tmp_path / ".config" / "mcp" / "master-mcp.json"
        cli = tmp_path / ".local" / "bin" / "sync-mcp.sh"
        assert master.resolve() == (MCP_DIR / "master-mcp.json").resolve()
        assert cli.resolve() == SYNC_SH.resolve()
        assert (tmp_path / ".config" / "mcp" / "master-mcp.d").is_dir(), (
            "the include dir must exist so other repos can drop configs into it"
        )
