"""
Validate user/bin/hindsight-retain-hook.sh — the SessionEnd hook that feeds
Hindsight (docs/adr/0017).

The hook is driven through HINDSIGHT_RETAIN_DRY_RUN so the tests never reach the
network: the payload it would POST goes to stdout instead. Everything else
(transcript parsing, the harness-tag filter, the size floor, the no-key path)
runs for real.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
HOOK = ROOT / "user" / "bin" / "hindsight-retain-hook.sh"
SETTINGS = ROOT / "user" / "settings.json"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="hindsight-retain-hook.sh requires jq"
)

HOOK_COMMAND = "hindsight-retain-hook.sh"


def _line(**payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _transcript(tmp_path: Path, *lines: str) -> Path:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _run(transcript: Path, tmp_path: Path, *, dry_run=True, env_extra=None):
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        **(env_extra or {}),
    }
    if dry_run:
        env["HINDSIGHT_RETAIN_DRY_RUN"] = "1"
    stdin = _line(
        transcript_path=str(transcript),
        session_id="session-abc",
        cwd="/home/u/ghq/github.com/acme/widget",
    )
    return subprocess.run(
        ["bash", str(HOOK)], input=stdin, env=env, capture_output=True, text=True
    )


def _assistant(*blocks):
    return _line(type="assistant", message={"content": list(blocks)})


def _user_text(text):
    return _line(type="user", message={"content": text})


# 閾値（500 B）を越えるだけの分量を作るためのダミー本文
LONG = "この決定の理由をここに長めに書いておく。" * 20


class TestFiltering:
    """会話の地の文だけを残し、機械同士のやりとりは落とす。"""

    def test_keeps_conversation_and_drops_machine_blocks(self, tmp_path):
        transcript = _transcript(
            tmp_path,
            _user_text("人間が打った質問。" + LONG),
            _assistant(
                {"type": "thinking", "thinking": "SECRET-THINKING"},
                {"type": "text", "text": "アシスタントの回答。"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "SECRET-TOOL-USE"}},
            ),
            _line(
                type="user",
                message={"content": [{"type": "tool_result", "content": "SECRET-TOOL-RESULT"}]},
            ),
            _line(type="attachment", attachment={"type": "environment", "text": "SECRET-ATTACHMENT"}),
            _line(type="system", content="SECRET-SYSTEM"),
            _line(type="file-history-snapshot", snapshot={"x": "SECRET-SNAPSHOT"}),
        )

        result = _run(transcript, tmp_path)
        assert result.returncode == 0, result.stderr
        content = json.loads(result.stdout)["items"][0]["content"]

        assert "人間が打った質問。" in content
        assert "アシスタントの回答。" in content
        for dropped in (
            "SECRET-THINKING",
            "SECRET-TOOL-USE",
            "SECRET-TOOL-RESULT",
            "SECRET-ATTACHMENT",
            "SECRET-SYSTEM",
            "SECRET-SNAPSHOT",
        ):
            assert dropped not in content, f"{dropped} は投入してはいけない"

    def test_strips_harness_command_output(self, tmp_path):
        """`!` で実行したコマンドの出力は文字列の user メッセージに紛れ込む。
        これはツール出力の生ログそのもので、秘密が載りうるので落とす。"""
        transcript = _transcript(
            tmp_path,
            _user_text(
                "鍵を出してみる。" + LONG
                + "<bash-input>aws ssm get-parameter --with-decryption</bash-input>"
                + "<bash-stdout>SECRET-KEY-VALUE\nsecond line</bash-stdout>"
                + "<local-command-caveat>Caveat: ...</local-command-caveat>"
                + "<local-command-stdout>SECRET-LOCAL-OUT</local-command-stdout>"
                + "<command-name>/context</command-name>"
            ),
        )

        result = _run(transcript, tmp_path)
        assert result.returncode == 0, result.stderr
        content = json.loads(result.stdout)["items"][0]["content"]

        assert "SECRET-KEY-VALUE" not in content
        assert "SECRET-LOCAL-OUT" not in content
        assert "Caveat:" not in content
        assert "/context" not in content
        # 打ったコマンド自体は短く文脈として役立つので残す
        assert "aws ssm get-parameter" in content


class TestPayload:
    def test_shape(self, tmp_path):
        transcript = _transcript(tmp_path, _user_text(LONG))
        result = _run(transcript, tmp_path)
        assert result.returncode == 0, result.stderr

        payload = json.loads(result.stdout)
        assert payload["async"] is True
        item = payload["items"][0]
        assert item["tags"] == ["project:widget", "source:session-hook"]
        assert "widget" in item["context"]
        # SessionEnd は 1 セッションで複数回発火しうる。document_id を session_id に
        # 固定することで、update_mode の既定 replace が再発火を冪等にする。
        assert item["document_id"] == "session-abc"
        assert item["timestamp"].endswith("Z")


class TestSkips:
    """セッション終了を妨げないこと。どの skip も exit 0。"""

    def test_short_session_is_skipped(self, tmp_path):
        transcript = _transcript(tmp_path, _user_text("ありがとう"))
        result = _run(transcript, tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == "", "閾値未満では何も投げない"

    def test_missing_transcript_is_skipped(self, tmp_path):
        result = _run(tmp_path / "does-not-exist.jsonl", tmp_path)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_no_api_key_exits_zero(self, tmp_path):
        """dry-run を外すと鍵を引きに行く。無ければ POST せず 0 で抜ける。"""
        transcript = _transcript(tmp_path, _user_text(LONG))
        result = _run(
            transcript,
            tmp_path,
            dry_run=False,
            # キーストアを見に行く前に環境変数で空を確定させ、CI でも実機でも同じ道を通す
            env_extra={
                "HINDSIGHT_MCP_API_KEY": "",
                "XDG_CONFIG_HOME": str(tmp_path / "config"),
                "PATH": "/usr/bin:/bin",  # security / secret-tool を引かせない
            },
        )
        assert result.returncode == 0, result.stderr

    def test_skip_reason_is_logged(self, tmp_path):
        transcript = _transcript(tmp_path, _user_text("短い"))
        _run(transcript, tmp_path)
        log = tmp_path / "state" / "hindsight-retain" / "log"
        assert log.is_file(), "skip の理由はログに残す"
        assert "skip" in log.read_text()


class TestScriptConventions:
    def test_shebang(self):
        assert HOOK.read_text().splitlines()[0] == "#!/usr/bin/env bash"

    def test_executable(self):
        assert os.access(HOOK, os.X_OK)

    def test_strict_mode(self):
        assert "set -euo pipefail" in HOOK.read_text()


class TestRegistration:
    def test_session_end_hook_is_in_settings_json(self):
        """SessionStart と違い herdr は SessionEnd を書かないので、install.sh の
        deep merge に任せて user/settings.json に直接持たせられる。
        逆向きの取り決め（SessionStart は settings.json に置かない）は
        tests/test_context_budget.py で検査している。"""
        settings = json.loads(SETTINGS.read_text())
        entries = settings["hooks"]["SessionEnd"]
        commands = [h["command"] for e in entries for h in e["hooks"]]
        assert HOOK_COMMAND in commands

    def test_install_sh_links_the_hook(self):
        assert HOOK_COMMAND in (ROOT / "user" / "install.sh").read_text()
