"""
Validate the two hooks that make the workflow graph's state visible and its
exit conditions enforced (docs/adr/0020):

- user/bin/workflow-graph-state.sh (UserPromptSubmit): injects a one-line
  summary of the active task's ledgers as additionalContext, and — the first
  time in a session that the prompt names one of the workflow commands — the
  workflow-graph skill body itself, so the rules are present even when the
  user never invoked the skill.
- user/bin/workflow-graph-guard.sh (PreToolUse, Bash|Workflow): denies
  `gh pr create` until verify.json is all pass, `gh pr merge` until review.json
  has no open items, and launching one of our four workflows without
  `args.models` (the machine-checkable trace that the model question was
  asked). Outside a task that uses the graph the Bash part stays silent.

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


def _run(hook: Path, payload: dict, env_extra=None):
    return subprocess.run(
        ["bash", str(hook)], input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, **(env_extra or {})},
    )


SKILL_MD = ROOT / "packages" / "workflow-graph" / ".apm" / "skills" / "workflow-graph" / "SKILL.md"
# skill 本文にしか無い見出し。注入されたかどうかの目印
SKILL_MARKER = "### 起動前にモデルを聞く"


def _prompt(tmp_path: Path, text: str, session="s1"):
    return {"hook_event_name": "UserPromptSubmit", "cwd": str(tmp_path), "prompt": text, "session_id": session}


def _state_env(tmp_path: Path):
    return {"XDG_STATE_HOME": str(tmp_path / "state"), "HOME": str(tmp_path / "home")}


def _ctx(r):
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


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


# --- state hook: skill 本文の注入 ------------------------------------------

@pytest.mark.parametrize("cmd", ["/deliberate", "/build", "/review", "/web-research"])
def test_state_hook_injects_skill_body_when_a_workflow_command_is_typed(tmp_path, cmd):
    """ユーザーが skill を先に叩かなくても、コマンドを打った時点で規約が載る。台帳が無くても出す。"""
    r = _run(STATE_HOOK, _prompt(tmp_path, f"{cmd} ADR 0001 の見直しを回して"), _state_env(tmp_path))
    assert r.returncode == 0, r.stderr
    ctx = _ctx(r)
    assert SKILL_MARKER in ctx
    assert "args.models" in ctx
    assert SKILL_MD.read_text().split("---", 2)[2].strip()[:60] in ctx, "frontmatter を除いた本文をそのまま載せる"


def test_state_hook_injects_skill_body_once_per_session(tmp_path):
    """毎ターン 150 行を積むとコンテキストを食うので、セッションにつき 1 回。別セッションは別。"""
    env = _state_env(tmp_path)
    assert SKILL_MARKER in _ctx(_run(STATE_HOOK, _prompt(tmp_path, "/deliberate x", "s1"), env))
    assert SKILL_MARKER not in _ctx(_run(STATE_HOOK, _prompt(tmp_path, "/deliberate y", "s1"), env))
    assert SKILL_MARKER in _ctx(_run(STATE_HOOK, _prompt(tmp_path, "/build z", "s2"), env))


def test_state_hook_does_not_inject_skill_for_unrelated_prompts(tmp_path):
    r = _run(STATE_HOOK, _prompt(tmp_path, "このテストを直して"), _state_env(tmp_path))
    assert r.stdout.strip() == ""


def test_state_hook_combines_skill_and_ledger_state(tmp_path):
    d = _ledger_dir(tmp_path)
    _decisions(d, open_rows=3)
    ctx = _ctx(_run(STATE_HOOK, _prompt(tmp_path, "/deliberate 続き"), _state_env(tmp_path)))
    assert SKILL_MARKER in ctx and "未確定 3" in ctx


# --- guard hook: Workflow の起動 --------------------------------------------

def _workflow(tool_input: dict, cwd: Path):
    return {"hook_event_name": "PreToolUse", "cwd": str(cwd), "tool_name": "Workflow", "tool_input": tool_input}


@pytest.mark.parametrize("name", ["deliberate", "build", "review", "web-research"])
def test_guard_denies_our_workflow_launched_without_models(tmp_path, name):
    """起動前にモデルを聞いた証拠は args.models（既定なら {}）。無ければ起動させない。"""
    r = _run(GUARD_HOOK, _workflow({"name": name, "args": {"goal": "g", "ledgerDir": "/x"}}, tmp_path))
    assert _decision(r) == "deny"
    assert "models" in json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def test_guard_allows_our_workflow_with_models_even_if_empty(tmp_path):
    r = _run(GUARD_HOOK, _workflow({"name": "deliberate", "args": {"goal": "g", "ledgerDir": "/x", "models": {}}}, tmp_path))
    assert _decision(r) is None


def test_guard_checks_script_path_launches_too(tmp_path):
    """name 解決に失敗して scriptPath で起動する経路（実機で起きた）も同じ規則。"""
    p = str(ROOT / "user" / "workflows" / "build.js")
    assert _decision(_run(GUARD_HOOK, _workflow({"scriptPath": p, "args": {"decision": "d"}}, tmp_path))) == "deny"
    assert _decision(_run(GUARD_HOOK, _workflow({"scriptPath": p, "args": {"decision": "d", "models": {"implement": "opus"}}}, tmp_path))) is None


def test_guard_denies_web_research_with_string_args(tmp_path):
    """文字列 args ではモデルを渡せない。{question, models} の形を要求する。"""
    assert _decision(_run(GUARD_HOOK, _workflow({"name": "web-research", "args": "何か"}, tmp_path))) == "deny"
    assert _decision(_run(GUARD_HOOK, _workflow({"name": "web-research", "args": {"question": "何か", "models": {}}}, tmp_path))) is None


def test_guard_denies_bundled_deep_research_and_points_to_web_research(tmp_path):
    """同梱 /deep-research は model を固定できずセッションのモデルで 100 体前後が回る。"""
    r = _run(GUARD_HOOK, _workflow({"name": "deep-research", "args": "何か"}, tmp_path))
    assert _decision(r) == "deny"
    assert "web-research" in json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def test_guard_ignores_other_workflows(tmp_path):
    assert _decision(_run(GUARD_HOOK, _workflow({"name": "triage-issues", "args": [1, 2]}, tmp_path))) is None


# --- guard hook: Bash --------------------------------------------------------

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
