#!/usr/bin/env python3
"""フォーカス中の pane の直近の出力に出てきた用語集の語と定義を並べる（popup 用）。

herdr の [[keys.command]] (type = "popup") から呼ばれる想定。pane の出力は
`herdr pane read` で取り、cwd から上へたどって見つけた CONTEXT.md / CONTEXT-MAP.md の
語と照合する。拾うのは見出し語と、見出しの括弧の中の別名の完全一致だけ。
出すのは定義の 1〜2 行だけで、構造の行（_種別_ など）は出さない。
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HEADING = re.compile(r"^\*\*(.+?)\*\*:\s*$")
PAREN = re.compile(r"^(.*?)[（(](.+?)[)）]$")
LINK = re.compile(r"\]\(([^)]*CONTEXT\.md)\)")


def parse_glossary(text):
    """{照合に使う名前: (見出しの表記, 定義)}。定義は構造の行（_..._）の手前まで。"""
    terms = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if not m:
            continue
        heading = m.group(1)
        definition = []
        for body in lines[i + 1:]:
            if not body.strip() or body.startswith(("_", "#", "**")):
                break
            definition.append(body.strip())
        d = " ".join(definition)
        p = PAREN.match(heading)
        names = [p.group(1).strip(), p.group(2).strip()] if p else [heading.strip()]
        for name in names:
            if name:
                terms.setdefault(name, (heading, d))
    return terms


def find_glossaries(cwd):
    found = []
    for d in [cwd, *cwd.parents]:
        context = d / "CONTEXT.md"
        if context.is_file():
            found.append(context)
        cmap = d / "CONTEXT-MAP.md"
        if cmap.is_file():
            for link in LINK.findall(cmap.read_text()):
                target = (d / link).resolve()
                if target.is_file():
                    found.append(target)
    return list(dict.fromkeys(found))


def matches(name, output):
    if name.isascii():
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", output) is not None
    return name in output


def lookup(output, glossaries):
    seen = {}
    for g in glossaries:
        for name, (heading, d) in parse_glossary(g.read_text()).items():
            if matches(name, output):
                seen.setdefault(heading, d)
    return sorted(seen.items())


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def pane_output(pane):
    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    raw = subprocess.run([herdr, "pane", "read", pane], capture_output=True, text=True, check=True).stdout
    try:  # JSON で返るなら、中の文字列をすべて連結する
        return "\n".join(strings(json.loads(raw)))
    except ValueError:
        return raw


def claude_session_cwds(pane):
    """pane で Claude Code が動いていれば、そのセッションの記録に残る cwd を新しい順に重複なく。

    Claude Code の中で作業ディレクトリを移しても pane の cwd は起動時のままなので、
    用語集を探す起点にはセッションの記録の cwd を使う。記録の cwd もツールの実行ごとに
    起動時の場所へ戻ることがあるので、最後の 1 つではなく訪れた cwd をすべて返す。
    """
    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    try:
        raw = subprocess.run([herdr, "pane", "get", pane], capture_output=True, text=True, check=True).stdout
        session = json.loads(raw)["result"]["pane"]["agent_session"]
    except (subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        return []
    if session.get("source") != "herdr:claude" or not session.get("value"):
        return []
    cwds = []
    # herdr のサーバは CLAUDE_CONFIG_DIR を持たないことがあるので、プロファイルの置き場を順に見る（ADR 0028）
    config_dirs = [os.environ.get("CLAUDE_CONFIG_DIR"), "~/.claude", "~/.claude-work"]
    for config_dir in filter(None, config_dirs):
        for transcript in Path(config_dir).expanduser().glob(f"projects/*/{session['value']}.jsonl"):
            for line in reversed(transcript.read_text(errors="replace").splitlines()):
                try:
                    cwd = json.loads(line).get("cwd")
                except ValueError:
                    continue
                if cwd:
                    cwds.append(Path(cwd))
    return list(dict.fromkeys(cwds))


def main():
    pane = os.environ.get("HERDR_ACTIVE_PANE_ID", "")
    if not pane:
        print("フォーカス中の pane を特定できない")
        return 1
    cwds = claude_session_cwds(pane) or [Path(os.environ.get("HERDR_ACTIVE_PANE_CWD") or Path.cwd())]
    glossaries = list(dict.fromkeys(g for cwd in cwds for g in find_glossaries(cwd)))
    if not glossaries:
        print(f"{', '.join(map(str, cwds))} から上に CONTEXT.md / CONTEXT-MAP.md が見つからない")
        return 1
    hits = lookup(pane_output(pane), glossaries)
    if not hits:
        print("直近の出力に用語集の語は出ていない")
        return 0
    for heading, d in hits:
        print(f"\033[1m{heading}\033[0m\n  {d}\n")
    return 0


if __name__ == "__main__":
    code = main()
    if sys.stdout.isatty():  # popup はコマンドが終わると閉じるので、読み終わるまで待つ
        input("Enter で閉じる")
    sys.exit(code)
