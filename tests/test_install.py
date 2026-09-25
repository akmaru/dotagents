"""
Validate that user/install.sh distributes the user-level config correctly.

Runs install.sh against a throwaway HOME (a temp dir) so the real ~/.claude is
never touched and the test is CI-safe. install.sh only does mkdir/ln/rm/jq, no
network, so sandboxing HOME fully exercises it.
"""

import json
import os
import re
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
    ".claude/rules": "rules",
    ".config/herdr/config.toml": "herdr/config.toml",
    ".config/herdr/scripts": "herdr/scripts",
}


def _run_install(home: Path):
    # herdr integration の導入は実バイナリを叩き repo の settings.json を書き換えるため、
    # symlink の検証には不要な副作用として抑止する（正規化処理は tests/test_herdr.py で検証）
    # plugin install は GitHub から clone・ビルドするため、テストは常に抑止する
    env = {
        **os.environ,
        "HOME": str(home),
        "DOTAGENTS_SKIP_HERDR_INTEGRATION": "1",
        "DOTAGENTS_SKIP_HERDR_PLUGINS": "1",
    }
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


def _agent_links():
    """user/agents/*.md → ~/.claude/agents/<name>.md（ファイル単位、docs/adr/0014）"""
    return {
        f".claude/agents/{p.name}": f"agents/{p.name}"
        for p in sorted((USER_DIR / "agents").glob("*.md"))
    }


@pytest.mark.parametrize("link, target", _agent_links().items())
def test_agent_definition_is_linked_per_file(installed, link, target):
    link_path = installed / link
    assert link_path.is_symlink(), f"{link} must be a per-file symlink"
    assert link_path.resolve() == (USER_DIR / target).resolve()
    assert not (installed / ".claude" / "agents").is_symlink(), (
        "ディレクトリごと symlink すると /agents UI の書き込みが repo に入る"
    )


def test_preserves_pre_existing_agent_file(tmp_path):
    """/agents UI や手で書いた同名の実ファイルは消さず退避する。"""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    name = next(iter(_agent_links()))  # ".claude/agents/<x>.md"
    (tmp_path / name).write_text("hand-written\n")

    assert _run_install(tmp_path).returncode == 0
    assert (tmp_path / name).is_symlink()
    moved = tmp_path / ".claude" / "agents.pre-dotagents" / Path(name).name
    assert moved.read_text() == "hand-written\n"


def test_removes_dangling_dotagents_agent_links_only(tmp_path):
    """repo 側で消した役割のリンクは掃除する。他由来のファイル・リンクには触れない。"""
    agents_dir = tmp_path / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "retired.md").symlink_to(USER_DIR / "agents" / "retired.md")  # dotagents 由来・壊れ
    foreign = tmp_path / "foreign.md"
    foreign.write_text("other tool\n")
    (agents_dir / "foreign-link.md").symlink_to(foreign)
    (agents_dir / "foreign-file.md").write_text("mine\n")

    assert _run_install(tmp_path).returncode == 0
    assert not (agents_dir / "retired.md").is_symlink()
    assert (agents_dir / "foreign-link.md").resolve() == foreign
    assert (agents_dir / "foreign-file.md").read_text() == "mine\n"


def test_does_not_create_opencode_config(installed):
    """OpenCode 向けの配布は畳んだ（docs/adr/0021）。~/.config/opencode を作らない。"""
    assert not (installed / ".config" / "opencode").exists()


def test_claude_import_target_resolves(installed):
    """CLAUDE.md imports @~/.claude/AGENTS.md; that path must resolve to a real file."""
    agents = installed / ".claude" / "AGENTS.md"
    assert agents.is_file(), "@~/.claude/AGENTS.md import target must resolve to a file"


def test_settings_is_merged_not_linked(installed):
    """settings.json は symlink せずマージする（docs/adr/0009）。"""
    settings = installed / ".claude" / "settings.json"
    assert not settings.is_symlink(), "マシン固有のキーを書けるよう実ファイルである必要がある"

    merged = json.loads(settings.read_text())
    repo = json.loads((USER_DIR / "settings.json").read_text())
    # hooks だけは install.sh が SessionStart を足すので完全一致にならない。
    # repo が持ち込む SessionEnd 側が生きていることを別に見る。
    assert {k: v for k, v in repo.items() if k != "hooks"}.items() <= merged.items()
    assert merged["hooks"]["SessionEnd"] == repo["hooks"]["SessionEnd"]


