"""
Validate the herdr assets under user/herdr/.

The fork keybinding depends on the config.toml binding and the script it points
at staying in sync. The Claude Code SessionStart hook that tells herdr which
session id a pane holds is machine-local and must not leak into the repo.
"""

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
HERDR_DIR = ROOT / "user" / "herdr"
SCRIPT = HERDR_DIR / "scripts" / "fork-claude-session.sh"


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
