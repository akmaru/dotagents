"""
Validate user/workflows/*.js — the saved dynamic-workflow scripts that run the
machine part of each SCC (docs/adr/0020).

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

# SCC ごとに 1 本（docs/adr/0018 の ① deliberate / ② build / ③ review）と、
# ① の research ノードが kind: 'web' で呼ぶ web-research（同梱 /deep-research の model 固定版）
EXPECTED = {"deliberate", "build", "review", "web-research"}


def _scripts():
    return sorted(WORKFLOWS_DIR.glob("*.js")) if WORKFLOWS_DIR.exists() else []


def test_expected_workflows_exist():
    assert {p.stem for p in _scripts()} == EXPECTED


def test_deliberate_calls_web_research_not_bundled_deep_research():
    """同梱 /deep-research は model を渡せずセッションのモデルで 100 体前後が回る。
    kind: 'web' の小問は model 固定版の web-research を呼ぶ。"""
    text = (WORKFLOWS_DIR / "deliberate.js").read_text()
    assert "workflow('web-research'" in text
    assert "workflow('deep-research'" not in text


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
        # 同梱スクリプトの写し（web-research）は二重引用符なので、どちらの引用符も受ける
        declared = set(re.findall(r"""title['"]?:\s*['"]([^'"]+)['"]""", meta_block))
        used = set(re.findall(r"""phase\(['"]([^'"]+)['"]\)""", text))
        used |= set(re.findall(r"""phase:\s*['"]([^'"]+)['"]""", text))
        assert declared, "meta.phases が空か、引用符の形式が想定外"
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
        # 台帳と報告の置き場は main が args.ledgerDir で渡す（docs/adr/0020）。
        # web-research は deliberate から呼ばれる下請けで、報告は deliberate 側が ledgerDir に書く
        if script.stem == "web-research":
            pytest.skip("SCC のワークフローではない（deliberate の下請け）")
        assert "args.ledgerDir" in script.read_text()

    def test_every_agent_call_names_its_model(self, script):
        """役割ファイルの model: は書けない（tests/test_user_config.py が禁止）ので、ノードごとの
        モデルは呼び出しごとに指定する。指定が無い agent() はセッションのモデルに落ち、
        機械的な段階まで最上位モデルで回る（deep-research の追試で 1 回 1,000 万トークン）。"""
        text = script.read_text()
        assert re.search(r"^const MODELS = \{", text, re.M), "MODELS（既定 + args.models で上書き）が要る"
        assert "args.models" in text
        calls = _agent_calls(text)
        assert calls, "agent() の呼び出しが見つからない"
        for call in calls:
            assert "model: MODELS." in call, f"agent() の引数に model が無い: {call[:100]!r}"


def _agent_calls(text: str):
    """`agent(` から対応する `)` までを括弧の対応で切り出す（文字列内の括弧は数えない）。"""
    calls = []
    for m in re.finditer(r"\bagent\(", text):
        depth, i, quote = 0, m.start(), None
        while i < len(text):
            c = text[i]
            if quote:
                if c == "\\":
                    i += 1
                elif c == quote:
                    quote = None
            elif c in "'\"`":
                quote = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    call = text[m.start():i + 1]
                    if call != "agent()":  # コメント中の「agent()」への言及は呼び出しではない
                        calls.append(call)
                    break
            i += 1
    return calls
