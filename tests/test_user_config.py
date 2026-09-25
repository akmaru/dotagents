"""
Validate the personal user-level agent config under user/.

user/ holds native (non-APM) config that install.sh symlinks into ~/.claude.
See docs/adr/0004-0006.
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
# Claude Code は未知の frontmatter キーを無言で無視する。defaultMode: auto 下の防壁は
# disallowedTools なので、その欠落だけを検査で止める（docs/adr/0021）。

AGENTS_DIR = USER_DIR / "agents"
AGENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")
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
    """README 等を混ぜると Claude が意図しないファイルを役割として読み込むので、
    役割定義以外を置かない。"""
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
    """AGENTS.md はツール非依存の共通指示（agents.md 形式）。Claude 固有のツール名・組み込み
    エージェント名は user/CLAUDE.md の対応表に置く（docs/adr/0005、docs/adr/0021）。"""
    agents_md = (USER_DIR / "AGENTS.md").read_text()
    for ident in ("AskUserQuestion", "SendMessage", "ListAgents", "EnterPlanMode", "Agent ツール"):
        assert ident not in agents_md, f"AGENTS.md に Claude 固有の識別子 {ident!r} を書かない"


@pytest.mark.parametrize("agent_file", _agent_files(), ids=lambda p: p.stem)
class TestAgentDefinition:
    def test_name_matches_file_stem(self, agent_file):
        # name が subagent_type として使われるので、ファイル名とずれると呼び出しと定義が食い違う
        name = _agent_frontmatter(agent_file).get("name")
        assert name == agent_file.stem, f"name '{name}' はファイル名 '{agent_file.stem}' と一致させる"
        assert AGENT_NAME_PATTERN.match(name)

    def test_description_is_nonempty_string(self, agent_file):
        desc = _agent_frontmatter(agent_file).get("description")
        assert isinstance(desc, str) and desc.strip()

    def test_disallowed_tools_block_writes_and_redelegation(self, agent_file):
        disallowed = set(_agent_frontmatter(agent_file).get("disallowedTools") or [])
        missing = AGENT_REQUIRED_DISALLOWED - disallowed
        assert not missing, f"{agent_file.name} の disallowedTools に {missing} が要る"

    def test_permission_mode_is_not_set(self, agent_file):
        """defaultMode: auto 下では無視されセッション間で権限クラスが割れる（docs/adr/0014）。"""
        assert "permissionMode" not in _agent_frontmatter(agent_file), (
            f"{agent_file.name} に permissionMode を書かない"
        )

    def test_model_when_set_is_a_known_value(self, agent_file):
        """役割の既定モデルは役割ファイルの model: で決める（docs/adr/0021 で可能になった）。
        値は sub-agents docs の alias（opus / sonnet / haiku / fable）、inherit、またはフル ID。
        タイポは Claude が無言で無視して session のモデルに落ちるので、ここで止める。"""
        model = _agent_frontmatter(agent_file).get("model")
        if model is None:
            return  # 未指定 = セッション継承
        assert model in {"opus", "sonnet", "haiku", "fable", "inherit"} or model.startswith("claude-"), (
            f"{agent_file.name} の model '{model}' は alias / inherit / フル ID のどれでもない"
        )

    def test_body_ends_with_open_questions(self, agent_file):
        body = _agent_body(agent_file)
        assert body.strip(), f"{agent_file.name} の本文が空"
        if agent_file.stem in INTERACTIVE_AGENTS:
            return
        # 対話できないサブエージェントが疑問をユーザーへ届ける唯一の経路
        assert "未決事項" in body, f"{agent_file.name} の報告形式に「未決事項」が要る"
