"""
user/bin/claude-context.py（コンテキスト使用量の記録・分析）を検証する。

`claude -p /context` の Markdown と transcript JSONL はどちらも Claude Code の内部形式で、
ここに入れてある fixture は 2.1.278 で実際に出力された形を縮めたもの。形式が変わって
パーサが壊れたときに「何も出ない」のではなく、このテストで気づけるようにしておく。
`claude` コマンド自体はここでは起動しない。
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "user" / "bin" / "claude-context.py"


def _load():
    spec = importlib.util.spec_from_file_location("claude_context", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["claude_context"] = module
    spec.loader.exec_module(module)
    return module


cc = _load()

# claude -p /context --output-format json の result（2.1.278）を縮めたもの
CONTEXT_MD = """## Context Usage

**Model:** claude-opus-5[1m]
**Tokens:** 56.9k / 1m (6%)

### Estimated usage by category

| Category | Tokens | Percentage |
|----------|--------|------------|
| System prompt | 3.3k | 0.3% |
| System tools | 22.4k | 2.2% |
| MCP tools | 22.7k | 2.3% |
| Custom agents | 603 | 0.1% |
| Memory files | 4.3k | 0.4% |
| Skills | 3.6k | 0.4% |
| Messages | 8 | 0.0% |
| Free space | 910.2k | 91.0% |
| Autocompact buffer | 33k | 3.3% |

### MCP Tools

| Tool | Server | Tokens |
|------|--------|--------|
| mcp__drawio__open_drawio_xml | drawio | 1.7k |
| mcp__drawio__search_shapes | drawio | 492 |
| mcp__hindsight__recall | hindsight | 1.2k |
| mcp__hindsight__retain | hindsight | 900 |
| mcp__hindsight__clear_memories | hindsight | 182 |
| mcp__hindsight__delete_bank | hindsight | 100 |

### Custom Agents

| Agent Type | Source | Tokens |
|------------|--------|--------|
| critic | Project | 149 |

### Memory Files

| Type | Path | Tokens |
|------|------|--------|
| User | /home/u/.claude/AGENTS.md | 1.8k |
| Project | /home/u/proj/CLAUDE.md | 3.2k |

### Skills

