"""
Validate the personal user-level agent config under user/.

user/ holds native (non-APM) config that install.sh symlinks into ~/.claude and
~/.config/opencode. See docs/adr/0004-0006.
"""

import json
import os
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
USER_DIR = ROOT / "user"


def test_user_dir_exists():
    assert USER_DIR.is_dir(), "user/ directory must exist"


def test_agents_md_exists_and_nonempty():
    agents = USER_DIR / "AGENTS.md"
    assert agents.exists(), "user/AGENTS.md must exist"
    assert agents.read_text().strip(), "user/AGENTS.md must not be empty"


def test_claude_md_imports_agents():
    claude = (USER_DIR / "CLAUDE.md").read_text()
    assert "@~/.claude/AGENTS.md" in claude, (
        "user/CLAUDE.md must import AGENTS.md via @~/.claude/AGENTS.md"
    )


def test_claude_md_keeps_work_import():
    claude = (USER_DIR / "CLAUDE.md").read_text()
    assert "@~/.claude/CLAUDE.work.md" in claude, (
        "Claude-specific work import must live in user/CLAUDE.md, not AGENTS.md"
    )


def test_agents_md_is_cross_agent_clean():
    agents = (USER_DIR / "AGENTS.md").read_text()
    assert "CLAUDE.work.md" not in agents, (
        "AGENTS.md must stay cross-agent clean (no Claude-specific work import)"
    )


def test_settings_json_is_valid():
    json.loads((USER_DIR / "settings.json").read_text())


def test_install_sh_is_executable():
    install = USER_DIR / "install.sh"
    assert install.exists(), "user/install.sh must exist"
    assert os.access(install, os.X_OK), "user/install.sh must be executable"


def test_statusline_script_is_executable():
    """settings.json の statusLine が参照するスクリプト。

    install.sh は symlink するだけなので、実行権が無いと statusLine が何も描画しない。
    """
    script = USER_DIR / "bin" / "claude-statusline.sh"
    assert script.is_file(), "user/bin/claude-statusline.sh must exist"
    assert os.access(script, os.X_OK), "statusline script must be executable"


def test_statusline_command_is_distributed_by_install_sh():
    """settings.json が参照するコマンド名を install.sh が ~/.local/bin に配ること。

    参照だけ更新して配布を忘れると、statusLine が command not found で無言で空になる。
    settings.json は絶対パスを持てない（ADR 0009）ため、PATH 上の名前で解決させる。
    """
    command = json.loads((USER_DIR / "settings.json").read_text())["statusLine"]["command"]
    assert "/" not in command, (
        f"statusLine.command は絶対パスを持てない（マシン固有になる）。名前で指定する: {command}"
    )
    install = (USER_DIR / "install.sh").read_text()
    assert f"${{HOME}}/.local/bin/{command}" in install, (
        f"install.sh が {command} を ~/.local/bin へ配布していない"
    )


@pytest.mark.parametrize(
    "rule_file",
    sorted((USER_DIR / "rules").rglob("*.md")) if (USER_DIR / "rules").exists() else [],
    ids=lambda p: p.name,
)
class TestRuleFrontmatter:
    def test_frontmatter_is_valid_yaml(self, rule_file):
        parts = rule_file.read_text().split("---", 2)
        assert len(parts) >= 3, f"{rule_file.name} must have YAML frontmatter"
        fm = yaml.safe_load(parts[1])
        assert isinstance(fm, dict), f"{rule_file.name} frontmatter must be a mapping"

    def test_paths_is_list_of_globs(self, rule_file):
        fm = yaml.safe_load(rule_file.read_text().split("---", 2)[1])
        paths = fm.get("paths")
        assert isinstance(paths, list) and paths, (
            f"{rule_file.name} must declare a non-empty 'paths' list"
        )
