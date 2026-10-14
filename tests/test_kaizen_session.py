"""
Validate the pieces that put "the user's turn" in front of the user (docs/adr/0029):

- user/bin/herdr-report-state.sh: reports blocked / working to herdr from Claude Code hooks
- user/bin/agent-kaizen-watch.sh: a dedicated session's watcher over its own issue
- user/herdr/scripts/agent-kaizen-session.sh: starts that dedicated session in a herdr pane
- install.sh registers the hooks; the agent-kaizen skill describes the dedicated session

herdr and gh are bash stubs that log their arguments, so nothing here reaches the real tools.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
REPORT = ROOT / "user" / "bin" / "herdr-report-state.sh"
WATCH = ROOT / "user" / "bin" / "agent-kaizen-watch.sh"
SESSION = ROOT / "user" / "herdr" / "scripts" / "agent-kaizen-session.sh"
INSTALL_SH = ROOT / "user" / "install.sh"
SKILL = ROOT / "packages" / "agent-kaizen" / ".apm" / "skills" / "agent-kaizen" / "SKILL.md"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="requires jq")


def _stub(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)
    return path


class TestReportState:
    def _run(self, tmp_path, state, pane="p1"):
        log = tmp_path / "herdr.log"
        herdr = _stub(tmp_path / "herdr", f'echo "$*" >> {log}\n')
        env = {**os.environ, "HERDR_BIN_PATH": str(herdr), "XDG_STATE_HOME": str(tmp_path / "state")}
        env.pop("HERDR_PANE_ID", None)
        if pane:
            env["HERDR_PANE_ID"] = pane
        subprocess.run(["bash", str(REPORT), state], input="{}", env=env, text=True, check=True)
        return log.read_text().splitlines() if log.exists() else []

    def test_blocked_is_reported_for_the_pane(self, tmp_path):
        assert self._run(tmp_path, "blocked") == ["pane report-agent --pane p1 --state blocked"]

    def test_working_is_sent_only_after_blocked(self, tmp_path):
        assert self._run(tmp_path, "working") == []
        self._run(tmp_path, "blocked")
        assert self._run(tmp_path, "working")[-1] == "pane report-agent --pane p1 --state working"
        # the mark is consumed: the next tool completion is silent
        assert len(self._run(tmp_path, "working")) == 2

    def test_does_nothing_outside_herdr(self, tmp_path):
        assert self._run(tmp_path, "blocked", pane="") == []

    def test_ignores_unknown_states_and_survives_a_missing_herdr(self, tmp_path):
        assert self._run(tmp_path, "bogus") == []
        env = {**os.environ, "HERDR_BIN_PATH": "/nonexistent/herdr", "HERDR_PANE_ID": "p1",
               "XDG_STATE_HOME": str(tmp_path / "s2")}
        assert subprocess.run(["bash", str(REPORT), "blocked"], input="{}", env=env, text=True).returncode == 0


def _gh_stub(tmp_path, issue: dict, prs: list) -> Path:
    (tmp_path / "issue.json").write_text(json.dumps(issue))
    (tmp_path / "prs.json").write_text(json.dumps(prs))
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    _stub(bindir / "gh", f'case "$1 $2" in\n  "issue view") cat {tmp_path}/issue.json ;;\n  "pr list") cat {tmp_path}/prs.json ;;\nesac\n')
    return bindir


def _watch(tmp_path, issue, prs, number="55"):
    bindir = _gh_stub(tmp_path, issue, prs)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "AGENT_KAIZEN_ONCE": "1"}
    out = subprocess.run(["bash", str(WATCH), number], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout


def _comment(login, body, id_="c1"):
    return {"id": id_, "url": f"https://example/{id_}", "author": {"login": login}, "body": body}


class TestWatch:
    def test_a_question_from_the_agent_is_the_users_turn(self, tmp_path):
        out = _watch(tmp_path, {"state": "OPEN", "comments": [_comment("claude", "どちらにしますか？")]}, [])
        assert "[agent-kaizen #55]" in out and "どちらにしますか？" in out

    def test_nothing_while_the_agent_is_working(self, tmp_path):
        working = _comment("claude", "**Claude Code is working…** <img src=\"x/5ac382c7-e004-429b-8e35-7feb3e8f9c6f\">")
        assert _watch(tmp_path, {"state": "OPEN", "comments": [working]}, []) == ""

    def test_nothing_after_the_owner_answered(self, tmp_path):
        comments = [_comment("claude", "質問", "c1"), _comment("akmaru", "@claude A", "c2")]
        assert _watch(tmp_path, {"state": "OPEN", "comments": comments}, []) == ""

    def test_an_open_pr_is_the_users_turn(self, tmp_path):
        prs = [{"number": 60, "headRefName": "claude/issue-55-2026", "state": "OPEN", "url": "https://example/pr/60"}]
        out = _watch(tmp_path, {"state": "OPEN", "comments": [_comment("akmaru", "x")]}, prs)
        assert "PR #60" in out

    def test_ignores_prs_of_other_issues(self, tmp_path):
        prs = [{"number": 7, "headRefName": "claude/issue-5-2026", "state": "OPEN", "url": "u"}]
        assert _watch(tmp_path, {"state": "OPEN", "comments": []}, prs) == ""

    def test_reports_a_merge_and_stops(self, tmp_path):
        prs = [{"number": 60, "headRefName": "claude/issue-55-2026", "state": "MERGED", "url": "u"}]
        assert "merge" in _watch(tmp_path, {"state": "CLOSED", "comments": []}, prs)

    def test_rejects_a_non_numeric_issue(self):
        assert subprocess.run(["bash", str(WATCH), "abc"], capture_output=True).returncode == 2


class TestSession:
    def _run(self, tmp_path, issue="55", running=""):
        log = tmp_path / "herdr.log"
        herdr = _stub(
            tmp_path / "herdr",
            f'echo "$*" >> {log}\n'
            'case "$1 $2" in\n'
            '  "pane split") echo \'{"result":{"pane":{"pane_id":"p9"}}}\' ;;\n'
            f'  "agent list") echo \'{{"result":{{"agents":[{running}]}}}}\' ;;\n'
            '  "agent start") echo \'{"type":"agent_started"}\' ;;\n'
            "esac\n",
        )
        env = {**os.environ, "HERDR_BIN_PATH": str(herdr), "HERDR_PANE_ID": "p1"}
        subprocess.run(["bash", str(SESSION), issue], env=env, check=True, capture_output=True, text=True)
        return log.read_text().splitlines()

    def test_starts_one_session_per_issue_without_taking_focus(self, tmp_path):
        calls = self._run(tmp_path)
        assert any(c.startswith("pane split --pane p1") and "--no-focus" in c for c in calls)
        start = next(c for c in calls if c.startswith("agent start kaizen-55 --kind claude --pane p9"))
        assert "Issue #55" in start
        assert not any(c.startswith("agent focus") for c in calls)

    def test_does_not_start_a_second_session_for_the_same_issue(self, tmp_path):
        calls = self._run(tmp_path, running='{"name":"kaizen-55"}')
        assert not any(c.startswith("pane split") for c in calls)


class TestWiring:
    def test_install_registers_the_blocked_and_working_hooks(self):
        body = INSTALL_SH.read_text()
        assert 'add_hook_once "PreToolUse"   "AskUserQuestion"' in body
        assert "herdr-report-state.sh blocked" in body and "herdr-report-state.sh working" in body
        assert 'add_hook_once "Notification"' in body
        assert "agent-kaizen-watch.sh" in body

    def test_skill_describes_the_dedicated_session(self):
        body = SKILL.read_text()
        assert "## 専用セッション" in body
        assert "agent-kaizen-session.sh" in body and "agent-kaizen-watch.sh" in body
        assert "@claude" in body and "確認" in body
