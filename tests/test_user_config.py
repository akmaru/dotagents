"""
Validate the personal user-level agent config under user/.

user/ holds native (non-APM) config that install.sh symlinks into ~/.claude and
~/.config/opencode. See docs/adr/0004-0006.
"""

import json
import os
import re
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


# --- agents: user/agents/*.md（docs/adr/0014） ---
#
# 1 ファイルを Claude Code と OpenCode の両方が読む。frontmatter は両ツールで形が衝突しない
# キーだけに絞る（tools: "Read, Grep" のような Claude 形式は OpenCode の設定ロード全体を壊す）。

AGENTS_DIR = USER_DIR / "agents"
AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
# Claude の disallowedTools と OpenCode の permission を同居させる（dual-key）。
# 追加するときは OpenCode の provider options への流出を確認してから増やす。
AGENT_FRONTMATTER_KEYS = {"name", "description", "mode", "disallowedTools", "permission", "initialPrompt"}
# defaultMode: auto ではプロンプトの「書かない」は防壁にならない。ツールごと剥がす
AGENT_REQUIRED_DISALLOWED = {"Edit", "Write", "NotebookEdit", "Agent"}
# ユーザーと対話できる役割は「未決事項」で返す必要が無い
INTERACTIVE_AGENTS = {"explainer"}


def _agent_files():
    return sorted(AGENTS_DIR.glob("*.md")) if AGENTS_DIR.exists() else []


def _agent_frontmatter(path: Path) -> dict:
    parts = path.read_text().split("---", 2)
    assert len(parts) >= 3, f"{path.name} must have YAML frontmatter"
    fm = yaml.safe_load(parts[1])
    assert isinstance(fm, dict), f"{path.name} frontmatter must be a mapping"
    return fm


def _agent_body(path: Path) -> str:
    return path.read_text().split("---", 2)[2]


def test_agents_dir_has_only_markdown():
    """description の無い .md は Claude が黙ってスキップし OpenCode は agent として読む。
    README 等を混ぜると両ツールで見えるものが食い違うので、役割定義以外を置かない。"""
    assert _agent_files(), "user/agents/ に役割定義が 1 つ以上あること"
    extras = [p.name for p in AGENTS_DIR.iterdir() if p.suffix != ".md"]
    assert not extras, f"user/agents/ には .md 以外を置かない: {extras}"


def test_delegation_table_lists_every_agent():
    """役割を足して AGENTS.md の Delegation 表を更新し忘れると、オーケストレータが呼び方を知らない。"""
    agents_md = (USER_DIR / "AGENTS.md").read_text()
    assert "## Delegation" in agents_md
    delegation = agents_md.split("## Delegation", 1)[1]
    for path in _agent_files():
        assert f"`{path.stem}`" in delegation, f"AGENTS.md の Delegation 表に `{path.stem}` が無い"


def test_agents_md_has_no_claude_specific_identifiers():
    """Delegation の文面は OpenCode でも読まれる。Claude 固有のツール名・組み込みエージェント名は
    user/CLAUDE.md の対応表に置く（docs/adr/0005 と同じ分離）。"""
    agents_md = (USER_DIR / "AGENTS.md").read_text()
    for ident in ("AskUserQuestion", "SendMessage", "ListAgents", "EnterPlanMode", "Agent ツール"):
        assert ident not in agents_md, f"AGENTS.md に Claude 固有の識別子 {ident!r} を書かない"


@pytest.mark.parametrize("agent_file", _agent_files(), ids=lambda p: p.stem)
class TestAgentDefinition:
    def test_name_matches_file_stem(self, agent_file):
        # OpenCode は name で ID を上書きするので、ファイル名とずれると二重登録になる
        name = _agent_frontmatter(agent_file).get("name")
        assert name == agent_file.stem, f"name '{name}' はファイル名 '{agent_file.stem}' と一致させる"
        assert AGENT_NAME_PATTERN.match(name)

    def test_description_is_nonempty_string(self, agent_file):
        desc = _agent_frontmatter(agent_file).get("description")
        assert isinstance(desc, str) and desc.strip()

    def test_frontmatter_keys_are_cross_tool_safe(self, agent_file):
        extra = set(_agent_frontmatter(agent_file)) - AGENT_FRONTMATTER_KEYS
        assert not extra, (
            f"{agent_file.name} の {extra} は両ツールで形が衝突する、または未検証のキー。"
            "tools / color / model は OpenCode の設定ロードを壊す（docs/adr/0014）"
        )

    def test_mode_is_an_opencode_mode(self, agent_file):
        assert _agent_frontmatter(agent_file).get("mode") in {"subagent", "primary", "all"}

    def test_disallowed_tools_block_writes_and_redelegation(self, agent_file):
        disallowed = set(_agent_frontmatter(agent_file).get("disallowedTools") or [])
        missing = AGENT_REQUIRED_DISALLOWED - disallowed
        assert not missing, f"{agent_file.name} の disallowedTools に {missing} が要る"

    def test_permission_denies_edit_and_task(self, agent_file):
        permission = _agent_frontmatter(agent_file).get("permission") or {}
        assert permission.get("edit") == "deny", "OpenCode 側の書き込み禁止"
        assert permission.get("task") == "deny", "OpenCode 側の再委譲禁止"

    def test_body_ends_with_open_questions(self, agent_file):
        body = _agent_body(agent_file)
        assert body.strip(), f"{agent_file.name} の本文が空"
        if agent_file.stem in INTERACTIVE_AGENTS:
            return
        # 対話できないサブエージェントが疑問をユーザーへ届ける唯一の経路
        assert "未決事項" in body, f"{agent_file.name} の報告形式に「未決事項」が要る"
