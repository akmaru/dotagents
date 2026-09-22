#!/usr/bin/env python3
"""Claude Code のコンテキスト使用量を記録・分析し、削減余地を提案する。

3 つの入口がある。

  snapshot       `claude -p /context` を非対話で叩き、起動直後の内訳（システムツール・MCP・
                 メモリ・スキル）を JSON で保存する。API は呼ばれないので課金ゼロ。
  report         transcript (~/.claude/projects/**/*.jsonl) とスナップショットを突き合わせ、
                 セッションごとの増加要因と、削減候補を Markdown で出す。
  session-start  Claude Code の SessionStart hook。スナップショットが古ければ裏で取り直し、
                 前回の分析で見つかった要点があれば 1〜3 行だけ標準出力に出す
                 （SessionStart の stdout はセッションのコンテキストに入る）。

設計判断は docs/adr/0013-context-budget-monitoring.md を参照。標準ライブラリのみで動く。
transcript の形式は Claude Code の内部仕様で、バージョンで変わり得る。読めない行は黙って飛ばし、
壊れて止まるより「一部欠けた集計」を返すことを優先している。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

SNAPSHOT_ENV_GUARD = "DOTAGENTS_CONTEXT_SNAPSHOT"
# 入れ子で起動した claude が herdr の pane を乗っ取らないよう、herdr の環境変数は渡さない
STRIP_ENV_PREFIXES = ("HERDR_",)
DEFAULT_WINDOW = 200_000
BRIEF_FILENAME = "brief.txt"
REPORT_FILENAME = "report.md"


# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------


def data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return Path(base) / "dotagents" / "context"


def projects_dir() -> Path:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return Path(cfg) / "projects"


def project_slug(cwd: str) -> str:
    """Claude Code が ~/.claude/projects/ 配下に使うディレクトリ名と同じ変換。"""
    return re.sub(r"[/.]", "-", cwd)


def parse_tokens(text: str) -> int:
    """'1.1k' / '~60' / '1m' / '603' → 整数トークン。"""
    s = text.strip().lstrip("~").replace(",", "")
    m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([kKmM]?)", s)
    if not m:
        raise ValueError(f"token count not parseable: {text!r}")
    n = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "k":
        n *= 1_000
    elif unit == "m":
        n *= 1_000_000
    return int(round(n))


def fmt_tokens(n: float) -> str:
    n = int(round(n))
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def estimate_tokens(text: str) -> float:
    """文字数からのざっくり推定。日本語は 1 文字 ≒ 1 トークン弱、ASCII は 4 文字 ≒ 1 トークン。"""
    ascii_n = sum(1 for c in text if ord(c) < 128)
    return ascii_n / 4.0 + (len(text) - ascii_n) / 1.3


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# snapshot: `claude -p /context` の Markdown を構造化する
# ---------------------------------------------------------------------------


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _iter_tables(md: str):
    """'### 見出し' と、それに続く Markdown 表の行（ヘッダ・区切り線を除く）を yield する。"""
    section = None
    rows: list[list[str]] = []
    for line in md.splitlines():
        if line.startswith("### "):
            if section is not None:
                yield section, rows
            section, rows = line[4:].strip(), []
        elif line.startswith("|") and section is not None:
            cells = _split_table_row(line)
            if all(re.fullmatch(r":?-+:?", c) for c in cells if c):
                continue
            rows.append(cells)
    if section is not None:
        yield section, rows


def parse_context_markdown(md: str) -> dict:
    """`claude -p /context --output-format json` の result（Markdown）を dict にする。"""
    out: dict = {
        "model": None,
        "used_tokens": None,
        "window_tokens": None,
        "categories": {},
        "mcp_tools": [],
        "agents": [],
        "memory_files": [],
        "skills": [],
    }
    m = re.search(r"\*\*Model:\*\*\s*(\S+)", md)
    if m:
        out["model"] = m.group(1)
    m = re.search(r"\*\*Tokens:\*\*\s*([0-9.,]+[kKmM]?)\s*/\s*([0-9.,]+[kKmM]?)", md)
    if m:
        out["used_tokens"] = parse_tokens(m.group(1))
        out["window_tokens"] = parse_tokens(m.group(2))

    for section, rows in _iter_tables(md):
        body = [r for r in rows if r and r[0].lower() not in ("category", "tool", "agent type", "type", "skill")]
        if section.startswith("Estimated usage"):
            for r in body:
                if len(r) >= 2:
                    out["categories"][r[0]] = parse_tokens(r[1])
        elif section == "MCP Tools":
            for r in body:
                if len(r) >= 3:
                    out["mcp_tools"].append({"tool": r[0], "server": r[1], "tokens": parse_tokens(r[2])})
        elif section == "Custom Agents":
            for r in body:
                if len(r) >= 3:
                    out["agents"].append({"name": r[0], "source": r[1], "tokens": parse_tokens(r[2])})
        elif section == "Memory Files":
            for r in body:
                if len(r) >= 3:
                    out["memory_files"].append({"type": r[0], "path": r[1], "tokens": parse_tokens(r[2])})
        elif section == "Skills":
            for r in body:
                if len(r) >= 3:
                    out["skills"].append({"name": r[0], "source": r[1], "tokens": parse_tokens(r[2])})
    return out


def mcp_tokens_by_server(snapshot: dict) -> dict[str, int]:
    acc: Counter = Counter()
    for t in snapshot.get("mcp_tools", []):
        acc[t["server"]] += t["tokens"]
    return dict(acc)


def run_context_command(cwd: str, timeout: int = 120) -> str:
    """`claude -p /context` を叩いて result の Markdown を返す。

    --no-session-persistence で transcript を残さない（残すと report 側の集計対象に混ざる）。
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_ENV_PREFIXES)}
    env[SNAPSHOT_ENV_GUARD] = "1"
    proc = subprocess.run(
        ["claude", "-p", "/context", "--output-format", "json", "--no-session-persistence"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p /context failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}")
    payload = json.loads(proc.stdout)
    result = payload.get("result")
    if not isinstance(result, str) or "Context Usage" not in result:
        raise RuntimeError("claude -p /context returned no context breakdown; the command may have changed")
    return result


def snapshot_dir(cwd: str, base: Path | None = None) -> Path:
    return (base or data_dir()) / "snapshots" / project_slug(cwd)


def list_snapshots(cwd: str, base: Path | None = None) -> list[Path]:
    d = snapshot_dir(cwd, base)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.json") if p.name[0].isdigit())


def load_snapshot(path: Path) -> dict:
    return json.loads(path.read_text())


def take_snapshot(cwd: str, base: Path | None = None, markdown: str | None = None) -> Path:
    md = markdown if markdown is not None else run_context_command(cwd)
    parsed = parse_context_markdown(md)
    parsed["taken_at"] = now_utc().isoformat(timespec="seconds")
    parsed["cwd"] = cwd
    d = snapshot_dir(cwd, base)
    d.mkdir(parents=True, exist_ok=True)
    path = d / (now_utc().strftime("%Y%m%d-%H%M%S") + ".json")
    path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n")
    return path


def snapshot_is_stale(cwd: str, max_age_hours: float, base: Path | None = None) -> bool:
    snaps = list_snapshots(cwd, base)
    if not snaps:
        return True
    age = now_utc() - dt.datetime.fromtimestamp(snaps[-1].stat().st_mtime, dt.timezone.utc)
    return age > dt.timedelta(hours=max_age_hours)


# ---------------------------------------------------------------------------
# transcript 解析
# ---------------------------------------------------------------------------


def _content_blocks(message: dict) -> list:
    c = message.get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c if isinstance(c, list) else []


def _block_chars(block) -> int:
    if isinstance(block, str):
        return len(block)
    if isinstance(block, dict):
        if block.get("type") == "text":
            return len(block.get("text") or "")
        return len(json.dumps(block, ensure_ascii=False))
    return len(json.dumps(block, ensure_ascii=False))


def _tool_result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join((b.get("text") or "") if isinstance(b, dict) else str(b) for b in c)
    return json.dumps(c, ensure_ascii=False) if c is not None else ""


def _tool_hint(name: str, tool_input) -> str:
    """どの呼び出しだったか人が見て分かる短い手がかり。"""
    if not isinstance(tool_input, dict):
        return ""
    for key in ("description", "file_path", "command", "query", "prompt", "pattern", "url"):
        v = tool_input.get(key)
        if isinstance(v, str) and v.strip():
            v = " ".join(v.split())
            return v[:70] + ("…" if len(v) > 70 else "")
    return ""


def analyze_transcript(path: Path) -> dict | None:
    """1 セッションの transcript を読み、コンテキスト増加の内訳を推定する。

    増加量の帰属は「連続する 2 リクエスト間のコンテキスト差分」を、その間に入った要素
    （前ターンの出力・ツール結果・ユーザー入力・attachment）へ推定トークン比で按分する。
    差分は API が返した実測値なので合計は正確、内訳は推定。
    """
    requests: list[dict] = []  # 1 API リクエスト = 1 要素（同じ requestId の行は 1 つに畳む）
    by_request: dict[str, dict] = {}
    pending: list[dict] = []  # 次のリクエストまでに入った要素
    tool_names: dict[str, tuple[str, str]] = {}  # tool_use_id → (name, hint)
    meta: dict = {"session_id": None, "cwd": None, "version": None, "started": None, "ended": None}
    compactions = 0
    calls: Counter = Counter()

    try:
        fh = path.open(encoding="utf-8")
    except OSError:
        return None
    with fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain"):
                continue
            t = d.get("type")
            ts = d.get("timestamp")
            if ts:
                meta["started"] = meta["started"] or ts
                meta["ended"] = ts
            meta["session_id"] = meta["session_id"] or d.get("sessionId")
            meta["cwd"] = meta["cwd"] or d.get("cwd")
            meta["version"] = meta["version"] or d.get("version")

            if t == "assistant":
                msg = d.get("message") or {}
                rid = d.get("requestId") or d.get("uuid")
                req = by_request.get(rid)
                if req is None:
                    usage = msg.get("usage") or {}
                    ctx = (
                        (usage.get("input_tokens") or 0)
                        + (usage.get("cache_creation_input_tokens") or 0)
                        + (usage.get("cache_read_input_tokens") or 0)
                    )
                    if ctx <= 0:
                        continue
                    req = {
                        "ctx": ctx,
                        "output": usage.get("output_tokens") or 0,
                        "model": msg.get("model"),
                        "items": pending,
                        "tools": [],
                    }
                    pending = []
                    by_request[rid] = req
                    requests.append(req)
                for b in _content_blocks(msg):
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        name = b.get("name") or "?"
                        tool_names[b.get("id")] = (name, _tool_hint(name, b.get("input")))
                        req["tools"].append(name)
                        calls[name] += 1
            elif t == "user":
                msg = d.get("message") or {}
                if d.get("isCompactSummary"):
                    compactions += 1
                for b in _content_blocks(msg):
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        name, hint = tool_names.get(b.get("tool_use_id"), ("(unknown tool)", ""))
                        text = _tool_result_text(b)
                        pending.append({"kind": "tool_result", "name": name, "hint": hint, "est": estimate_tokens(text)})
                    else:
                        pending.append({"kind": "user", "name": "user prompt", "hint": "", "est": estimate_tokens(
                            b.get("text", "") if isinstance(b, dict) else str(b))})
            elif t == "attachment":
                a = d.get("attachment") or {}
                pending.append({"kind": "attachment", "name": f"attachment:{a.get('type', '?')}", "hint": "",
                                "est": estimate_tokens(json.dumps(a, ensure_ascii=False))})

    if not requests:
        return None

    by_source: Counter = Counter()
    largest: list[dict] = []
    unattributed = 0.0
    for i in range(len(requests) - 1):
        cur, nxt = requests[i], requests[i + 1]
        delta = nxt["ctx"] - cur["ctx"]
        if delta <= 0:  # compaction 直後などは帰属しない
            continue
        items = [{"kind": "assistant", "name": "assistant output", "hint": "", "est": float(cur["output"])}] + nxt["items"]
        total_est = sum(it["est"] for it in items)
        if total_est <= 0:
            unattributed += delta
            continue
        for it in items:
            share = delta * it["est"] / total_est
            by_source[it["name"]] += share
            if it["kind"] == "tool_result":
                largest.append({"tokens": share, "name": it["name"], "hint": it["hint"]})
    largest.sort(key=lambda x: -x["tokens"])

    ctxs = [r["ctx"] for r in requests]
    model = next((r["model"] for r in requests if r.get("model")), None)
    return {
        "path": str(path),
        "session_id": meta["session_id"],
        "cwd": meta["cwd"],
        "version": meta["version"],
        "model": model,
        "started": meta["started"],
        "ended": meta["ended"],
        "requests": len(requests),
        "baseline": ctxs[0],
        "peak": max(ctxs),
        "final": ctxs[-1],
        "compactions": compactions,
        "calls": dict(calls),
        "by_source": {k: int(round(v)) for k, v in by_source.items()},
        "unattributed": int(round(unattributed)),
        "largest": largest[:10],
    }


def iter_transcripts(root: Path, since: dt.datetime | None = None):
    if not root.is_dir():
        return
    for p in root.glob("*/*.jsonl"):
        if since is not None:
            mtime = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc)
            if mtime < since:
                continue
        yield p


