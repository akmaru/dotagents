"""
Validate the agent-experience improvement loop (docs/adr/0027):

- packages/agent-kaizen: the skill that files an issue on akmaru/dotagents with the loop's label
- .github/workflows/agent-kaizen.yml: runs Claude on labeled issues and on @claude comments, only for the repo owner,
  authenticated with the personal subscription's OAuth token
- .github/workflows/agent-kaizen-merge.yml: merges a claude/ PR only when the repo owner approves it and the tests passed
- .github/agent-kaizen/INSTRUCTIONS.md: what the agent does on the runner (stop at a PR, never merge, add a trial guide)

The repo is public, so who can start a run and who can merge are the parts that must not regress.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
LABEL = "agent-kaizen"
SKILL = ROOT / "packages" / "agent-kaizen" / ".apm" / "skills" / "agent-kaizen" / "SKILL.md"
RUN_WORKFLOW = ROOT / ".github" / "workflows" / "agent-kaizen.yml"
MERGE_WORKFLOW = ROOT / ".github" / "workflows" / "agent-kaizen-merge.yml"
INSTRUCTIONS = ROOT / ".github" / "agent-kaizen" / "INSTRUCTIONS.md"


def load_workflow(path):
    data = yaml.safe_load(path.read_text())
    # PyYAML reads the bare `on:` key as boolean True
    data["on"] = data.pop(True, data.get("on"))
    return data


def only_job(workflow):
    jobs = workflow["jobs"]
    assert len(jobs) == 1
    return next(iter(jobs.values()))


def action_step(job):
    steps = [s for s in job["steps"] if str(s.get("uses", "")).startswith("anthropics/claude-code-action@")]
    assert len(steps) == 1, "exactly one claude-code-action step"
    return steps[0]


class TestRunWorkflow:
    @pytest.fixture(scope="class")
    def wf(self):
        return load_workflow(RUN_WORKFLOW)

    def test_triggers_on_labeled_issues_and_comments(self, wf):
        assert wf["on"]["issues"]["types"] == ["labeled"]
        assert wf["on"]["issue_comment"]["types"] == ["created"]

    def test_only_the_repo_owner_can_start_a_run(self, wf):
        cond = only_job(wf)["if"]
        # both the label event and the comment event are gated on the owner
        assert cond.count("github.repository_owner") >= 2, cond
        assert "github.event.sender.login" in cond
        assert "github.event.comment.user.login" in cond

    def test_label_event_requires_the_loop_label(self, wf):
        assert f"github.event.label.name == '{LABEL}'" in only_job(wf)["if"]

    def test_uses_the_subscription_token_not_an_api_key(self, wf):
        w = action_step(only_job(wf))["with"]
        assert w["claude_code_oauth_token"] == "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
        assert "anthropic_api_key" not in w

    def test_label_trigger_matches(self, wf):
        assert action_step(only_job(wf))["with"]["label_trigger"] == LABEL

    def test_points_the_agent_at_the_instructions(self, wf):
        args = action_step(only_job(wf))["with"]["claude_args"]
        assert str(INSTRUCTIONS.relative_to(ROOT)) in args
        assert "--max-turns" in args

    def test_can_write_the_pr_body_outside_the_checkout(self, wf):
        # Issue #49: writing the PR body to /tmp waited for an approval nobody can give on the runner,
        # so the agent stopped before `gh pr create`
        args = action_step(only_job(wf))["with"]["claude_args"]
        assert "--add-dir /tmp" in args

    def test_can_set_the_executable_bit_in_the_working_tree(self, wf):
        # Issue #57: chmod was not allowed, so a new script stayed non-executable in the working tree,
        # the executable-bit test failed, and the agent stopped before `gh pr create` (#54)
        args = action_step(only_job(wf))["with"]["claude_args"]
        assert "Bash(chmod:*)" in args

    def test_has_a_timeout(self, wf):
        assert only_job(wf)["timeout-minutes"] <= 120


class TestMergeWorkflow:
    @pytest.fixture(scope="class")
    def wf(self):
        return load_workflow(MERGE_WORKFLOW)

    def test_triggers_on_submitted_reviews_only(self, wf):
        assert list(wf["on"]) == ["pull_request_review"]
        assert wf["on"]["pull_request_review"]["types"] == ["submitted"]

    def test_merges_only_owner_approvals_of_claude_branches(self, wf):
        cond = only_job(wf)["if"]
        assert "github.event.review.state == 'approved'" in cond
        assert "github.event.review.user.login == github.repository_owner" in cond
        assert "startsWith(github.event.pull_request.head.ref, 'claude/')" in cond

    def test_closes_linked_issues_after_merging(self, wf):
        # PR #51: merged by GITHUB_TOKEN, `Closes #49` did not close the issue
        job = only_job(wf)
        script = "\n".join(s.get("run", "") for s in job["steps"])
        assert "closingIssuesReferences" in script
        assert script.index("gh pr merge") < script.index("gh issue close")
        assert job["permissions"]["issues"] == "write"

    def test_checks_tests_before_merging(self, wf):
        script = "\n".join(s.get("run", "") for s in only_job(wf)["steps"])
        assert "gh pr checks" in script
        assert script.index("gh pr checks") < script.index("gh pr merge")


class TestInstructions:
    @pytest.fixture(scope="class")
    def body(self):
        return INSTRUCTIONS.read_text()

    def test_stops_at_a_pull_request(self, body):
        assert "gh pr create" in body
        assert "merge しない" in body

    def test_does_not_touch_its_own_workflows(self, body):
        assert ".github/" in body

    def test_asks_questions_on_the_issue_when_design_is_needed(self, body):
        assert "gh issue comment" in body

    def test_writes_the_pr_body_to_a_file_under_tmp(self, body):
        assert "gh pr create" in body
        assert re.search(r"--body-file /tmp/\S+", body)

    def test_creating_the_pr_overrides_the_default_manual_pr_link(self, body):
        # Issue #57: claude-code-action's built-in prompt says to leave a manual "Create PR" link,
        # which conflicts with `gh pr create`; on #49 and #54 the agent left only the link
        assert "手動作成用の URL" in body
        assert "優先" in body

    def test_files_a_draft_pr_when_tests_fail_for_environment_reasons(self, body):
        # Issue #57: a test failing only because of the runner's permissions stopped the agent before the PR
        assert "--draft" in body

    def test_reports_why_when_it_cannot_create_a_pr(self, body):
        assert "PR を作れなかったとき" in body

    def test_runs_tests_and_keeps_the_trial_guide_even_for_docs_only_changes(self, body):
        # Issue #49: the agent skipped both because the change was documentation only
        assert "ドキュメントだけの変更でも" in body

    def test_pr_body_has_a_trial_guide_in_an_isolated_home(self, body):
        assert re.search(r"HOME=\S+ \S*user/install\.sh", body)
        assert "Closes #" in body

    def test_trial_home_is_reused_across_prs_and_keeps_its_own_login(self, body):
        # A fresh HOME per PR is logged out, so every trial needed /login (found on PR #51).
        # One fixed trial HOME needs /login once; CLAUDE_CONFIG_DIR keys the Keychain entry to it,
        # so that login does not overwrite the everyday one.
        assert "TRY_HOME=~/.claude-trial-home" in body
        assert re.search(r'HOME="\$TRY_HOME" CLAUDE_CONFIG_DIR="\$TRY_HOME/\.claude" claude', body)


class TestCaptureSkill:
    @pytest.fixture(scope="class")
    def body(self):
        return SKILL.read_text()

    def test_files_on_dotagents_with_the_loop_label(self, body):
        assert "gh issue create" in body
        assert "--repo akmaru/dotagents" in body
        assert f"--label {LABEL}" in body

    def test_confirms_the_draft_before_filing(self, body):
        assert "AskUserQuestion" in body

    def test_warns_that_the_issue_is_public(self, body):
        assert "公開" in body

    def test_is_listed_in_the_marketplace(self):
        manifest = yaml.safe_load((ROOT / "apm.yml").read_text())
        names = [p["name"] for p in manifest["marketplace"]["packages"]]
        assert "agent-kaizen" in names
