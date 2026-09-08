"""
Validate the herdr assets under user/herdr/.

The fork keybinding depends on the config.toml binding and the script it points
at staying in sync. The Claude Code SessionStart hook that tells herdr which
session id a pane holds is machine-local and must not leak into the repo.
Plugins are distributed by declaring them in install.sh (docs/adr/0010), so the
declarations and the keybindings that invoke them must stay in sync too.
"""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
HERDR_DIR = ROOT / "user" / "herdr"
SCRIPT = HERDR_DIR / "scripts" / "fork-claude-session.sh"
INSTALL_SH = ROOT / "user" / "install.sh"


def _commands():
    config = tomllib.loads((HERDR_DIR / "config.toml").read_text())
    return config["keys"]["command"]


def _declared_plugins():
    """`owner/repo@ref` entries from the HERDR_PLUGINS array in install.sh."""
    body = re.search(
        r"^HERDR_PLUGINS=\((.*?)^\)", INSTALL_SH.read_text(), re.S | re.M
    )
    assert body, "install.sh に HERDR_PLUGINS 配列が要る"
    return re.findall(r'"([^"]+)"', body.group(1))


def test_keybinding_points_at_an_executable_script():
    config = tomllib.loads((HERDR_DIR / "config.toml").read_text())
    commands = config["keys"]["command"]
    fork = next(c for c in commands if "fork-claude-session" in c["command"])

    assert fork["type"] == "shell", "フォーカスを奪わないよう shell 実行にする"
    assert fork["command"] == "$HOME/.config/herdr/scripts/fork-claude-session.sh"
    assert SCRIPT.is_file()
    assert SCRIPT.stat().st_mode & 0o111, "keybinding から直接起動するため実行権が要る"


def test_settings_json_carries_no_machine_specific_hook():
    """herdr の SessionStart hook は絶対パスを含むため repo に入れない（docs/adr/0009）。

    各マシンの `herdr integration install claude` がローカルの settings.json に書き、
    install.sh のマージがそれを保持する。
    """
    settings = json.loads((ROOT / "user" / "settings.json").read_text())
    commands = [
        hook.get("command", "")
        for group in settings.get("hooks", {}).get("SessionStart", [])
        for hook in group.get("hooks", [])
    ]
    assert not any("herdr-agent-state.sh" in c for c in commands)


def test_plugins_are_pinned_to_a_full_commit():
    """他マシンで同じコミットが入るよう ref を固定する（docs/adr/0010）。

    ブランチ名やタグでは解決先が動く。auto-title の v0.4.0 タグは既に
    デフォルトブランチ HEAD より古く、同じ version を名乗る別コミットが存在する。
    """
    plugins = _declared_plugins()
    assert plugins, "配布するプラグインが 1 つ以上あること"
    for entry in plugins:
        repo, _, ref = entry.partition("@")
        assert re.fullmatch(r"[\w.-]+/[\w.-]+", repo), f"{entry} は owner/repo 形式"
        assert re.fullmatch(r"[0-9a-f]{40}", ref), (
            f"{entry} の ref は 40 桁のコミット SHA である必要がある"
        )


def test_plugin_action_bindings_have_a_declared_plugin():
    """キーバインドだけ配って本体が入っていない状態を防ぐ。"""
    # plugin_id の owner は herdr が小文字化するため（ChmaraX → chmarax）比較も小文字で行う
    repos = [entry.partition("@")[0].lower() for entry in _declared_plugins()]
    for command in _commands():
        if command.get("type") != "plugin_action":
            continue
        # command は "<plugin_id>.<action_id>"、plugin_id は "<owner>.<name>"
        owner, name, _ = command["command"].split(".", 2)
        assert any(owner in repo and name in repo for repo in repos), (
            f"{command['command']} に対応する plugin が install.sh に宣言されていない"
        )


def test_external_binaries_are_reachable_without_a_login_shell():
    """herdr サーバはデーモン化で PATH が /usr/bin:/bin:/usr/sbin:/sbin まで削られ、
    カスタムコマンドは login shell を経由しない。PATH を補わないと exit 127 で
    popup が即閉じし、キーが効かないようにしか見えない。
    """
    for command in _commands():
        if command.get("type") not in ("popup", "pane"):
            continue
        body = command["command"]
        assert body.startswith("/") or "PATH=" in body, (
            f"{body} は絶対パスか PATH の明示が要る"
        )
