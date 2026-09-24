"""
Validate the two hooks that make the workflow graph's state visible and its
exit conditions enforced (docs/adr/0020):

- user/bin/workflow-graph-state.sh (UserPromptSubmit): injects a one-line
  summary of the active task's ledgers as additionalContext.
- user/bin/workflow-graph-guard.sh (PreToolUse, Bash): denies `gh pr create`
  until verify.json is all pass, and `gh pr merge` until review.json has no
  open items. Outside a task that uses the graph it must stay silent.

Ledgers live at <cwd>/.claude/workflow-graph/<task>/{decisions,verify,review}.json.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
STATE_HOOK = ROOT / "user" / "bin" / "workflow-graph-state.sh"
GUARD_HOOK = ROOT / "user" / "bin" / "workflow-graph-guard.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="hooks require jq")


def _run(hook: Path, payload: dict):
    return subprocess.run(
        ["bash", str(hook)], input=json.dumps(payload), capture_output=True, text=True
    )


def _ledger_dir(tmp_path: Path, task="t1") -> Path:
    d = tmp_path / ".claude" / "workflow-graph" / task
    d.mkdir(parents=True)
    return d


def _decisions(d: Path, open_rows=1):
    (d / "decisions.json").write_text(json.dumps({
        "task": d.name,
        "confirmed": [{"axis": "a", "choice": "x", "reason": "r"}],
        "open": [{"axis": f"q{i}", "question": "?", "options": ["1", "2"]} for i in range(open_rows)],
    }))


def _verify(d: Path, results):
    (d / "verify.json").write_text(json.dumps({
        "status": "pass" if all(r == "pass" for r in results) else "fail",
        "items": [{"name": f"c{i}", "kind": "test", "result": r} for i, r in enumerate(results)],
    }))


def _review(d: Path, statuses):
    (d / "review.json").write_text(json.dumps({
        "items": [{"severity": "直す", "file": "f", "line": 1, "what": "w", "status": s} for s in statuses],
    }))


# --- state hook -------------------------------------------------------------

def test_state_hook_is_silent_without_ledger(tmp_path):
    r = _run(STATE_HOOK, {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "hi"})
    assert r.returncode == 0
    assert r.stdout.strip() == "", "グラフを使っていないタスクでは何も注入しない"


def test_state_hook_reports_counts_per_scc(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d, open_rows=2)
    _verify(d, ["pass", "fail"])
    r = _run(STATE_HOOK, {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "hi"})
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "t1" in ctx
    assert "未確定 2" in ctx
    assert "未pass 1" in ctx
    assert "scc=②" in ctx, "台帳の存在で現在の SCC を推定する（review 無し・verify 有りなら ②）"


def test_state_hook_picks_review_scc_when_review_exists(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d, 0)
    _verify(d, ["pass"])
    _review(d, ["open", "fixed", "deferred"])
    r = _run(STATE_HOOK, {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": "x"})
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "scc=③" in ctx and "未対応 1" in ctx


# --- guard hook -------------------------------------------------------------

def _bash(cmd: str, cwd: Path):
    return {"hook_event_name": "PreToolUse", "cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": cmd}}


def _decision(r):
    if r.stdout.strip() == "":
        return None
    return json.loads(r.stdout)["hookSpecificOutput"].get("permissionDecision")


def test_guard_allows_everything_without_ledger(tmp_path):
    for cmd in ("gh pr create --fill", "gh pr merge 12", "ls"):
        r = _run(GUARD_HOOK, _bash(cmd, tmp_path))
        assert r.returncode == 0 and _decision(r) is None, f"{cmd}: グラフ不使用なら黙る"


def test_guard_ignores_non_bash_and_unrelated_commands(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d)
    r = _run(GUARD_HOOK, {"hook_event_name": "PreToolUse", "cwd": str(tmp_path), "tool_name": "Read", "tool_input": {"file_path": "x"}})
    assert _decision(r) is None
    r = _run(GUARD_HOOK, _bash("ls -la", tmp_path))
    assert _decision(r) is None


def test_guard_denies_pr_create_until_verify_passes(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d)
    r = _run(GUARD_HOOK, _bash("gh pr create --fill", tmp_path))
    assert _decision(r) == "deny", "verify 未実行なら PR を作らせない"
    _verify(d, ["pass", "fail"])
    r = _run(GUARD_HOOK, _bash("gh pr create --fill", tmp_path))
    assert _decision(r) == "deny"
    assert "fail" in json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    _verify(d, ["pass", "pass"])
    r = _run(GUARD_HOOK, _bash("gh pr create --fill", tmp_path))
    assert _decision(r) is None, "全 pass なら通す"


def test_guard_denies_merge_until_review_has_no_open_items(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d)
    _verify(d, ["pass"])
    r = _run(GUARD_HOOK, _bash("gh pr merge 7 --squash", tmp_path))
    assert _decision(r) == "deny", "review 未実行なら merge させない"
    _review(d, ["open", "fixed"])
    r = _run(GUARD_HOOK, _bash("gh pr merge 7 --squash", tmp_path))
    assert _decision(r) == "deny"
    _review(d, ["fixed", "deferred", "rejected"])
    r = _run(GUARD_HOOK, _bash("gh pr merge 7 --squash", tmp_path))
    assert _decision(r) is None, "棚上げ・却下は未対応に数えない"


def test_guard_uses_most_recently_modified_task(tmp_path):
    old = _ledger_dir(tmp_path, "old")
    _decisions(old)
    _verify(old, ["pass"])
    new = _ledger_dir(tmp_path, "new")
    _decisions(new)
    t = time.time()
    os.utime(old, (t - 100, t - 100))
    os.utime(new, (t, t))
    r = _run(GUARD_HOOK, _bash("gh pr create", tmp_path))
    assert _decision(r) == "deny", "複数タスクがあれば最近更新されたものを見る"
