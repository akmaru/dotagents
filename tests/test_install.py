"""
Validate that user/install.sh links the user-level config correctly.

Runs install.sh against a throwaway HOME (a temp dir) so the real ~/.claude is
never touched and the test is CI-safe. install.sh only does mkdir/ln/rm, no
network, so sandboxing HOME fully exercises it.
"""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
USER_DIR = ROOT / "user"
INSTALL_SH = USER_DIR / "install.sh"

# (link relative to fake HOME) -> (expected target under user/)
EXPECTED_LINKS = {
    ".claude/AGENTS.md": "AGENTS.md",
    ".claude/CLAUDE.md": "CLAUDE.md",
    ".claude/settings.json": "settings.json",
    ".claude/rules": "rules",
    ".config/opencode/AGENTS.md": "AGENTS.md",
}


def _run_install(home: Path):
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["bash", str(INSTALL_SH)],
        env=env,
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def installed(tmp_path):
    result = _run_install(tmp_path)
    assert result.returncode == 0, f"install.sh failed:\n{result.stderr}"
    return tmp_path


@pytest.mark.parametrize("link, target", EXPECTED_LINKS.items())
def test_link_points_to_user_file(installed, link, target):
    link_path = installed / link
    assert link_path.is_symlink(), f"{link} must be a symlink"
    assert link_path.resolve() == (USER_DIR / target).resolve(), (
        f"{link} must point to user/{target}"
    )


def test_claude_import_target_resolves(installed):
    """CLAUDE.md imports @~/.claude/AGENTS.md; that path must resolve to a real file."""
    agents = installed / ".claude" / "AGENTS.md"
    assert agents.is_file(), "@~/.claude/AGENTS.md import target must resolve to a file"


def test_settings_is_valid_json_through_link(installed):
    import json

    json.loads((installed / ".claude" / "settings.json").read_text())


def test_cpp_rule_reachable_through_rules_link(installed):
    rule = installed / ".claude" / "rules" / "programming_languages" / "c_cpp.md"
    assert rule.is_file(), "path-scoped rule must be reachable through the rules symlink"


def test_idempotent(tmp_path):
    """Running twice yields the same correct links (no error, no nesting)."""
    assert _run_install(tmp_path).returncode == 0
    assert _run_install(tmp_path).returncode == 0
    for link, target in EXPECTED_LINKS.items():
        assert (tmp_path / link).resolve() == (USER_DIR / target).resolve()


def test_replaces_stale_symlink(tmp_path):
    """A pre-existing stale ~/.claude/CLAUDE.md symlink is replaced, not left dangling."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    stale = claude_dir / "CLAUDE.md"
    stale.symlink_to(tmp_path / "nonexistent-old-target")
    # a real rules dir with a file, mimicking the old dotfiles link layout
    (claude_dir / "rules").mkdir()
    (claude_dir / "rules" / "old.md").write_text("stale")

    assert _run_install(tmp_path).returncode == 0
    assert (claude_dir / "CLAUDE.md").resolve() == (USER_DIR / "CLAUDE.md").resolve()
    assert (claude_dir / "rules").is_symlink()
    assert not (claude_dir / "rules" / "old.md").exists(), "stale rules must be removed"
