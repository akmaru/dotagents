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
    "compose/deploy.sh",
]

# config.sh is sourced by the other scripts, not invoked: it needs neither the
# executable bit nor its own `set -euo pipefail` (which would leak to the caller).
EXECUTABLE_SCRIPTS = [s for s in SHELL_SCRIPTS if s != "config.sh"]

DEFAULT_URL = "http://localhost:8888/mcp"


def _run_install_client(home: Path, url: str | None = None, api_key: str | None = None):
    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        # keep the real sync-mcp.sh out of the way; the fragment is what we assert on.
        # jq is needed; keep the Homebrew prefixes so the script finds it on macOS.
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        # a real Keychain entry must not leak into the no-key assertions
        "HINDSIGHT_MCP_API_KEY": "",
    }
    if url is not None:
        env["HINDSIGHT_MCP_URL"] = url
    else:
        env.pop("HINDSIGHT_MCP_URL", None)
    if api_key is not None:
        env["HINDSIGHT_MCP_API_KEY"] = api_key
    else:
        # shadow macOS `security` so a real Keychain entry cannot leak into the fragment
        stub_dir = home / "stubbin"
        stub_dir.mkdir(exist_ok=True)
        stub = stub_dir / "security"
        stub.write_text("#!/bin/sh\nexit 1\n")
        stub.chmod(0o755)
        env["PATH"] = f"{stub_dir}:{env['PATH']}"
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

    def test_no_key_means_no_headers(self, installed):
        """Local servers have no auth; a stray Authorization header must not appear."""
        data = json.loads(_fragment_path(installed).read_text())
        assert "headers" not in data["servers"]["hindsight"]

    def test_api_key_becomes_bearer_header(self, tmp_path):
        """ApiKeyTenantExtension reads `Authorization: Bearer <key>` (also on /mcp)."""
        url = "https://hindsight.example.com/mcp"
        assert _run_install_client(tmp_path, url, api_key="s3cret").returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["headers"] == {"Authorization": "Bearer s3cret"}

    def test_fragment_is_private(self, tmp_path):
        """The fragment can hold the API key, so it must be owner-readable only,
        also when it overwrites a world-readable fragment from an older version."""
        frag = _fragment_path(tmp_path)
        frag.parent.mkdir(parents=True)
        frag.write_text("{}")
        frag.chmod(0o644)
        assert _run_install_client(tmp_path, api_key="s3cret").returncode == 0
        assert frag.stat().st_mode & 0o077 == 0

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


class TestServerAssets:
    """The AWS deployment (hindsight/compose + hindsight/aws) is only checked
    structurally: nothing here talks to Docker or AWS."""

    COMPOSE_DIR = HINDSIGHT_DIR / "compose"
    AWS_DIR = HINDSIGHT_DIR / "aws"

    def test_compose_is_valid_yaml_with_expected_services(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load((self.COMPOSE_DIR / "docker-compose.yml").read_text())
        assert set(data["services"]) == {"caddy", "hindsight-api", "postgres"}

    def test_compose_enables_api_key_auth(self):
        """The public endpoint must not be reachable without the tenant API key."""
        text = (self.COMPOSE_DIR / "docker-compose.yml").read_text()
        assert "ApiKeyTenantExtension" in text
        assert "HINDSIGHT_API_TENANT_API_KEY" in text

    def test_compose_matches_config_sh(self):
        """Non-secret settings are duplicated from config.sh; keep them in sync."""
        compose = (self.COMPOSE_DIR / "docker-compose.yml").read_text()
        config = (HINDSIGHT_DIR / "config.sh").read_text()
        for line in config.splitlines():
            if not line.startswith("export HINDSIGHT_API_") or "HOST" in line or "PORT" in line:
                continue
            key, value = line.removeprefix("export ").split("=", 1)
            assert f"{key}: {value}" in compose, f"{key}={value} from config.sh is missing in compose"

    def test_env_is_ignored(self):
        assert ".env" in (self.COMPOSE_DIR / ".gitignore").read_text().split()

    def test_backend_and_tfvars_are_ignored(self):
        """Account-specific values live outside this public repo."""
        ignored = (self.AWS_DIR / ".gitignore").read_text().split()
        assert "backend.hcl" in ignored
        assert "terraform.tfvars" in ignored
        assert (self.AWS_DIR / "backend.hcl.example").is_file()
        assert (self.AWS_DIR / "terraform.tfvars.example").is_file()

    def test_terraform_validate(self):
        import shutil

        if shutil.which("terraform") is None:
            pytest.skip("terraform not installed")
        run = lambda *args: subprocess.run(  # noqa: E731
            ["terraform", *args], cwd=self.AWS_DIR, capture_output=True, text=True
        )
        assert run("fmt", "-check", "-recursive").returncode == 0, "run `terraform fmt`"
        init = run("init", "-backend=false", "-input=false")
        assert init.returncode == 0, init.stderr
        validate = run("validate")
        assert validate.returncode == 0, validate.stderr