# ---------------------------------------------------------------------------
# 提案ルール
# ---------------------------------------------------------------------------

MCP_UNUSED_MIN_TOKENS = 1_000
MEMORY_FILE_WARN_TOKENS = 3_000
SINGLE_RESULT_WARN_TOKENS = 10_000
PEAK_WARN_RATIO = 0.6
DRIFT_WARN_RATIO = 0.10


def _mcp_server_of(tool_name: str) -> str | None:
    # Claude Code の MCP ツール名は mcp__<server>__<tool>
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) >= 2:
            return parts[1]
    return None


def recommend(snapshot: dict | None, previous: dict | None, sessions: list[dict], window: int) -> list[str]:
    """人が判断する材料としての削減候補。適用は行わない。"""
    out: list[str] = []
    calls: Counter = Counter()
    for s in sessions:
        calls.update(s.get("calls", {}))

    if snapshot:
        by_server: dict[str, list[dict]] = defaultdict(list)
        for t in snapshot.get("mcp_tools", []):
            by_server[t["server"]].append(t)
        for server, tools in sorted(by_server.items(), key=lambda kv: -sum(t["tokens"] for t in kv[1])):
            total = sum(t["tokens"] for t in tools)
            used = [t for t in tools if calls.get(t["tool"], 0) > 0]
            if total >= MCP_UNUSED_MIN_TOKENS and not used:
                out.append(
                    f"MCP サーバー `{server}` は {len(tools)} ツール / 毎セッション {fmt_tokens(total)} tokens を占めるが、"
                    f"集計期間中に 1 度も呼ばれていない。`disabledMcpServers` か MCP 設定から外す候補。"
                )
            elif total >= MCP_UNUSED_MIN_TOKENS and len(used) <= len(tools) // 3:
                unused = [t for t in tools if t not in used]
                unused_tokens = sum(t["tokens"] for t in unused)
                out.append(
                    f"MCP サーバー `{server}` は {len(tools)} ツール中 {len(used)} つしか使われていない"
                    f"（未使用 {len(unused)} ツール = {fmt_tokens(unused_tokens)} tokens）。"
                    f"サーバー側でツールを絞れるなら絞る候補: "
                    + ", ".join(t["tool"].split("__", 2)[-1] for t in unused[:8])
                    + ("…" if len(unused) > 8 else "")
                )
        for f in snapshot.get("memory_files", []):
            if f["tokens"] >= MEMORY_FILE_WARN_TOKENS:
                out.append(
                    f"メモリファイル `{f['path']}` が {fmt_tokens(f['tokens'])} tokens。"
                    f"常時読まれる指示なので、場面が限られる節はスキルや rules へ移す候補。"
                )
        if previous:
            for cat, cur in snapshot.get("categories", {}).items():
                if cat in ("Free space", "Messages", "Autocompact buffer"):
                    continue
                prev = previous.get("categories", {}).get(cat)
                if prev and cur > prev * (1 + DRIFT_WARN_RATIO) and cur - prev >= 500:
                    out.append(
                        f"前回スナップショット（{previous.get('taken_at', '?')[:10]}）から `{cat}` が "
                        f"{fmt_tokens(prev)} → {fmt_tokens(cur)} tokens に増えている。何を足したか確認する。"
                    )

    tool_totals: Counter = Counter()
    for s in sessions:
        for name, tokens in s.get("by_source", {}).items():
            tool_totals[name] += tokens
    growth_total = sum(v for k, v in tool_totals.items())
    if growth_total > 0:
        for name, tokens in tool_totals.most_common(3):
            if name.startswith("attachment:") or name in ("assistant output", "user prompt"):
                continue
            if tokens / growth_total >= 0.4:
                out.append(
                    f"会話中の増加分の {tokens / growth_total:.0%} が `{name}` の結果。"
                    f"出力を head / grep で絞る、ファイルに書いて必要な部分だけ読む、サブエージェントに読ませる、"
                    f"などで減らせる。"
                )
                break

    big = [(s, r) for s in sessions for r in s.get("largest", []) if r["tokens"] >= SINGLE_RESULT_WARN_TOKENS]
    big.sort(key=lambda x: -x[1]["tokens"])
    for s, r in big[:3]:
        out.append(
            f"1 回のツール結果で {fmt_tokens(r['tokens'])} tokens: `{r['name']}` {r['hint']}"
            f"（session {str(s.get('session_id'))[:8]}）。"
        )

    hot = [s for s in sessions if s["peak"] >= window * PEAK_WARN_RATIO]
    if hot:
        ids = ", ".join(str(s.get("session_id"))[:8] for s in hot[:5])
        out.append(
            f"{len(hot)} セッションがウィンドウの {PEAK_WARN_RATIO:.0%} 以上まで達した（{ids}）。"
            f"話題が変わる時点で /clear、長い調査は別セッションやサブエージェントへ分ける。"
        )
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _fmt_ts(ts: str | None) -> str:
    return (ts or "?")[:16].replace("T", " ")


