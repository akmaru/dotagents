"""
Validate user/bin/claude-main-digest.sh — the整形 script that lets the explainer
role (user/agents/explainer.md) read the main session's transcript
(docs/design/explainer-pane.md「整形スクリプト claude-main-digest.sh の仕様」).

Most tests here go through --file, so no herdr binary and no real pane/session
resolution is involved (docs/adr/0016 の Confirmation どおり). The fixture
tests/fixtures/transcript-sample.jsonl is a short, fully anonymized JSONL that
exercises every selection rule: an array-content turn split by message.id, a
tool_result wrapper, isMeta, isSidechain, a thinking block, and one
deliberately malformed line.

TestHerdrPaneResolution is the exception: it exercises the herdr pane-resolution
path (resolve_main_pane and the agent/session checks that follow it) against a
stub herdr swapped in via HERDR_BIN_PATH, per review-v1.md 直す-3.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "user" / "bin" / "claude-main-digest.sh"
FIXTURE = ROOT / "tests" / "fixtures" / "transcript-sample.jsonl"

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None, reason="claude-main-digest.sh requires jq"
)

# フィクスチャの構成（tests/fixtures/transcript-sample.jsonl 参照）:
#   15 生行、うち 1 行は壊れている（有効 14 行）。
#   選別後の entries は 9 個: 質問1 / 回答1(msg1, text+tool_use) / 回答1の続き(msg2) /
#   質問2 / 回答2(msg3) / 質問3 / 回答3(msg4, thinking 混在) / 質問4 / 回答4(msg5)。
#   ユーザーターンは 4 個（質問1〜4）。


def _run(*args, expect_ok=True):
    result = subprocess.run(
        ["bash", str(SCRIPT), "--file", str(FIXTURE), *args],
        capture_output=True,
        text=True,
    )
    if expect_ok:
        assert result.returncode == 0, result.stderr
    return result


class TestSelectionRules:
    """isSidechain・isMeta・tool_result ラッパー・thinking・壊れた行の除外を確かめる。"""

    def test_keeps_real_turns(self):
        out = _run("--turns", "6").stdout
        assert "質問1" in out
        assert "回答1のテキストです" in out
        assert "質問4" in out
        assert "回答4のテキストです" in out

    def test_drops_sidechain_and_meta_and_system_and_thinking(self):
        out = _run("--turns", "6").stdout
        for secret in (
            "SECRET-META-OUTPUT",
            "SECRET-SIDECHAIN-TEXT",
            "SECRET-SYSTEM-EVENT",
            "SECRET-THINKING-CONTENT",
        ):
            assert secret not in out, f"{secret} は投入してはいけない"

    def test_tool_result_wrapper_hidden_by_default(self):
        out = _run("--turns", "6").stdout
        assert "SECRET-TOOL-RESULT-ONLY-WITH-FLAG" not in out

    def test_tool_result_shown_with_with_results(self):
        out = _run("--turns", "6", "--with-results").stdout
        assert "SECRET-TOOL-RESULT-ONLY-WITH-FLAG" in out

    def test_assistant_blocks_bundled_by_message_id(self):
        """msg1 は text ブロックと tool_use ブロックの 2 行に分かれているが、
        1 つの assistant 応答として束ねられ、tool 行も出る。"""
        out = _run("--turns", "6").stdout
        assert "- tool Bash: ls -la && echo done" in out

    def test_reports_dropped_malformed_line_count(self):
        """壊れた行（1 件）を捨てたことがヘッダから分かる。"""
        out = _run("--turns", "6").stdout
        header = out.splitlines()[0]
        assert "dropped 1" in header


class TestTurnsWindow:
    def test_turns_limits_to_recent_user_turns(self):
        out = _run("--turns", "2").stdout
        assert "質問3" in out and "質問4" in out
        assert "質問1" not in out and "質問2" not in out

    def test_turns_larger_than_available_returns_everything(self):
        out = _run("--turns", "100").stdout
        assert "質問1" in out and "質問4" in out


class TestSince:
    def test_since_known_uuid_returns_only_the_remainder(self):
        # u6 は「質問2」の生行 uuid。以降だけが出て、質問2 自体は出ない。
        out = _run("--since", "u6").stdout
        assert "質問2" not in out
        assert "回答2のテキストです" in out
        assert "質問3" in out and "質問4" in out

    def test_unknown_since_falls_back_to_turns_with_a_warning(self):
        result = _run("--since", "does-not-exist", "--turns", "1")
        assert "見つからない" in result.stderr
        assert "質問4" in result.stdout
        assert "質問3" not in result.stdout

    def test_since_at_last_entry_keeps_cursor_and_reports_zero_new(self):
        """u15 はフィクスチャの最終エントリ（回答4）の uuid。それ以降に新規エントリが無い
        とき、以前は entries の範囲が逆転し (entries 10-9/9)、cursor が選別前の最終
        「有効行」の uuid に落ちて空になっていた（review-v1.md 直す-1）。窓が空でも
        exit 0 のまま、cursor には渡した --since をそのまま返し、次回も同じ位置から
        差分が取れることを確かめる。"""
        result = _run("--since", "u15")
        header = result.stdout.splitlines()[0]
        assert "entries 0 new/9" in header
        assert "10–9" not in header  # 範囲が逆転していない
        lines = result.stdout.splitlines()
        assert lines[-1] == "cursor: u15"


class TestMaxChars:
    def test_drops_oldest_entries_and_notes_truncation(self):
        result = _run("--turns", "6", "--max-chars", "50")
        out = result.stdout
        assert "truncated" in out
        # 古い側から落ちるので、末尾の回答4 は残る
        assert "回答4のテキストです" in out
        assert "質問1" not in out


class TestResolveOnly:
    def test_resolve_only_is_a_single_header_line(self):
        result = _run("--resolve-only")
        lines = [l for l in result.stdout.splitlines() if l.strip()]
        assert len(lines) == 1
        assert lines[0].startswith("# main:")


class TestExitCodes:
    def test_missing_file_exits_4(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--file", "/nonexistent/does-not-exist.jsonl"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 4

    def test_all_garbage_exits_5(self, tmp_path):
        garbage = tmp_path / "garbage.jsonl"
        garbage.write_text("not json\nalso not json\n")
        result = subprocess.run(
            ["bash", str(SCRIPT), "--file", str(garbage)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 5

    def test_empty_file_exits_0_with_zero_entries(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("")
        result = subprocess.run(
            ["bash", str(SCRIPT), "--file", str(empty)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "entries 0/0" in result.stdout


def _stub_herdr(tmp_path, panes):
    """Write a stub herdr that answers `pane get <id>` / `pane list` with
    canned JSON, so resolve_main_pane() and the agent/session checks in
    claude-main-digest.sh can be exercised without a real herdr binary
    (see tests/test_install.py's _stub_herdr for the pattern this follows;
    that one only logs calls, this one also has to answer them).

    panes: list of pane dicts (mirroring herdr's `pane list`/`pane get`
    shape), each with at least "pane_id". Returns the path to the stub
    herdr executable, for HERDR_BIN_PATH.
    """
    bin_dir = tmp_path / "stub-bin"
    bin_dir.mkdir(exist_ok=True)
    data_dir = bin_dir / "data"
    data_dir.mkdir(exist_ok=True)

    (data_dir / "panes.json").write_text(json.dumps({"result": {"panes": panes}}))
    for p in panes:
        (data_dir / f"pane-{p['pane_id']}.json").write_text(
            json.dumps({"result": {"pane": p}})
        )

    stub = bin_dir / "herdr"
    stub.write_text(
        '#!/usr/bin/env bash\n'
        'data_dir="$(cd "$(dirname "$0")" && pwd)/data"\n'
        'if [[ "$1" == "pane" && "$2" == "list" ]]; then\n'
        '  cat "$data_dir/panes.json"\n'
        'elif [[ "$1" == "pane" && "$2" == "get" ]]; then\n'
        '  f="$data_dir/pane-$3.json"\n'
        '  if [[ -f "$f" ]]; then cat "$f"; else echo \'{"result":{}}\'; fi\n'
        'else\n'
        '  echo "stub-herdr: unsupported command: $*" >&2\n'
        '  exit 1\n'
        'fi\n'
    )
    stub.chmod(0o755)
    return stub


def _write_transcript(claude_root, session_id, text):
    proj = claude_root / "projects" / "proj"
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{session_id}.jsonl").write_text(
        json.dumps(
            {
                "type": "user",
                "uuid": "m1",
                "timestamp": "2026-01-01T00:00:00.000Z",
                "message": {"content": text},
            }
        )
        + "\n"
    )


class TestHerdrPaneResolution:
    """--file を使わず herdr 経由でメイン pane を解決する経路（resolve_main_pane と
    その後の agent/session チェック）。resolve 順は docs/design/explainer-pane.md
    「メイン pane の特定（確定事項）」。"""

    def _env(self, stub, tmp_path, self_pane, main_pane_id=None):
        claude_root = tmp_path / "claude-config"
        claude_root.mkdir(exist_ok=True)
        env = {
            **os.environ,
            "HERDR_BIN_PATH": str(stub),
            "HERDR_PANE_ID": self_pane,
            "CLAUDE_CONFIG_DIR": str(claude_root),
        }
        env.pop("HERDR_MAIN_PANE_ID", None)
        if main_pane_id is not None:
            env["HERDR_MAIN_PANE_ID"] = main_pane_id
        return env, claude_root

    def test_main_label_is_preferred_over_env_var(self, tmp_path):
        panes = [
            {"pane_id": "self1", "tab_id": "t1", "label": "explainer", "agent": "claude"},
            {
                "pane_id": "mainpane",
                "tab_id": "t1",
                "label": "main",
                "agent": "claude",
                "agent_status": "idle",
                "agent_session": {"kind": "id", "value": "sess-a"},
                "foreground_cwd": "/work",
            },
            {
                "pane_id": "envpane",
                "tab_id": "t1",
                "label": "",
                "agent": "claude",
                "agent_status": "idle",
                "agent_session": {"kind": "id", "value": "sess-b"},
            },
        ]
        stub = _stub_herdr(tmp_path, panes)
        env, claude_root = self._env(stub, tmp_path, "self1", main_pane_id="envpane")
        _write_transcript(claude_root, "sess-a", "hello main A")
        # sess-b の transcript はわざと作らない: 誤って envpane が選ばれたら
        # transcript が見つからず exit 4 になり、明確に落ちる。

        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "pane mainpane" in result.stdout
        assert "session sess-a" in result.stdout
        assert "hello main A" in result.stdout

    def test_falls_back_to_env_var_when_no_label(self, tmp_path):
        panes = [
            {"pane_id": "self2", "tab_id": "t2", "label": "", "agent": "claude"},
            {
                "pane_id": "cand1",
                "tab_id": "t2",
                "label": "",
                "agent": "claude",
                "agent_status": "idle",
                "agent_session": {"kind": "id", "value": "sess-c1"},
            },
            {
                "pane_id": "cand2",
                "tab_id": "t2",
                "label": "",
                "agent": "claude",
                "agent_status": "idle",
                "agent_session": {"kind": "id", "value": "sess-c2"},
            },
        ]
        stub = _stub_herdr(tmp_path, panes)
        env, claude_root = self._env(stub, tmp_path, "self2", main_pane_id="cand1")
        _write_transcript(claude_root, "sess-c1", "hello main C")
        # sess-c2 の transcript も作らない: env var を無視して自動判定に落ちた場合、
        # 候補 2 つ (cand1, cand2) で exit 2 になり、成功と区別できる。

        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "pane cand1" in result.stdout
        assert "hello main C" in result.stdout

    def test_two_candidates_with_no_label_or_env_exits_2(self, tmp_path):
        panes = [
            {"pane_id": "self3", "tab_id": "t3", "label": "", "agent": "claude"},
            {"pane_id": "c1", "tab_id": "t3", "label": "", "agent": "claude"},
            {"pane_id": "c2", "tab_id": "t3", "label": "", "agent": "claude"},
        ]
        stub = _stub_herdr(tmp_path, panes)
        env, _ = self._env(stub, tmp_path, "self3")

        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 2
        assert "候補" in result.stderr

    def test_non_claude_agent_exits_3(self, tmp_path):
        panes = [
            {"pane_id": "self4", "tab_id": "t4", "label": "", "agent": "claude"},
            {
                "pane_id": "mainpane4",
                "tab_id": "t4",
                "label": "main",
                "agent": "bash",
                "agent_status": "idle",
            },
        ]
        stub = _stub_herdr(tmp_path, panes)
        env, _ = self._env(stub, tmp_path, "self4")

        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 3
        assert "Claude Code が居ない" in result.stderr

    def test_unreported_session_id_exits_3(self, tmp_path):
        """agent_session.kind が "id" でない（herdr integration 導入前などでセッション
        ID が未報告の）とき、exit 3 で「セッション ID 未報告」を出す
        （review-v1.md 任意-1、docs/design/explainer-pane.md の失敗モード表どおり）。"""
        panes = [
            {"pane_id": "self5", "tab_id": "t5", "label": "", "agent": "claude"},
            {
                "pane_id": "mainpane5",
                "tab_id": "t5",
                "label": "main",
                "agent": "claude",
                "agent_status": "idle",
                "agent_session": {"kind": "none"},
            },
        ]
        stub = _stub_herdr(tmp_path, panes)
        env, _ = self._env(stub, tmp_path, "self5")

        result = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 3
        assert "セッション ID 未報告" in result.stderr


class TestScriptConventions:
    def test_shebang(self):
        assert SCRIPT.read_text().splitlines()[0] == "#!/usr/bin/env bash"

    def test_executable(self):
        assert os.access(SCRIPT, os.X_OK)

    def test_strict_mode(self):
        assert "set -euo pipefail" in SCRIPT.read_text()


@pytest.mark.skipif(
    os.environ.get("DOTAGENTS_REAL_TRANSCRIPT") != "1",
    reason="手元の実トランスクリプトが要る。DOTAGENTS_REAL_TRANSCRIPT=1 で有効化",
)
def test_smoke_against_latest_real_transcript():
    """形式ドリフトの早期検知用。~/.claude/projects/ 配下の最新トランスクリプトに対して
    落ちない（0/5 系の異常終了をしない）ことだけを確かめる。内容の中身は検証しない。"""
    claude_root = Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude")))
    projects_dir = claude_root / "projects"
    candidates = sorted(
        projects_dir.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    assert candidates, "実トランスクリプトが見つからない"
    result = subprocess.run(
        ["bash", str(SCRIPT), "--file", str(candidates[0]), "--turns", "3"],
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0,), (
        f"最新トランスクリプトの整形が失敗した (exit={result.returncode}): {result.stderr}"
    )
