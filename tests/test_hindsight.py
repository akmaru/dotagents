"""
Validate the Hindsight setup assets under hindsight/.

install-client.sh only writes a small JSON fragment (no network, no process
launch), so running it against a throwaway HOME/XDG_CONFIG_HOME fully exercises
it. The server side (compose/, aws/) talks to Docker and AWS and is therefore
only checked structurally.
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
    "api-key.sh",
    "install-client.sh",
    "control-plane.sh",
    "compose/deploy.sh",
]

# api-key.sh is sourced by the other scripts, not invoked: it needs neither the
# executable bit nor its own `set -euo pipefail` (which would leak to the caller).
EXECUTABLE_SCRIPTS = [s for s in SHELL_SCRIPTS if s != "api-key.sh"]

# バンクは URL パスで固定する。/mcp だと既定バンクが空の default になる (hindsight/README.md)
DEFAULT_URL = "https://hindsight.akmaru.dev/mcp/personal/"


def _stub(home: Path, name: str, body: str) -> Path:
    stub_dir = home / "stubbin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / name
    stub.write_text(f"#!/bin/sh\n{body}\n")
    stub.chmod(0o755)
    return stub_dir


def _run_install_client(
    home: Path,
    url: str | None = None,
    api_key: str | None = None,
    os_name: str | None = None,
    secret_tool: str = "exit 1",
):
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
    # shadow the OS keystores so a real entry on the dev machine cannot leak in
    stub_dir = _stub(home, "security", "exit 1")
    _stub(home, "secret-tool", secret_tool)
    if os_name is not None:
        _stub(home, "uname", f"echo {os_name}")
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
    result = _run_install_client(tmp_path, api_key="s3cret")
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
        assert server["headers"] == {"Authorization": "Bearer s3cret"}, (
            "ApiKeyTenantExtension reads `Authorization: Bearer <key>` (also on /mcp)"
        )

    def test_url_override(self, tmp_path):
        url = "https://hindsight.example.com/mcp"
        assert _run_install_client(tmp_path, url, api_key="s3cret").returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["url"] == url, (
            "HINDSIGHT_MCP_URL must override the default URL"
        )

    @pytest.mark.parametrize(
        "os_name, expected_hint",
        [
            ("Darwin", "security add-generic-password"),
            ("Linux", "secret-tool store"),
        ],
    )
    def test_no_key_skips_with_os_specific_help(self, tmp_path, os_name, expected_hint):
        """Shipping the authenticated default URL without a key would 401 every client,
        so nothing is written; the help names the keystore for this OS and the file
        fallback, and the exit code stays 0 so install.sh carries on."""
        result = _run_install_client(tmp_path, os_name=os_name)
        assert result.returncode == 0, result.stderr
        assert not _fragment_path(tmp_path).exists()
        assert expected_hint in result.stderr
        assert "hindsight/mcp-api-key" in result.stderr, "file fallback must be offered on every OS"
        assert "/hindsight/tenant_api_key" in result.stderr, "tell the user where the value lives"

    def test_no_key_keeps_existing_fragment(self, tmp_path):
        """A skip must not destroy a fragment written earlier with a key."""
        assert _run_install_client(tmp_path, api_key="s3cret").returncode == 0
        before = _fragment_path(tmp_path).read_text()
        assert _run_install_client(tmp_path).returncode == 0
        assert _fragment_path(tmp_path).read_text() == before

    def test_explicit_url_without_key_means_no_headers(self, tmp_path):
        """An explicit HINDSIGHT_MCP_URL is a dev instance with auth disabled: write it, no header."""
        url = "http://localhost:8888/mcp"
        assert _run_install_client(tmp_path, url).returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["url"] == url
        assert "headers" not in data["servers"]["hindsight"]

    def test_key_from_file_fallback(self, tmp_path):
        """Headless Linux has no keyring; ~/.config/hindsight/mcp-api-key is read on any OS."""
        key_file = tmp_path / ".config" / "hindsight" / "mcp-api-key"
        key_file.parent.mkdir(parents=True)
        key_file.write_text("fr0mfile\n")
        assert _run_install_client(tmp_path, os_name="Linux").returncode == 0
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["headers"] == {"Authorization": "Bearer fr0mfile"}

    def test_key_from_secret_tool_on_linux(self, tmp_path):
        """On Linux the libsecret CLI is consulted before the file fallback."""
        result = _run_install_client(tmp_path, os_name="Linux", secret_tool="echo fr0mkeyring")
        assert result.returncode == 0, result.stderr
        data = json.loads(_fragment_path(tmp_path).read_text())
        assert data["servers"]["hindsight"]["headers"] == {"Authorization": "Bearer fr0mkeyring"}

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
        assert _run_install_client(tmp_path, api_key="s3cret").returncode == 0
        assert _run_install_client(tmp_path, api_key="s3cret").returncode == 0
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


def test_install_sh_runs_the_client_setup():
    """The client is lightweight now that the server lives on AWS, so the top-level
    install.sh distributes it; install-client.sh exits 0 without a key so this
    cannot break the rest of the install."""
    assert '"${ROOT_DIR}/hindsight/install-client.sh"' in (ROOT / "install.sh").read_text()


def test_committed_mcp_json_matches_default_url():
    """hindsight/mcp.json documents the shape install-client.sh generates."""
    data = json.loads((HINDSIGHT_DIR / "mcp.json").read_text())
    assert data["servers"]["hindsight"]["url"] == DEFAULT_URL
    assert data["servers"]["hindsight"]["type"] == "http"
    assert data["servers"]["hindsight"]["headers"]["Authorization"].startswith("Bearer ")


class TestServerAssets:
    """The AWS deployment (hindsight/compose + hindsight/aws) is only checked
    structurally: nothing here talks to Docker or AWS."""

    COMPOSE_DIR = HINDSIGHT_DIR / "compose"
    AWS_DIR = HINDSIGHT_DIR / "aws"

    def test_compose_is_valid_yaml_with_expected_services(self):
        yaml = pytest.importorskip("yaml")
        data = yaml.safe_load((self.COMPOSE_DIR / "docker-compose.yml").read_text())
        assert set(data["services"]) == {"caddy", "hindsight-api", "postgres", "scanner"}

    def test_compose_enables_api_key_auth(self):
        """The public endpoint must not be reachable without the tenant API key."""
        text = (self.COMPOSE_DIR / "docker-compose.yml").read_text()
        assert "ApiKeyTenantExtension" in text
        assert "HINDSIGHT_API_TENANT_API_KEY" in text

    def test_compose_pins_known_traps(self):
        """Each of these guards a documented misbehaviour (README: 既知の罠)."""
        compose = (self.COMPOSE_DIR / "docker-compose.yml").read_text()
        assert "HINDSIGHT_API_LLM_PROVIDER: anthropic" in compose, "unset provider falls back to openai -> 401"
        assert "HINDSIGHT_API_LLM_OUTPUT_LANGUAGE" not in compose, "pinning the output language strips identifier protection (ADR 0019)"
        assert "HINDSIGHT_API_REFLECT_LLM_MODEL: claude-sonnet-5" in compose, "haiku fabricates on reflect"

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