def render_report(snapshot: dict | None, previous: dict | None, sessions: list[dict], window: int,
                  days: int, cwd: str | None) -> str:
    L: list[str] = []
    scope = f"`{cwd}`" if cwd else "全プロジェクト"
    L.append(f"# コンテキスト使用量レポート（{scope} / 直近 {days} 日 / {len(sessions)} セッション）")
    L.append("")

    if snapshot:
        L.append(f"## 起動直後のベースライン（{_fmt_ts(snapshot.get('taken_at'))} 取得, {snapshot.get('model')}）")
        L.append("")
        L.append("| 区分 | tokens | 前回 |")
        L.append("|------|-------:|-----:|")
        for cat, cur in snapshot.get("categories", {}).items():
            if cat == "Free space":
                continue
            prev = (previous or {}).get("categories", {}).get(cat)
            L.append(f"| {cat} | {fmt_tokens(cur)} | {fmt_tokens(prev) if prev is not None else '-'} |")
        L.append("")
        servers = mcp_tokens_by_server(snapshot)
        if servers:
            calls: Counter = Counter()
            for s in sessions:
                for name, n in s.get("calls", {}).items():
                    srv = _mcp_server_of(name)
                    if srv:
                        calls[srv] += n
            L.append("| MCP サーバー | ツール数 | tokens | 期間中の呼び出し |")
            L.append("|--------------|--------:|-------:|----------------:|")
            for srv, tok in sorted(servers.items(), key=lambda kv: -kv[1]):
                n = sum(1 for t in snapshot["mcp_tools"] if t["server"] == srv)
                L.append(f"| {srv} | {n} | {fmt_tokens(tok)} | {calls.get(srv, 0)} |")
            L.append("")
        if snapshot.get("memory_files"):
            L.append("| メモリファイル | tokens |")
            L.append("|----------------|-------:|")
            for f in snapshot["memory_files"]:
                L.append(f"| {f['path']} | {fmt_tokens(f['tokens'])} |")
            L.append("")
    else:
        L.append("_スナップショットなし（`claude-context.py snapshot` で取得できる）_")
        L.append("")

    if sessions:
        L.append("## セッション")
        L.append("")
        L.append("| 開始 | session | model | 開始時 | 最大 | ％ | req | 主な増加要因 |")
        L.append("|------|---------|-------|-------:|-----:|---:|----:|--------------|")
        for s in sorted(sessions, key=lambda x: x.get("started") or "", reverse=True):
            top = sorted(s.get("by_source", {}).items(), key=lambda kv: -kv[1])[:3]
            top_s = ", ".join(f"{k} {fmt_tokens(v)}" for k, v in top)
            L.append(
                f"| {_fmt_ts(s.get('started'))} | {str(s.get('session_id'))[:8]} | {s.get('model') or '?'} | "
                f"{fmt_tokens(s['baseline'])} | {fmt_tokens(s['peak'])} | {s['peak'] / window:.0%} | "
                f"{s['requests']} | {top_s} |"
            )
        L.append("")
        tool_totals: Counter = Counter()
        for s in sessions:
            tool_totals.update(s.get("by_source", {}))
        total = sum(tool_totals.values())
        if total:
            L.append("### 会話中の増加分の内訳（期間合計・推定）")
            L.append("")
            L.append("| 要因 | tokens | 割合 |")
            L.append("|------|-------:|----:|")
            for name, tok in tool_totals.most_common(12):
                L.append(f"| {name} | {fmt_tokens(tok)} | {tok / total:.0%} |")
            L.append("")

    recs = recommend(snapshot, previous, sessions, window)
    L.append("## 削減候補")
    L.append("")
    if recs:
        L.extend(f"- {r}" for r in recs)
    else:
        L.append("- 目立った削減候補なし")
    L.append("")
    L.append("_内訳は API が返した実測差分を推定比で按分した値。合計は正確、個々は目安。_")
    return "\n".join(L) + "\n"