def test_settings_merge_keeps_local_keys(tmp_path):
    """herdr の hook など、ローカルにしかないキーは残す。競合したキーは repo が勝つ。"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    local_only = {"SessionStart": [{"matcher": "*", "hooks": []}]}
    (claude_dir / "settings.json").write_text(
        json.dumps({"hooks": local_only, "theme": "machine-local"})
    )

    assert _run_install(tmp_path).returncode == 0

    merged = json.loads((claude_dir / "settings.json").read_text())
    repo = json.loads((USER_DIR / "settings.json").read_text())
    # install.sh が足す context-budget の hook 以外は、ローカルの hooks をそのまま残す
    assert merged["hooks"]["SessionStart"][0] == local_only["SessionStart"][0]
    assert merged["theme"] == repo["theme"]


CONTEXT_HOOK_CMD = "claude-context.py session-start"


def _context_hook_entries(settings: dict):
    return [
        e for e in settings.get("hooks", {}).get("SessionStart", [])
        if any(h.get("command") == CONTEXT_HOOK_CMD for h in e.get("hooks", []))
    ]


def test_context_hook_is_added_once_and_keeps_existing_hooks(tmp_path):
    """SessionStart hook は配列で herdr も書くので、user/settings.json ではなく install.sh が追記する
    （docs/adr/0013）。2 回走らせても 1 つだけ、既存の hook は消さない。"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    herdr_entry = {"matcher": "*", "hooks": [{"type": "command", "command": "bash /x/herdr-agent-state.sh session"}]}
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {"SessionStart": [herdr_entry]}}))

    assert _run_install(tmp_path).returncode == 0
    assert _run_install(tmp_path).returncode == 0

    merged = json.loads((claude_dir / "settings.json").read_text())
    assert merged["hooks"]["SessionStart"][0] == herdr_entry
    entries = _context_hook_entries(merged)
    assert len(entries) == 1
    assert entries[0]["matcher"] == "startup|resume"
    assert (tmp_path / ".local" / "bin" / "claude-context.py").resolve() == (USER_DIR / "bin" / "claude-context.py").resolve()


