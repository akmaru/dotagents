"""
Validate user/bin/claude-main-digest.sh — the整形 script that lets the explainer
role (user/agents/explainer.md) read the main session's transcript
(docs/design/explainer-pane.md「整形スクリプト claude-main-digest.sh の仕様」).

All tests here go through --file, so no herdr binary and no real pane/session
resolution is involved (docs/adr/0016 の Confirmation どおり). The fixture
tests/fixtures/transcript-sample.jsonl is a short, fully anonymized JSONL that
exercises every selection rule: an array-content turn split by message.id, a
tool_result wrapper, isMeta, isSidechain, a thinking block, and one
deliberately malformed line.
"""

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