| Skill | Source | Tokens |
|-------|--------|--------|
| madr-writer | User | ~60 |
| dataviz | Built-in | ~480 |
"""


# --- parse -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [("1.1k", 1100), ("~60", 60), ("603", 603), ("1m", 1_000_000), ("910.2k", 910_200), ("33k", 33_000)],
)
def test_parse_tokens(text, expected):
    assert cc.parse_tokens(text) == expected


def test_parse_context_markdown_categories_and_tables():
    snap = cc.parse_context_markdown(CONTEXT_MD)
    assert snap["model"] == "claude-opus-5[1m]"
    assert snap["used_tokens"] == 56_900
    assert snap["window_tokens"] == 1_000_000
    assert snap["categories"]["System tools"] == 22_400
    assert snap["categories"]["Autocompact buffer"] == 33_000
    assert len(snap["mcp_tools"]) == 6
    assert cc.mcp_tokens_by_server(snap) == {"drawio": 2192, "hindsight": 2382}
    assert snap["agents"] == [{"name": "critic", "source": "Project", "tokens": 149}]
    assert [f["tokens"] for f in snap["memory_files"]] == [1800, 3200]
    assert {s["name"]: s["tokens"] for s in snap["skills"]} == {"madr-writer": 60, "dataviz": 480}


def test_parse_context_markdown_tolerates_missing_sections():
    md = "## Context Usage\n\n**Model:** x\n**Tokens:** 10k / 200k (5%)\n"
    snap = cc.parse_context_markdown(md)
    assert snap["window_tokens"] == 200_000
    assert snap["mcp_tools"] == [] and snap["categories"] == {}


def test_project_slug_matches_claude_projects_dir():
    assert cc.project_slug("/Users/maru/ghq/github.com/akmaru/dotagents") == "-Users-maru-ghq-github-com-akmaru-dotagents"


# --- transcript ------------------------------------------------------------


def _assistant(rid, ctx, output, tools=(), cache_read=0):
    """usage を持つ assistant 行。同じ requestId をブロックごとに複数行に分けて書く（実物と同じ）。"""
    usage = {
        "input_tokens": ctx - cache_read,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": cache_read,
        "output_tokens": output,
    }
    lines = [{
        "type": "assistant", "requestId": rid, "uuid": rid + "-0", "sessionId": "sess-1",
        "cwd": "/home/u/proj", "version": "2.1.278", "timestamp": f"2026-09-22T06:{len(rid):02d}:00.000Z",
        "message": {"model": "claude-opus-5", "usage": usage, "content": [{"type": "text", "text": "ok"}]},
    }]
    for i, (tid, name, tinput) in enumerate(tools):
        lines.append({
            "type": "assistant", "requestId": rid, "uuid": f"{rid}-{i + 1}", "sessionId": "sess-1",
            "cwd": "/home/u/proj", "version": "2.1.278", "timestamp": f"2026-09-22T06:{len(rid):02d}:01.000Z",
            "message": {"model": "claude-opus-5", "usage": usage,
                        "content": [{"type": "tool_use", "id": tid, "name": name, "input": tinput}]},
        })
    return lines


def _tool_result(tid, text):
    return {"type": "user", "sessionId": "sess-1", "cwd": "/home/u/proj", "timestamp": "2026-09-22T06:30:00.000Z",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def _user(text):
    return {"type": "user", "sessionId": "sess-1", "cwd": "/home/u/proj", "timestamp": "2026-09-22T06:00:00.000Z",
            "message": {"role": "user", "content": text}}


def _write_transcript(path: Path, records):
    with path.open("w") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")
        fh.write("this line is not json\n")  # 壊れた行は無視される


def test_analyze_transcript_attributes_growth_to_tool_results(tmp_path):
    big = "x" * 40_000  # ≒ 10k tokens
    records = [
        _user("hello"),
        *_assistant("r1", ctx=80_000, output=200, tools=[("t1", "Bash", {"command": "cat big.log", "description": "Read the log"})]),
        _tool_result("t1", big),
        *_assistant("r2", ctx=90_200, output=100, tools=[("t2", "mcp__hindsight__recall", {"query": "q"})]),
        _tool_result("t2", "short"),
        *_assistant("r3", ctx=90_400, output=50),
    ]
    p = tmp_path / "sess-1.jsonl"
    _write_transcript(p, records)

    s = cc.analyze_transcript(p)
    assert s["session_id"] == "sess-1"
    assert s["cwd"] == "/home/u/proj"
    assert s["requests"] == 3, "同じ requestId の複数行は 1 リクエストに畳む"
    assert (s["baseline"], s["peak"], s["final"]) == (80_000, 90_400, 90_400)
    assert s["calls"] == {"Bash": 1, "mcp__hindsight__recall": 1}
    # r1→r2 の +10.2k のほぼ全部が Bash の結果に帰属する（assistant 出力 200 は按分で小さい）
    assert s["by_source"]["Bash"] > 9_500
    assert s["largest"][0]["name"] == "Bash"
    assert s["largest"][0]["hint"] == "Read the log"
    # 内訳の合計はコンテキストの実測増分に一致する
    assert abs(sum(s["by_source"].values()) - (90_400 - 80_000)) <= 2


def test_analyze_transcript_skips_sidechain_and_empty(tmp_path):
    p = tmp_path / "empty.jsonl"
    _write_transcript(p, [_user("hi"), {**_assistant("r1", 1000, 10)[0], "isSidechain": True}])
    assert cc.analyze_transcript(p) is None


def test_analyze_transcript_counts_compaction_without_negative_attribution(tmp_path):
    records = [
        *_assistant("r1", ctx=150_000, output=100, tools=[("t1", "Read", {"file_path": "a.py"})]),
        _tool_result("t1", "y" * 4000),
        {**_user("summary"), "isCompactSummary": True},
        *_assistant("r2", ctx=20_000, output=100),
    ]
    p = tmp_path / "c.jsonl"
    _write_transcript(p, records)
    s = cc.analyze_transcript(p)
    assert s["compactions"] == 1
    assert s["by_source"] == {}  # 減った区間は帰属しない


# --- recommend / report ----------------------------------------------------


def _session(calls, by_source=None, peak=100_000, largest=None):
    return {"session_id": "abcdef12", "cwd": "/home/u/proj", "model": "m", "started": "2026-09-22T06:00:00Z",
            "requests": 5, "baseline": 80_000, "peak": peak, "final": peak, "compactions": 0,
            "calls": calls, "by_source": by_source or {}, "unattributed": 0, "largest": largest or []}


def test_recommend_flags_unused_and_mostly_unused_mcp_servers():
    snap = cc.parse_context_markdown(CONTEXT_MD)
    sessions = [_session({"mcp__hindsight__recall": 3, "Bash": 10})]
    recs = cc.recommend(snap, None, sessions, window=1_000_000)
    assert any("`drawio`" in r and "1 度も呼ばれていない" in r for r in recs)
    assert any("`hindsight`" in r and "4 ツール中 1 つ" in r for r in recs)


def test_recommend_flags_large_memory_file_and_drift():
    snap = cc.parse_context_markdown(CONTEXT_MD)
    prev = json.loads(json.dumps(snap))
    prev["categories"]["MCP tools"] = 10_000
    prev["taken_at"] = "2026-09-01T00:00:00+00:00"
    recs = cc.recommend(snap, prev, [], window=1_000_000)
    assert any("/home/u/proj/CLAUDE.md" in r for r in recs)
    assert any("`MCP tools`" in r and "10.0k → 22.7k" in r for r in recs)
    assert not any("AGENTS.md" in r for r in recs), "3k 未満のメモリファイルは指摘しない"


def test_recommend_flags_dominant_tool_and_big_results_and_hot_sessions():
    sessions = [_session(
        {"Bash": 20},
        by_source={"Bash": 90_000, "assistant output": 5_000},
        peak=700_000,
        largest=[{"tokens": 30_000, "name": "Bash", "hint": "cat huge.log"}],
    )]
    recs = cc.recommend(None, None, sessions, window=1_000_000)
    joined = "\n".join(recs)
    assert "`Bash` の結果" in joined
    assert "30.0k tokens: `Bash` cat huge.log" in joined
    assert "60% 以上" in joined


def test_recommend_is_quiet_when_nothing_stands_out():
    snap = cc.parse_context_markdown(CONTEXT_MD)
    snap["memory_files"] = []
    sessions = [_session({"mcp__hindsight__recall": 1, "mcp__hindsight__retain": 1,
                          "mcp__hindsight__clear_memories": 1, "mcp__drawio__open_drawio_xml": 1},
                         by_source={"Bash": 100, "Read": 100, "assistant output": 100})]
    assert cc.recommend(snap, None, sessions, window=1_000_000) == []


def test_snapshot_and_report_round_trip(tmp_path):
    data = tmp_path / "data"
    projects = tmp_path / "projects"
    cwd = "/home/u/proj"
    slug_dir = projects / cc.project_slug(cwd)
    slug_dir.mkdir(parents=True)
    _write_transcript(slug_dir / "s.jsonl", [
        _user("hi"),
        *_assistant("r1", ctx=80_000, output=100, tools=[("t1", "Bash", {"command": "ls"})]),
        _tool_result("t1", "a" * 400),
        *_assistant("r2", ctx=80_300, output=50),
    ])

    path = cc.take_snapshot(cwd, base=data, markdown=CONTEXT_MD)
    assert path.parent == data / "snapshots" / cc.project_slug(cwd)
    assert cc.snapshot_is_stale(cwd, max_age_hours=1, base=data) is False
    assert cc.snapshot_is_stale("/other", max_age_hours=1, base=data) is True

    md, recs = cc.build_report(cwd, days=3650, base=data, projects=projects)
    assert "起動直後のベースライン" in md
    assert "| drawio | 2 | 2.2k | 0 |" in md
    assert "| 2026-09-22 06:00 | sess-1 |" in md
    assert any("`drawio`" in r for r in recs)
    # スナップショットが無いプロジェクトでもセッション表は出る
    md_all, _ = cc.build_report(None, days=3650, base=data, projects=projects)
    assert "スナップショットなし" in md_all and "sess-1" in md_all


def test_session_start_hook_is_noop_inside_snapshot_process(monkeypatch, capsys):
    monkeypatch.setenv(cc.SNAPSHOT_ENV_GUARD, "1")
    assert cc.main(["session-start"]) == 0
    assert capsys.readouterr().out == ""


def test_session_start_hook_prints_cached_brief_and_spawns_snapshot(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(cc.SNAPSHOT_ENV_GUARD, raising=False)
    cwd = "/home/u/proj"
    d = cc.snapshot_dir(cwd, tmp_path)
    d.mkdir(parents=True)
    (d / cc.BRIEF_FILENAME).write_text("- MCP サーバー `drawio` は使われていない\n")
    spawned = []
    monkeypatch.setattr(cc.subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    monkeypatch.setenv("HERDR_PANE_ID", "pane-1")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps({"cwd": cwd, "hook_event_name": "SessionStart"})))

    assert cc.main(["session-start", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "[context-budget]" in out and "`drawio`" in out
    assert len(spawned) == 1, "スナップショットが無いので裏で取りに行く"
    cmd, kw = spawned[0]
    assert cmd[1:4] == [str(SCRIPT), "snapshot", "--cwd"]
    assert "HERDR_PANE_ID" not in kw["env"], "入れ子の claude に herdr の pane を渡さない"
    assert kw["start_new_session"] is True


# --- 配布 -------------------------------------------------------------------


def test_script_is_executable_and_linked_by_install_sh():
    import os
    assert os.access(SCRIPT, os.X_OK)
    install = (ROOT / "user" / "install.sh").read_text()
    assert "claude-context.py" in install
    assert "session-start" in install, "install.sh が SessionStart hook を登録する"


def test_repo_settings_json_does_not_carry_the_hook():
    # hooks.SessionStart は herdr も書く配列で、jq の deep merge では配列が丸ごと置換される
    # (docs/adr/0009)。リポジトリ側に持たせると herdr の hook を消してしまう。
    settings = json.loads((ROOT / "user" / "settings.json").read_text())
    assert "claude-context" not in json.dumps(settings.get("hooks", {}))
