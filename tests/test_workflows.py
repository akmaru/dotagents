"""
Validate user/workflows/*.js — the saved dynamic-workflow scripts that run the
machine part of each SCC (docs/adr/0019).

Claude Code loads these from ~/.claude/workflows/<name>.js and exposes each as
/<name>. The runtime rules checked here come from the official workflows doc
(code.claude.com/docs/en/workflows, "Edit a saved script") and the bundled
/workflow-authoring reference: meta must be the first statement and a pure
literal, phase titles must match, and Date.now()/Math.random()/new Date()/
import() throw or fail inside a script.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
WORKFLOWS_DIR = ROOT / "user" / "workflows"
AGENTS_DIR = ROOT / "user" / "agents"

# SCC ごとに 1 本（docs/adr/0018 の ① deliberate / ② build / ③ review）
EXPECTED = {"deliberate", "build", "review"}


def _scripts():
    return sorted(WORKFLOWS_DIR.glob("*.js")) if WORKFLOWS_DIR.exists() else []


def test_one_workflow_per_scc():
    assert {p.stem for p in _scripts()} == EXPECTED


@pytest.mark.parametrize("script", _scripts(), ids=lambda p: p.stem)
class TestWorkflowScript:
    def test_meta_is_first_statement(self, script):
        body = script.read_text()
        code = re.sub(r"^\s*(//[^\n]*\n|\s*\n)*", "", body)  # 先頭のコメント・空行だけ許す
        assert code.startswith("export const meta = {"), (
            "meta が最初の文でないと /<name> が autocomplete から落ちる"
        )

    def test_meta_name_matches_file_stem(self, script):
        m = re.search(r"export const meta = \{\s*name:\s*'([^']+)'", script.read_text())
        assert m and m.group(1) == script.stem, "meta.name が /<name> になるのでファイル名と揃える"

    def test_meta_has_description(self, script):
        assert re.search(r"^\s*description:\s*'[^']+'", script.read_text(), re.M)

    def test_phase_titles_match_meta(self, script):
        text = script.read_text()
        meta_block = text.split("export const meta = {", 1)[1].split("\n}", 1)[0]
        declared = set(re.findall(r"title:\s*'([^']+)'", meta_block))
        used = set(re.findall(r"phase\('([^']+)'\)", text))
        used |= set(re.findall(r"phase:\s*'([^']+)'", text))
        assert used == declared, f"meta.phases {declared} と phase() 呼び出し {used} を一致させる"

    def test_no_nondeterministic_calls(self, script):
        text = script.read_text()
        for bad in ("Date.now(", "Math.random(", "new Date()", "import("):
            assert bad not in text, f"{bad} は resume を壊すのでスクリプト内で使えない"

    def test_agent_types_are_defined_roles(self, script):
        used = set(re.findall(r"agentType:\s*'([^']+)'", script.read_text()))
        defined = {p.stem for p in AGENTS_DIR.glob("*.md")}
        assert used <= defined, f"未定義の役割 {used - defined} を agentType に渡している"

    def test_uses_ledger_dir_arg(self, script):
        # 台帳と報告の置き場は main が args.ledgerDir で渡す（docs/adr/0019）
        assert "args.ledgerDir" in script.read_text()