def test_settings_migrates_from_symlink(tmp_path):
    """旧 symlink 方式からの移行: symlink を実ファイルに置き換える。"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").symlink_to(USER_DIR / "settings.json")

    assert _run_install(tmp_path).returncode == 0

    settings = claude_dir / "settings.json"
    assert not settings.is_symlink()
    merged = json.loads(settings.read_text())
    repo = json.loads((USER_DIR / "settings.json").read_text())
    assert merged["hooks"]["SessionEnd"] == repo["hooks"]["SessionEnd"]
    # install.sh が足す context-budget の SessionStart hook（後述）だけは増える
    merged.pop("hooks", None)
    repo.pop("hooks", None)
    assert merged == repo, "repo の内容を壊さずに実ファイル化する"


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


def test_preserves_pre_existing_herdr_config(tmp_path):
    """herdr が自分で書いた config.toml は消さず退避する。"""
    herdr_dir = tmp_path / ".config" / "herdr"
    herdr_dir.mkdir(parents=True)
    (herdr_dir / "config.toml").write_text("onboarding = false\n")

    assert _run_install(tmp_path).returncode == 0
    assert (herdr_dir / "config.toml").is_symlink()
    assert (herdr_dir / "config.toml.pre-dotagents").read_text() == "onboarding = false\n"


def _stub_herdr(tmp_path):
    """呼び出しを記録するだけの herdr を PATH の先頭に置く。

    herdr は設定ディレクトリを $HOME ではなく OS のユーザーから解決するため、
    偽 HOME では隔離できない（`HOME=/tmp/x herdr plugin config-dir` は実ユーザーの
    ~/.config/herdr を返す）。実バイナリを呼ばせると開発機の実環境に
    プラグインを入れてしまうので、スタブに差し替えて検証する。
    """
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir()
    log = tmp_path / "herdr-calls.log"
    stub = bin_dir / "herdr"
    stub.write_text(f'#!/usr/bin/env bash\necho "$@" >> "{log}"\n')
    stub.chmod(0o755)
    return bin_dir, log


def test_declared_plugins_are_installed_with_their_pinned_ref(tmp_path):
    bin_dir, log = _stub_herdr(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = subprocess.run(
        ["bash", str(INSTALL_SH)],
        env={**os.environ, "HOME": str(home), "PATH": f"{bin_dir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    calls = log.read_text()
    install_sh = INSTALL_SH.read_text()
    declared = re.findall(r'"([\w.-]+/[\w.-]+)@([0-9a-f]{40})"', install_sh)
    assert declared, "install.sh に宣言されたプラグインが要る"
    for repo, ref in declared:
        assert f"plugin install {repo} --ref {ref} --yes" in calls


def test_plugin_install_is_skippable(tmp_path):
    """DOTAGENTS_SKIP_HERDR_PLUGINS=1 で plugin install を打たない。

    テストは常にこの経路を通る。ここが壊れるとスイートがネットワークに出て、
    実行した開発機の実 herdr にプラグインを入れてしまう。
    """
    bin_dir, log = _stub_herdr(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    result = subprocess.run(
        ["bash", str(INSTALL_SH)],
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "DOTAGENTS_SKIP_HERDR_PLUGINS": "1",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "plugin install" not in (log.read_text() if log.exists() else "")


# --- workflows: user/workflows/*.js → ~/.claude/workflows/<name>.js（docs/adr/0020） ---

def _workflow_links():
    return {
        f".claude/workflows/{p.name}": f"workflows/{p.name}"
        for p in sorted((USER_DIR / "workflows").glob("*.js"))
    }


@pytest.mark.parametrize("link, target", _workflow_links().items())
def test_workflow_is_linked_per_file(installed, link, target):
    """保存ワークフローはファイル単位で symlink する。ディレクトリごと張ると /workflows の
    保存ダイアログが repo に書き込む（保存先の symlink 拒否は「対象ファイル自身」だけ）。"""
    link_path = installed / link
    assert link_path.is_symlink(), f"{link} must be a per-file symlink"
    assert link_path.resolve() == (USER_DIR / target).resolve()
    assert not (installed / ".claude" / "workflows").is_symlink()


def test_removes_dangling_dotagents_workflow_links_only(tmp_path):
    wf_dir = tmp_path / ".claude" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "retired.js").symlink_to(USER_DIR / "workflows" / "retired.js")
    (wf_dir / "mine.js").write_text("export const meta = {}\n")
    assert _run_install(tmp_path).returncode == 0
    assert not (wf_dir / "retired.js").is_symlink()
    assert (wf_dir / "mine.js").read_text() == "export const meta = {}\n"


# --- workflow-graph hooks（docs/adr/0020） ---

WORKFLOW_GRAPH_HOOKS = {
    "UserPromptSubmit": "workflow-graph-state.sh",
    "PreToolUse": "workflow-graph-guard.sh",
}


def _entries_with_command(settings: dict, event: str, cmd: str):
    return [
        e for e in settings.get("hooks", {}).get(event, [])
        if any(h.get("command") == cmd for h in e.get("hooks", []))
    ]


def test_workflow_graph_hooks_added_once_and_keep_existing(tmp_path):
    """UserPromptSubmit / PreToolUse は他ツールも書き得る配列なので、deep merge ではなく
    install.sh が無ければ足す（docs/adr/0013 と同じ扱い）。2 回走らせても 1 つずつ。"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-guard.sh"}]}
    (claude_dir / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [foreign]}}))

    assert _run_install(tmp_path).returncode == 0
    assert _run_install(tmp_path).returncode == 0
    merged = json.loads((claude_dir / "settings.json").read_text())

    assert merged["hooks"]["PreToolUse"][0] == foreign
    for event, cmd in WORKFLOW_GRAPH_HOOKS.items():
        entries = _entries_with_command(merged, event, cmd)
        assert len(entries) == 1, f"{event} の {cmd} は 1 つだけ"
        assert (tmp_path / ".local" / "bin" / cmd).resolve() == (USER_DIR / "bin" / cmd).resolve()
    guard = _entries_with_command(merged, "PreToolUse", "workflow-graph-guard.sh")[0]
    assert guard["matcher"] == "Bash|Workflow", "guard は Bash の gh pr create/merge と、Workflow の起動を見る"