def build_report(cwd: str | None, days: int, base: Path | None = None, projects: Path | None = None) -> tuple[str, list[str]]:
    since = now_utc() - dt.timedelta(days=days)
    sessions = []
    for p in iter_transcripts(projects or projects_dir(), since):
        s = analyze_transcript(p)
        if s and (cwd is None or s.get("cwd") == cwd):
            sessions.append(s)
    snapshot = previous = None
    if cwd:
        snaps = list_snapshots(cwd, base)
        if snaps:
            snapshot = load_snapshot(snaps[-1])
        if len(snaps) >= 2:
            previous = load_snapshot(snaps[-2])
    window = (snapshot or {}).get("window_tokens") or DEFAULT_WINDOW
    md = render_report(snapshot, previous, sessions, window, days, cwd)
    return md, recommend(snapshot, previous, sessions, window)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_snapshot(args) -> int:
    cwd = os.path.abspath(args.cwd)
    base = Path(args.data_dir) if args.data_dir else None
    if args.if_older_than is not None and not snapshot_is_stale(cwd, args.if_older_than, base):
        return 0
    path = take_snapshot(cwd, base)
    # 次回の SessionStart で出す要点も、この機会に更新しておく
    md, recs = build_report(cwd, args.days, base, Path(args.projects_dir) if args.projects_dir else None)
    d = snapshot_dir(cwd, base)
    (d / REPORT_FILENAME).write_text(md)
    (d / BRIEF_FILENAME).write_text("".join(f"- {r}\n" for r in recs[:3]))
    if not args.quiet:
        print(path)
    return 0


