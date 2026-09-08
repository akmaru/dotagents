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
    ".config/opencode/AGENTS.md": "AGENTS.md",
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
    assert repo.items() <= merged.items()


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
    assert merged["hooks"] == local_only
    assert merged["theme"] == repo["theme"]


def test_settings_migrates_from_symlink(tmp_path):
    """旧 symlink 方式からの移行: symlink を実ファイルに置き換える。"""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "settings.json").symlink_to(USER_DIR / "settings.json")

    assert _run_install(tmp_path).returncode == 0

    settings = claude_dir / "settings.json"
    assert not settings.is_symlink()
    assert json.loads(settings.read_text()) == json.loads(
        (USER_DIR / "settings.json").read_text()
    ), "repo の内容を壊さずに実ファイル化する"


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