def cmd_report(args) -> int:
    cwd = os.path.abspath(args.cwd) if args.cwd else None
    base = Path(args.data_dir) if args.data_dir else None
    md, _ = build_report(cwd, args.days, base, Path(args.projects_dir) if args.projects_dir else None)
    sys.stdout.write(md)
    return 0


def cmd_session_start(args) -> int:
    if os.environ.get(SNAPSHOT_ENV_GUARD):
        return 0  # スナップショット用に入れ子で起動した claude。何もしない
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    cwd = payload.get("cwd") or os.getcwd()
    base = Path(args.data_dir) if args.data_dir else None
    if snapshot_is_stale(cwd, args.max_age_hours, base):
        env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_ENV_PREFIXES)}
        d = snapshot_dir(cwd, base)
        d.mkdir(parents=True, exist_ok=True)
        log = (d / "snapshot.log").open("ab")
        cmd = [sys.executable, os.path.abspath(__file__), "snapshot", "--cwd", cwd, "--quiet",
               "--if-older-than", str(args.max_age_hours)]
        if args.data_dir:
            cmd += ["--data-dir", args.data_dir]
        # hook の終了を待たせないよう切り離す
        subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    brief = snapshot_dir(cwd, base) / BRIEF_FILENAME
    if brief.is_file():
        text = brief.read_text().strip()
        if text:
            print("[context-budget] 前回の分析で見つかった削減候補（詳細は `claude-context.py report`）:")
            print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("snapshot", help="claude -p /context の内訳を JSON で保存する")
    p.add_argument("--cwd", default=os.getcwd())
    p.add_argument("--data-dir")
    p.add_argument("--projects-dir")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--if-older-than", type=float, metavar="HOURS", help="最新スナップショットがこれより新しければ何もしない")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("report", help="transcript とスナップショットからレポートを出す")
    p.add_argument("--cwd", help="このプロジェクトに絞る（省略時は全プロジェクト。スナップショットは cwd 指定時のみ使う）")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--data-dir")
    p.add_argument("--projects-dir")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("session-start", help="Claude Code の SessionStart hook として呼ぶ")
    p.add_argument("--max-age-hours", type=float, default=24)
    p.add_argument("--data-dir")
    p.set_defaults(func=cmd_session_start)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
