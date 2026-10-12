#!/usr/bin/env python3
"""ontology.py — ONTOLOGY.md（用語集の上に重ねる概念の構造）を検査・同期・Alloy で検証する。

サブコマンド:
  init   [--glossary CONTEXT.md] [--mode markdown|alloy] [-o ONTOLOGY.md]
                                    用語集の語から ONTOLOGY.md の雛形を作る（既存なら書かない）
  lint   ONTOLOGY.md               構造の静的検査（Markdown 検証の機械部分）
  scan   ONTOLOGY.md PATH...       仕様・実装とのずれ（用語のドリフト）を検出
  alloy  ONTOLOGY.md [-o out.als]  Alloy モデルを生成して出力
  verify ONTOLOGY.md [--mode M]    lint +（alloy なら）Alloy で無矛盾性・帰結・事例を検証
  setup-alloy                      Alloy の jar を取得してパスを表示

終了コード: error が 1 件以上なら 1、それ以外は 0。
依存: Python 3.10+ の標準ライブラリのみ。Alloy 検証には Java 17+ が要る。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

ALLOY_VERSION = "6.2.0"
ALLOY_URL = (
    "https://github.com/AlloyTools/org.alloytools.alloy/releases/download/"
    f"v{ALLOY_VERSION}/org.alloytools.alloy.dist.jar"
)

KINDS = {"kind", "subkind", "role", "phase", "relator", "event", "value"}
STATUSES = {"confirmed", "assumed", "open", "rejected"}
MULTS = {"one", "lone", "some", "set"}
ACTIVE = {"confirmed", "assumed"}  # Alloy の制約として採用する状態

SECTION_ALIASES = {
    "terms": ["用語", "terms"],
    "relations": ["関係", "relations"],
    "axioms": ["公理", "axioms"],
    "checks": ["帰結", "checks"],
    "scenarios": ["事例", "scenarios", "シナリオ"],
    "questions": ["未決事項", "open questions"],
    "nongoals": ["対象外", "non-goals"],
    "changelog": ["変更履歴", "changelog"],
}
ALLOY_KEYWORDS = {
    "abstract", "all", "and", "as", "assert", "but", "check", "disj", "else", "exactly",
    "extends", "fact", "for", "fun", "iden", "iff", "implies", "in", "Int", "let", "lone",
    "module", "no", "none", "not", "one", "open", "or", "pred", "run", "set", "sig", "some",
    "sum", "univ", "enum", "var", "always", "eventually", "after", "before", "historically",
    "once", "releases", "since", "triggered", "until", "steps", "String", "seq", "this",
}
IDENT_RE = re.compile(r"^[^\W\d][\w']*$", re.UNICODE)
REF_RE = re.compile(r"\[\[([^\]]+)\]\]")
NAME_ALIAS_RE = re.compile(r"^(.+?)\s*[（(]\s*([^）)]+?)\s*[）)]\s*$")


def split_name(title: str):
    """'顧客（Customer）' -> ('顧客', ['Customer'])"""
    m = NAME_ALIAS_RE.match(title.strip())
    if m:
        return m.group(1).strip(), [a.strip() for a in re.split(r"[,、/]", m.group(2)) if a.strip()]
    return title.strip(), []


def split_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [s.strip().strip("`") for s in v if s.strip()]
    return [s.strip().strip("`") for s in re.split(r"[,、]", v) if s.strip()]


# ---------------------------------------------------------------- glossary (CONTEXT.md)

@dataclass
class GlossaryTerm:
    name: str
    aliases: list
    definition: str
    avoid: list
    line: int


def parse_glossary(path: Path) -> list:
    """grill-with-docs の CONTEXT-FORMAT.md 形式の用語集を読む。"""
    terms = []
    cur = None
    for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^\*\*(.+?)\*\*\s*[:：]\s*(.*)$", ln.strip())
        if m:
            name, aliases = split_name(m.group(1))
            cur = GlossaryTerm(name, aliases, m.group(2).strip(), [], n)
            terms.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r"^_(使わない|Avoid)_\s*[:：]\s*(.*)$", ln.strip(), re.IGNORECASE)
        if m:
            # 括弧の注記と鉤括弧を外す（例: 「課題（「課題」は Problem の意味に限る）」→ 課題）
            raw = re.sub(r"[（(][^）)]*[）)]", "", m.group(2))
            cur.avoid = [w.strip("「」『』\"' ") for w in split_list(raw) if w.strip("「」『』\"' ")]
            continue
        if not ln.strip() or ln.startswith("#"):
            cur = None
            continue
        cur.definition = (cur.definition + " " + ln.strip()).strip()
    return terms


# ---------------------------------------------------------------- ontology model

@dataclass
class Item:
    section: str
    title: str
    line: int
    fields: dict = field(default_factory=dict)
    alloy: str | None = None
    body: str = ""

    def get(self, key, default=None):
        v = self.fields.get(key, default)
        return v.strip() if isinstance(v, str) else v

    def lst(self, key):
        return split_list(self.fields.get(key))

    def groups(self, key):
        """1 行なら 1 組、入れ子の箇条書きなら行ごとに 1 組。"""
        v = self.fields.get(key)
        if v is None:
            return []
        if isinstance(v, list):
            return [split_list(x) for x in v if x.strip()]
        return [split_list(v)] if v.strip() else []

    @property
    def ident(self):
        """'AX-1: 説明' -> 'AX-1'"""
        return re.split(r"[:：]", self.title, maxsplit=1)[0].strip()

    @property
    def name(self):
        return split_name(self.title)[0]

    @property
    def aliases(self):
        return split_name(self.title)[1] + self.lst("aliases")


@dataclass
class Relation:
    line: int
    id: str
    name: str
    frm: str
    to: str
    mult: str
    inverse: str
    status: str
    meaning: str


@dataclass
class Ontology:
    path: Path
    meta: dict
    items: dict
    relations: list
    glossary_path: Path | None
    glossary: list

    def section(self, s):
        return self.items.get(s, [])

    @property
    def mode(self):
        return str(self.meta.get("verification", "markdown")).strip().lower()

    @property
    def scope(self):
        try:
            return int(self.meta.get("alloy-scope", 4))
        except ValueError:
            return 4


def _section_key(heading: str):
    h = heading.strip().lower()
    for key, names in SECTION_ALIASES.items():
        if any(h.startswith(n) for n in names):
            return key
    return None


def parse(path: Path) -> Ontology:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    meta = {}
    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            m = re.match(r"^([\w-]+)\s*:\s*(.*?)\s*(#.*)?$", lines[i])
            if m:
                meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
            i += 1
        i += 1

    items: dict = {}
    relations: list = []
    section = None
    cur: Item | None = None
    last_key = None
    in_fence = False
    fence_lang = ""
    fence_buf: list = []
    header = None

    def flush():
        nonlocal cur
        if cur is not None:
            items.setdefault(cur.section, []).append(cur)
        cur = None

    while i < len(lines):
        ln = lines[i]
        lineno = i + 1
        i += 1
        if in_fence:
            if ln.strip().startswith("```"):
                in_fence = False
                if cur is not None and fence_lang == "alloy":
                    cur.alloy = "\n".join(fence_buf).strip()
            else:
                fence_buf.append(ln)
            continue
        if ln.strip().startswith("```"):
            in_fence, fence_lang, fence_buf = True, ln.strip()[3:].strip().lower(), []
            continue
        if ln.startswith("## "):
            flush()
            section, header = _section_key(ln[3:]), None
            continue
        if ln.startswith("### ") and section:
            flush()
            cur, last_key = Item(section=section, title=ln[4:].strip(), line=lineno), None
            continue
        if section == "relations" and ln.strip().startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if header is None:
                header = [c.lower() for c in cells]
                continue
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            row = dict(zip(header, cells))
            relations.append(Relation(
                line=lineno, id=row.get("id", ""), name=row.get("name", "").strip("`"),
                frm=row.get("from", "").strip("`"), to=row.get("to", "").strip("`"),
                mult=row.get("mult", "set").strip("`") or "set",
                inverse=row.get("inverse", "set").strip("`") or "set",
                status=row.get("status", "confirmed") or "confirmed",
                meaning=row.get("meaning", ""),
            ))
            continue
        if section in ("questions", "nongoals", "changelog") and cur is None:
            m = re.match(r"^\s*-\s+(.*)$", ln)
            if m:
                txt = m.group(1)
                mm = re.match(r"^`?([^`:：\s]+)`?\s*[:：]\s*(.*)$", txt)
                it = Item(section=section, title=mm.group(1) if mm else txt[:30], line=lineno, body=txt)
                rel = re.search(r"[（(]related\s*[:：]\s*([^)）]*)[)）]", txt)
                if rel:
                    it.fields["related"] = rel.group(1)
                items.setdefault(section, []).append(it)
            continue
        if cur is None:
            continue
        m = re.match(r"^-\s+([A-Za-z][\w-]*)\s*:\s*(.*)$", ln)
        if m:
            key, val = m.group(1).lower(), m.group(2).strip()
            if key == "alloy":
                cur.alloy = val.strip("`").strip() or cur.alloy
                last_key = None
                continue
            cur.fields[key] = val
            last_key = key
            continue
        m = re.match(r"^\s{2,}-\s+(.*)$", ln)
        if m and last_key and (cur.fields.get(last_key) == "" or isinstance(cur.fields.get(last_key), list)):
            if cur.fields[last_key] == "":
                cur.fields[last_key] = []
            cur.fields[last_key].append(m.group(1).strip())
            continue
        if ln.startswith("  ") and ln.strip() and last_key and isinstance(cur.fields.get(last_key), str):
            cur.fields[last_key] += " " + ln.strip()
            continue
        if ln.strip():
            cur.body += ln + "\n"
    flush()

    gpath = None
    if meta.get("glossary"):
        gpath = (path.parent / meta["glossary"]).resolve()
    elif (path.parent / "CONTEXT.md").exists():
        gpath = (path.parent / "CONTEXT.md").resolve()
    glossary = parse_glossary(gpath) if gpath and gpath.exists() else []
    return Ontology(path=path, meta=meta, items=items, relations=relations,
                    glossary_path=gpath if gpath and gpath.exists() else None, glossary=glossary)


# ---------------------------------------------------------------- shared helpers

@dataclass
class Finding:
    level: str  # error / warning / info
    code: str
    msg: str
    line: int | None = None

    def fmt(self, path):
        loc = f"{path}:{self.line}" if self.line else str(path)
        return f"[{self.level.upper():7}] {self.code}: {self.msg} ({loc})"


class Index:
    """用語名・別名・id から ONTOLOGY.md の用語を引く。"""

    def __init__(self, onto: Ontology):
        self.lookup = {}
        self.collisions = []
        for t in onto.section("terms"):
            for key in [t.name, t.get("id")] + t.aliases:
                if not key:
                    continue
                if key in self.lookup and self.lookup[key] is not t:
                    self.collisions.append((key, self.lookup[key], t))
                self.lookup[key] = t
        self.gloss = {}
        self.avoid = {}
        for g in onto.glossary:
            for key in [g.name] + g.aliases:
                self.gloss[key] = g
        for g in onto.glossary:
            for a in g.avoid:
                # 別の語として定義されている語は、使わない語として扱わない（定義が優先）
                if a not in self.gloss:
                    self.avoid[a] = g

    def resolve(self, name):
        return self.lookup.get(name.strip().strip("`")) if name else None

    def glossary_of(self, t: Item):
        for key in [t.name] + t.aliases:
            if key in self.gloss:
                return self.gloss[key]
        return None

    def definition(self, t: Item):
        g = self.glossary_of(t)
        return t.get("definition") or (g.definition if g else "")


def alloy_name(t: Item) -> str:
    """id、見出しの括弧内の別名（識別子として使えるもの）、語そのもの、の順に採る。"""
    if t.get("id"):
        return t.get("id")
    for a in split_name(t.title)[1]:
        if IDENT_RE.match(a) and a not in ALLOY_KEYWORDS:
            return a
    return t.name


DISJOINT_SETS = ("partition", "disjoint-children")
COVERING_SETS = ("partition", "covering")


def sibling_facts(t: Item, idx):
    """親 t の汎化集合から、排他な組・網羅する組・重なりうると明言した組を返す。"""
    disj, cover, overlap = [], [], []
    for key in DISJOINT_SETS:
        for g in t.groups(key):
            ms = [idx.resolve(x) for x in g]
            disj += [(a, b) for i, a in enumerate(ms) for b in ms[i + 1:] if a and b]
    for key in COVERING_SETS:
        for g in t.groups(key):
            cover.append([m for m in (idx.resolve(x) for x in g) if m])
    for g in t.groups("overlapping-children"):
        ms = [idx.resolve(x) for x in g]
        overlap += [(a, b) for i, a in enumerate(ms) for b in ms[i + 1:] if a and b]
    return disj, cover, overlap


def declared_overlaps(onto, idx):
    """term の overlaps: と親の overlapping-children: から、重なりうると明言した組を集める。"""
    pairs = set()
    for t in active_terms(onto):
        for o in t.lst("overlaps"):
            ot = idx.resolve(o)
            if ot:
                pairs.add(frozenset((t.name, ot.name)))
        for a, b in sibling_facts(t, idx)[2]:
            pairs.add(frozenset((a.name, b.name)))
    return pairs


def active_terms(onto):
    return [t for t in onto.section("terms") if t.get("status") != "rejected"]


def children_of(onto, idx):
    ch = {}
    for t in active_terms(onto):
        for p in t.lst("is-a"):
            pt = idx.resolve(p)
            if pt:
                ch.setdefault(pt.name, []).append(t)
    return ch


def ancestors(t, idx, seen=None):
    seen = set() if seen is None else seen
    for p in t.lst("is-a"):
        pt = idx.resolve(p)
        if pt and pt.name not in seen:
            seen.add(pt.name)
            ancestors(pt, idx, seen)
    return seen


# ---------------------------------------------------------------- lint

def lint(onto: Ontology) -> list:
    F = []
    idx = Index(onto)
    mode = onto.mode
    terms = onto.section("terms")

    if mode not in ("markdown", "alloy"):
        F.append(Finding("error", "META", f"verification は markdown か alloy: '{mode}'"))
    if not terms:
        F.append(Finding("error", "EMPTY", "「用語」の節に用語が 1 つもない"))
    if onto.meta.get("glossary") and not onto.glossary_path:
        F.append(Finding("error", "GLOSSARY", f"glossary: {onto.meta['glossary']} が見つからない"))
    for key, a, b in idx.collisions:
        F.append(Finding("error", "DUP", f"名前/別名 '{key}' が '{a.name}' と '{b.name}' で衝突", b.line))

    q_related = set()
    for q in onto.section("questions"):
        for r in q.lst("related") + REF_RE.findall(q.body):
            t = idx.resolve(r)
            if t:
                q_related.add(t.name)
            else:
                F.append(Finding("error", "REF", f"未決事項 {q.title} が未定義の '{r}' を参照", q.line))

    ch = children_of(onto, idx)
    referenced = set()

    def check_refs(text, owner, where, line):
        for r in REF_RE.findall(str(text or "")):
            rt = idx.resolve(r)
            if not rt:
                if r in idx.avoid:
                    continue  # 下の AVOID で報告する
                if r in idx.gloss:
                    F.append(Finding("error", "REF", f"{owner}: {where} の [[{r}]] は用語集にあるがオントロジーに無い（用語の節に足す）", line))
                else:
                    F.append(Finding("error", "REF", f"{owner}: {where} の [[{r}]] が未定義", line))
                continue
            referenced.add(rt.name)
            if rt.get("status") == "rejected":
                F.append(Finding("error", "REJECTED", f"{owner}: rejected の [[{r}]] を使っている", line))
        for word, g in idx.avoid.items():
            if f"[[{word}]]" in str(text or ""):
                F.append(Finding("error", "AVOID", f"{owner}: '{word}' は用語集で使わない語（→ {g.name}）", line))

    for t in terms:
        st, kd = t.get("status", ""), t.get("kind", "")
        if st not in STATUSES:
            F.append(Finding("error", "STATUS", f"{t.name}: status は {'/'.join(sorted(STATUSES))} のいずれか（'{st}'）", t.line))
        for key in [t.name] + t.aliases:
            if key in idx.avoid:
                F.append(Finding("error", "AVOID", f"{t.name}: '{key}' は用語集で使わない語（→ {idx.avoid[key].name}）", t.line))
        if st == "rejected":
            if not t.get("replaced-by"):
                F.append(Finding("warning", "REJECT", f"{t.name}: rejected なら replaced-by を書く", t.line))
            continue
        if kd not in KINDS:
            lvl = "warning" if st == "open" and not kd else "error"
            F.append(Finding(lvl, "KIND", f"{t.name}: kind が{'未定' if not kd else '不正 ' + repr(kd)}（{'/'.join(sorted(KINDS))}）", t.line))
        g = idx.glossary_of(t)
        if onto.glossary_path:
            if not g:
                F.append(Finding("error", "GLOSSARY", f"{t.name}: 用語集 {onto.glossary_path.name} に無い。先に用語集へ定義を書く", t.line))
            elif t.get("definition"):
                F.append(Finding("warning", "DEF-DUP", f"{t.name}: 定義は用語集が正。ONTOLOGY.md の definition は消す", t.line))
        elif not t.get("definition"):
            F.append(Finding("error" if st == "confirmed" else "warning", "DEF", f"{t.name}: 定義が無い（用語集も無い）", t.line))
        if kd in ("subkind", "role", "phase") and not t.lst("is-a"):
            F.append(Finding("error", "ISA", f"{t.name}: {kd} は is-a で上位の語を持つ", t.line))
        if st in ("assumed", "open") and t.name not in q_related:
            F.append(Finding("warning", "OPENQ", f"{t.name}: status={st} なのに未決事項から参照されていない", t.line))
        if mode == "alloy" and (not IDENT_RE.match(alloy_name(t)) or alloy_name(t) in ALLOY_KEYWORDS):
            F.append(Finding("error", "IDENT", f"{t.name}: Alloy の識別子にできない。id: を付ける", t.line))
        for p in t.lst("is-a"):
            pt = idx.resolve(p)
            if not pt:
                F.append(Finding("error", "REF", f"{t.name}: is-a の '{p}' が未定義", t.line))
            elif pt.get("status") == "rejected":
                F.append(Finding("error", "REJECTED", f"{t.name}: is-a が rejected の '{p}' を指す", t.line))
            else:
                referenced.add(pt.name)
        anc = ancestors(t, idx)
        if t.name in anc:
            F.append(Finding("error", "CYCLE", f"{t.name}: is-a が循環している", t.line))
        for d in t.lst("disjoint"):
            dt = idx.resolve(d)
            if not dt:
                F.append(Finding("error", "REF", f"{t.name}: disjoint の '{d}' が未定義", t.line))
                continue
            referenced.add(dt.name)
            if dt.name in anc or t.name in ancestors(dt, idx):
                F.append(Finding("error", "CONTRA", f"{t.name} と {dt.name} は is-a で包含関係にあるのに disjoint", t.line))
        check_refs(t.get("definition"), t.name, "definition", t.line)
        check_refs(t.get("note"), t.name, "note", t.line)
        for o in t.lst("overlaps"):
            ot = idx.resolve(o)
            if not ot:
                F.append(Finding("error", "REF", f"{t.name}: overlaps の '{o}' が未定義", t.line))
                continue
            referenced.add(ot.name)
            if ot.name in anc or t.name in ancestors(ot, idx):
                F.append(Finding("warning", "OVERLAP", f"{t.name}: '{o}' とは is-a で包含関係にあるので overlaps は意味を持たない", t.line))
        kids = ch.get(t.name, [])
        kid_names = {k.name for k in kids}
        for key in DISJOINT_SETS + ("covering", "overlapping-children"):
            for g in t.groups(key):
                for x in g:
                    xt = idx.resolve(x)
                    if not xt:
                        F.append(Finding("error", "REF", f"{t.name}: {key} の '{x}' が未定義", t.line))
                    elif xt.name not in kid_names:
                        F.append(Finding("error", "GENSET", f"{t.name}: {key} の '{x}' は {t.name} の下位の語（is-a: {t.name}）ではない", t.line))
                    else:
                        referenced.add(xt.name)
                if len(g) < 2 and key != "covering":
                    F.append(Finding("error", "GENSET", f"{t.name}: {key} には 2 つ以上の語を並べる", t.line))
        cp = t.get("complete")
        if cp and cp not in ("no", "open"):
            F.append(Finding("error", "FIELD", f"{t.name}: complete に書けるのは no / open（網羅するなら partition か covering）", t.line))
        disj, cover, overlap = sibling_facts(t, idx)
        if kids and not cover and not cp:
            F.append(Finding("warning", "UNSTATED", f"{t.name}: 下位の語で網羅されるか書いていない（partition / covering か complete: no|open）", t.line))
    # 兄弟の組ごとに、排他か重なりうるかが書かれているか（言っていないことを残さない）
    overlaps_all = declared_overlaps(onto, idx)
    for t in active_terms(onto):
        kids = ch.get(t.name, [])
        disj_pairs = {frozenset((a.name, b.name)) for a, b in sibling_facts(t, idx)[0]}
        for k in kids:
            for d in k.lst("disjoint"):
                dt = idx.resolve(d)
                if dt:
                    disj_pairs.add(frozenset((k.name, dt.name)))
        for i, a in enumerate(kids):
            for b in kids[i + 1:]:
                pr = frozenset((a.name, b.name))
                if pr in disj_pairs and pr in overlaps_all:
                    F.append(Finding("error", "CONTRA", f"{a.name} と {b.name} が排他とも重なりうるとも書かれている", t.line))
                elif pr not in disj_pairs and pr not in overlaps_all:
                    F.append(Finding("warning", "UNSTATED", f"{t.name} の下位の {a.name} と {b.name}: 排他か重なりうるか書いていない", t.line))

    names = {}
    for r in onto.relations:
        tag = r.id or r.name
        if r.status not in STATUSES:
            F.append(Finding("error", "STATUS", f"関係 {tag}: status が不正（'{r.status}'）", r.line))
        for end in (r.frm, r.to):
            et = idx.resolve(end)
            if not et:
                F.append(Finding("error", "REF", f"関係 {tag}: '{end}' が未定義", r.line))
                continue
            referenced.add(et.name)
            if et.get("status") == "rejected" and r.status != "rejected":
                F.append(Finding("error", "REJECTED", f"関係 {tag}: rejected の '{end}' を指す", r.line))
        for mv, nm in ((r.mult, "mult"), (r.inverse, "inverse")):
            if mv not in MULTS:
                F.append(Finding("error", "MULT", f"関係 {tag}: {nm} は {'/'.join(sorted(MULTS))}（'{mv}'）", r.line))
        if not r.meaning:
            F.append(Finding("warning", "MEANING", f"関係 {tag}: meaning が無い", r.line))
        if r.name in names:
            F.append(Finding("error", "DUP", f"関係名 '{r.name}' が重複", r.line))
        names[r.name] = r
        if idx.resolve(r.name):
            F.append(Finding("error", "DUP", f"関係名 '{r.name}' が用語と衝突", r.line))
        if mode == "alloy" and (not IDENT_RE.match(r.name) or r.name in ALLOY_KEYWORDS):
            F.append(Finding("error", "IDENT", f"関係 {tag}: name '{r.name}' は Alloy の識別子にできない", r.line))
        check_refs(r.meaning, f"関係 {tag}", "meaning", r.line)

    for sec, label in (("axioms", "公理"), ("checks", "帰結"), ("scenarios", "事例")):
        seen = set()
        for it in onto.section(sec):
            if it.ident in seen:
                F.append(Finding("error", "DUP", f"{label} の ID '{it.ident}' が重複", it.line))
            seen.add(it.ident)
            st = it.get("status", "confirmed")
            if st not in STATUSES:
                F.append(Finding("error", "STATUS", f"{label} {it.ident}: status が不正（'{st}'）", it.line))
            if not it.get("statement"):
                F.append(Finding("error", "STMT", f"{label} {it.ident}: statement（自然言語の命題）が無い", it.line))
            check_refs(it.get("statement"), f"{label} {it.ident}", "statement", it.line)
            if sec == "scenarios" and it.get("expect") not in ("possible", "impossible"):
                F.append(Finding("error", "EXPECT", f"事例 {it.ident}: expect は possible|impossible", it.line))
            if mode == "alloy" and st in ACTIVE and not it.alloy:
                F.append(Finding("warning", "NOALLOY", f"{label} {it.ident}: alloy 式が無いので機械検証されない", it.line))

    for t in active_terms(onto):
        if t.name not in referenced and t.name not in ch:
            F.append(Finding("info", "ISOLATED", f"{t.name}: どの is-a・関係・命題からも参照されていない", t.line))
    if onto.glossary:
        missing = [g.name for g in onto.glossary if not any(idx.resolve(k) for k in [g.name] + g.aliases)]
        if missing:
            F.append(Finding("info", "UNSTRUCTURED", f"用語集にあって構造が未記述の語: {', '.join(missing)}"))
    if not onto.section("nongoals"):
        F.append(Finding("info", "NONGOALS", "「対象外」が空。言っていないことの境界を書くと誤読が減る"))
    return F


# ---------------------------------------------------------------- scan (drift)

SCAN_SUFFIXES = {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".rs", ".go", ".java", ".kt", ".cpp", ".cc",
                 ".h", ".hpp", ".c", ".cs", ".rb", ".swift", ".scala", ".td", ".mlir", ".yaml", ".yml",
                 ".json", ".toml", ".sql"}


def scan(onto: Ontology, paths: list) -> list:
    F = []
    idx = Index(onto)
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SCAN_SUFFIXES
                      and not any(part.startswith(".") for part in f.relative_to(p).parts)]
        elif p.is_file():
            files.append(p)
    skip = {onto.path.resolve()} | ({onto.glossary_path.resolve()} if onto.glossary_path else set())
    corpus = {}
    for f in files:
        if f.resolve() in skip:
            continue
        try:
            corpus[f] = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            pass

    def where(word, limit=3):
        # ASCII の語は単語境界で、日本語などの語は部分一致で探す（日本語には単語境界が無い）
        pat = re.compile(r"(?<![\w])" + re.escape(word) + r"(?![\w])") if word.isascii() else re.compile(re.escape(word))
        hits = []
        for f, lines in corpus.items():
            for n, ln in enumerate(lines, 1):
                if pat.search(ln):
                    hits.append(f"{f}:{n}")
                    if len(hits) >= limit:
                        return hits
        return hits

    for word, g in idx.avoid.items():
        hits = where(word)
        if hits:
            F.append(Finding("warning", "AVOID-USE", f"使わない語 '{word}'（→ {g.name}）が出てくる: {', '.join(hits)}"))
    for t in onto.section("terms"):
        names = [t.name] + t.aliases + ([t.get("id")] if t.get("id") else [])
        if t.get("status") == "rejected":
            for n in names:
                hits = where(n)
                if hits:
                    F.append(Finding("error", "REJECTED-USE", f"廃止した語 '{n}'（→ {t.get('replaced-by') or '置き換え先が未定'}）が出てくる: {', '.join(hits)}", t.line))
            continue
        codes = t.lst("code")
        for c in codes:
            if not where(c, 1):
                F.append(Finding("warning", "CODE-DRIFT", f"{t.name}: code '{c}' が対象ファイルに無い（改名・削除の可能性）", t.line))
        if not any(where(n, 1) for n in names + codes):
            F.append(Finding("info", "UNUSED", f"{t.name}: 対象ファイルのどこにも出てこない", t.line))

    known = set(idx.lookup) | set(idx.gloss) | {r.name for r in onto.relations}
    for t in onto.section("terms"):
        known.update(t.lst("code"))
    cand = {}
    for f, lines in corpus.items():
        txt = "\n".join(lines)
        if f.suffix.lower() == ".md":
            toks = [a or b for a, b in re.findall(r"\*\*([^*\n]{2,30})\*\*|「([^」\n]{2,20})」", txt)]
        else:
            toks = re.findall(r"\b(?:class|struct|enum|interface|trait|type|record|sig)\s+([A-Z]\w+)", txt)
        for tk in toks:
            if tk not in known:
                cand[tk] = cand.get(tk, 0) + 1
    for tk, n in sorted(cand.items(), key=lambda x: -x[1])[:30]:
        F.append(Finding("info", "CANDIDATE", f"オントロジーに無い概念の候補 '{tk}'（{n} 箇所）"))
    return F


# ---------------------------------------------------------------- alloy generation

def _cid(s: str) -> str:
    s = re.sub(r"[^\w]", "_", s, flags=re.UNICODE)
    return s if IDENT_RE.match(s) else "x_" + s


@dataclass
class Command:
    name: str
    kind: str      # run / check
    expect: str    # sat / unsat
    purpose: str
    line: int | None = None
    severity: str = "error"


def generate_alloy(onto: Ontology, exclude: set | None = None):
    """(Alloy ソース, Command の一覧, 外せる fact のラベル一覧, ラベル→説明) を返す。"""
    exclude = exclude or set()
    idx = Index(onto)
    scope = onto.scope
    terms = active_terms(onto)
    ch = children_of(onto, idx)
    out = [f"// {onto.path.name} から ontology.py が生成。手で編集しない。",
           "// fact のラベルは ONTOLOGY.md の項目に対応する。", ""]
    facts = []  # (label, body, comment)

    def ok_term(name):
        t = idx.resolve(name)
        return t if t and t.get("status") != "rejected" else None

    fields_of = {}
    for r in onto.relations:
        ft, tt = ok_term(r.frm), ok_term(r.to)
        if r.status in ACTIVE and ft and tt:
            fields_of.setdefault(ft.name, []).append(f"{r.name}: set {alloy_name(tt)}")

    for t in terms:
        name = alloy_name(t)
        parents = [p for p in (ok_term(x) for x in t.lst("is-a")) if p]
        fl = fields_of.get(t.name, [])
        body = "{ " + ", ".join(fl) + " }" if fl else "{}"
        out.append(f"// {t.title} [{t.get('kind') or '?'}, {t.get('status')}]: {idx.definition(t)[:100]}")
        if parents:
            out.append(f"sig {name} in {alloy_name(parents[0])} {body}")
            for p in parents[1:]:
                facts.append((f"isa_{_cid(name)}_{_cid(alloy_name(p))}", f"{name} in {alloy_name(p)}", f"{t.name} は {p.name} の一種"))
        else:
            out.append(f"sig {name} {body}")
        for d in t.lst("disjoint"):
            dt = ok_term(d)
            if dt:
                a, b = sorted([name, alloy_name(dt)])
                lbl = f"disj_{_cid(a)}_{_cid(b)}"
                if lbl not in {f[0] for f in facts}:
                    facts.append((lbl, f"no {a} & {b}", f"{t.name} と {dt.name} は排他的"))
        for key in DISJOINT_SETS:
            for n, g in enumerate(t.groups(key), 1):
                ks = [alloy_name(k) for k in (ok_term(x) for x in g) if k]
                if len(ks) >= 2:
                    facts.append((f"{key.split('-')[0]}{n}_disj_{_cid(name)}",
                                  " and ".join(f"no {a} & {b}" for i, a in enumerate(ks) for b in ks[i + 1:]),
                                  f"{t.name} の {key}: {'・'.join(g)} は互いに排他的"))
        for key in COVERING_SETS:
            for n, g in enumerate(t.groups(key), 1):
                ks = [alloy_name(k) for k in (ok_term(x) for x in g) if k]
                if ks:
                    facts.append((f"{key}{n}_cover_{_cid(name)}", f"{name} = " + " + ".join(ks),
                                  f"{t.name} の {key}: {'・'.join(g)} で網羅される"))

    for r in onto.relations:
        ft, tt = ok_term(r.frm), ok_term(r.to)
        if r.status not in ACTIVE or not ft or not tt:
            continue
        tag = _cid(r.id or r.name)
        if r.mult != "set":
            facts.append((f"mult_{tag}", f"all x: {alloy_name(ft)} | {r.mult} x.{r.name}",
                          f"{r.id}: 各 {ft.name} の {r.name} 先の {tt.name} は {r.mult}"))
        if r.inverse != "set":
            facts.append((f"inv_{tag}", f"all y: {alloy_name(tt)} | {r.inverse} {r.name}.y",
                          f"{r.id}: 各 {tt.name} を {r.name} する {ft.name} は {r.inverse}"))

    for ax in onto.section("axioms"):
        if ax.get("status", "confirmed") in ACTIVE and ax.alloy:
            facts.append((f"AX_{_cid(ax.ident)}", ax.alloy, f"公理 {ax.title}（{ax.get('status', 'confirmed')}）"))

    out.append("")
    for lbl, body, cmt in facts:
        if lbl in exclude:
            out.append(f"// （外した）{lbl}: {cmt}")
            continue
        out += [f"// {cmt}", f"fact {lbl} {{\n  {body}\n}}"]
    out.append("")

    cmds = []

    def add_run(name, body, expect, purpose, line=None, severity="error", sc=None):
        cmds.append(Command(name, "run", expect, purpose, line, severity))
        out.append(f"pred p_{name} {{\n  {body}\n}}")
        out.append(f"run {name} {{ p_{name} }} for {sc or scope}")

    add_run("consistency", "", "sat", "公理系全体に少なくとも 1 つのモデルがある（無矛盾）")
    for t in terms:
        add_run(f"inhabited_{_cid(alloy_name(t))}", f"some {alloy_name(t)}", "sat", f"{t.name} が実例を持ちうる", t.line)
    for r in onto.relations:
        if r.status in ACTIVE and ok_term(r.frm) and ok_term(r.to):
            add_run(f"used_{_cid(r.id or r.name)}", f"some {r.name}", "sat",
                    f"関係 {r.id}（{r.name}）が成り立ちうる", r.line, "warning")
    for pr in sorted(declared_overlaps(onto, idx), key=lambda p: sorted(p)):
        a, b = sorted(pr)
        ta, tb = ok_term(a), ok_term(b)
        if ta and tb:
            add_run(f"overlap_{_cid(alloy_name(ta))}_{_cid(alloy_name(tb))}", f"some {alloy_name(ta)} & {alloy_name(tb)}", "sat",
                    f"重なりうると書いた {a} と {b} が実際に重なりうる", ta.line)
    for c in onto.section("checks"):
        if c.alloy and c.get("status", "confirmed") in ACTIVE:
            nm = f"check_{_cid(c.ident)}"
            cmds.append(Command(nm, "check", "unsat", f"帰結 {c.title} が公理から導かれる", c.line))
            out += [f"assert {nm} {{\n  {c.alloy}\n}}", f"check {nm} for {c.get('scope') or scope}"]
    for s in onto.section("scenarios"):
        if s.alloy and s.get("status", "confirmed") in ACTIVE:
            add_run(f"scenario_{_cid(s.ident)}", s.alloy, "sat" if s.get("expect") == "possible" else "unsat",
                    f"事例 {s.title} が {s.get('expect')}", s.line, sc=s.get("scope"))
    return "\n".join(out) + "\n", cmds, [f[0] for f in facts], {f[0]: f[2] for f in facts}


# ---------------------------------------------------------------- alloy execution

class AlloyError(Exception):
    pass


def find_jar(download=True):
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "ontology-skill" / f"alloy-{ALLOY_VERSION}.jar"
    env = os.environ.get("ALLOY_JAR")
    if env:
        if not Path(env).is_file():
            raise AlloyError(f"ALLOY_JAR={env} が無い")
        return env
    if cache.is_file():
        return str(cache)
    if not download:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    print(f"Alloy {ALLOY_VERSION} を取得します: {ALLOY_URL} -> {cache}", file=sys.stderr)
    tmp = cache.with_suffix(".part")
    with urllib.request.urlopen(ALLOY_URL) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.rename(cache)
    return str(cache)


def run_alloy(jar, src: str, workdir: Path, command="*", text=False):
    workdir.mkdir(parents=True, exist_ok=True)
    als = workdir / "model.als"
    als.write_text(src, encoding="utf-8")
    java = shutil.which("java")
    if not java:
        raise AlloyError("java が見つからない（Alloy 検証には Java 17+ が要る）")
    base = [java, "-jar", jar, "exec", "-f", "-q", "-c", command]
    args = base + (["-t", "text", "-o", "-"] if text else ["-t", "json", "-o", str(workdir / "out")]) + [str(als)]
    p = subprocess.run(args, capture_output=True, text=True)
    err = "\n".join(l for l in p.stderr.splitlines() if not l.startswith("Picked up JAVA_TOOL_OPTIONS"))
    if p.returncode != 0:
        m = re.search(r"((?:Syntax|Type) error[^\n]*\n[^\n]*)", err)
        raise AlloyError((m.group(1) if m else err[-1500:]).strip())
    if text:
        return p.stdout
    rec = json.loads((workdir / "out" / "receipt.json").read_text())
    return {name: bool(c.get("solution")) for name, c in rec["commands"].items()}


def instance_text(jar, src, workdir, cmd, limit=40):
    """反例・実例を、sig と関係の中身だけに絞って返す。"""
    raw = run_alloy(jar, src, workdir / "inst", command=cmd, text=True)
    keep = []
    for ln in raw.splitlines():
        if (ln.startswith("this/") or ln.startswith("skolem ") or re.match(r"^\$\S+=", ln)) and not ln.endswith("={}"):
            keep.append("      " + ln.replace("this/", ""))
    return "\n".join(keep[:limit]) or "      （すべて空のインスタンス）"


def unsat_core(onto, jar, cmd: Command, labels, workdir):
    """削除法で、cmd を充足不能にしている fact の極小集合を求める。"""
    removed = set()
    for lbl in labels:
        src, _, _, _ = generate_alloy(onto, exclude=removed | {lbl})
        try:
            res = run_alloy(jar, src, workdir / "core", command=cmd.name)
        except AlloyError:
            continue
        if not res.get(cmd.name, True):
            removed.add(lbl)
    return [l for l in labels if l not in removed]


def verify_alloy(onto: Ontology, explain=True, keep=None):
    F = []
    try:
        jar = find_jar()
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "ALLOY-SETUP", f"Alloy の jar を用意できない: {e}")], None
    src, cmds, labels, comments = generate_alloy(onto)
    work = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="ontology-alloy-"))
    try:
        res = run_alloy(jar, src, work)
    except AlloyError as e:
        return [Finding("error", "ALLOY-SYNTAX", f"Alloy がモデルを読めない（alloy 式を直す）:\n      {e}")], work
    consistent = res.get("consistency", False)
    for c in cmds:
        sat = res.get(c.name)
        if sat is None:
            continue
        if sat == (c.expect == "sat"):
            F.append(Finding("info", "OK", f"{c.name}: {c.purpose}", c.line))
            continue
        if c.kind == "check":
            F.append(Finding("error", "CHECK-FAIL",
                             f"{c.purpose} はずが反例がある（公理が足りないか、帰結の見込みが誤り）。反例:\n{instance_text(jar, src, work, c.name)}", c.line))
        elif c.expect == "unsat":
            F.append(Finding("error", "TOO-LOOSE",
                             f"{c.purpose} はずが成り立つモデルがある（禁じる公理が足りない）。実例:\n{instance_text(jar, src, work, c.name)}", c.line))
        elif c.name != "consistency" and not consistent:
            F.append(Finding(c.severity, "UNSAT", f"{c.purpose} はずが充足不能（公理系全体が矛盾しているため。先に consistency を直す）", c.line))
        else:
            msg = f"{c.purpose} はずが充足不能"
            if explain:
                core = unsat_core(onto, jar, c, labels, work)
                msg += ("。衝突している制約:\n" + "\n".join(f"      - {l}: {comments[l]}" for l in core)) if core \
                    else "（is-a の宣言と、最上位の語どうしが排他的という前提だけで矛盾している）"
            F.append(Finding(c.severity, "UNSAT", msg, c.line))
    return F, work


# ---------------------------------------------------------------- init

TEMPLATE_HEAD = """---
verification: {mode}   # markdown | alloy
alloy-scope: 4         # Alloy で探す各集合の要素数の上限
glossary: {glossary}
---

# {title} のオントロジー

{glossary} の語の間の構造（種別・包含・排他・関係・公理）を定める。語の定義は {glossary} が正で、ここには書かない。

## 用語

"""
TEMPLATE_TAIL = """
## 関係

| id | name | from | to | mult | inverse | status | meaning |
|----|------|------|----|------|---------|--------|---------|

## 公理

## 帰結

## 事例

## 未決事項

{questions}
## 対象外

## 変更履歴

- {date}: 用語集から雛形を作成
"""


def init(glossary: Path, mode: str, out: Path):
    if out.exists():
        print(f"{out} は既にある。書かない", file=sys.stderr)
        return 1
    terms = parse_glossary(glossary) if glossary.exists() else []
    from datetime import date
    rel = os.path.relpath(glossary, out.parent)
    title = "このリポジトリ"
    if glossary.exists():
        for ln in glossary.read_text(encoding="utf-8").splitlines():
            if ln.startswith("# "):
                title = ln[2:].strip()
                break
    body = TEMPLATE_HEAD.format(mode=mode, glossary=rel, title=title)
    qs = []
    for n, g in enumerate(terms, 1):
        label = f"{g.name}（{', '.join(g.aliases)}）" if g.aliases else g.name
        body += f"### {label}\n- kind:\n- is-a:\n- status: open\n\n"
        qs.append(f"- Q{n}: {g.name} の種別と上位の語は何か（related: {g.name}）")
    body += TEMPLATE_TAIL.format(questions="\n".join(qs) + ("\n" if qs else ""), date=date.today().isoformat())
    out.write_text(body, encoding="utf-8")
    print(out)
    return 0


# ---------------------------------------------------------------- CLI

def report(path, findings, verbose=False, as_json=False):
    if as_json:
        print(json.dumps([f.__dict__ for f in findings], ensure_ascii=False, indent=2))
    else:
        order = {"error": 0, "warning": 1, "info": 2}
        for f in sorted(findings, key=lambda f: (order[f.level], f.line or 0)):
            if f.code == "OK" and not verbose:
                continue
            print(f.fmt(path))
        oks = sum(1 for f in findings if f.code == "OK")
        n = {k: sum(1 for f in findings if f.level == k and f.code != "OK") for k in order}
        print(f"\nerror={n['error']} warning={n['warning']} info={n['info']}" + (f" alloy-ok={oks}" if oks else ""))
    return 1 if any(f.level == "error" for f in findings) else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("init")
    sp.add_argument("--glossary", default="CONTEXT.md")
    sp.add_argument("--mode", choices=["markdown", "alloy"], default="markdown")
    sp.add_argument("-o", "--output")
    for name in ("lint", "scan", "alloy", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("ontology")
        sp.add_argument("--json", action="store_true")
        sp.add_argument("-v", "--verbose", action="store_true")
        if name == "scan":
            sp.add_argument("paths", nargs="+")
        if name == "alloy":
            sp.add_argument("-o", "--output")
        if name == "verify":
            sp.add_argument("--mode", choices=["markdown", "alloy"])
            sp.add_argument("--no-explain", action="store_true", help="充足不能のときに衝突する制約を探さない")
            sp.add_argument("--keep", help="生成した model.als と結果を残すディレクトリ")
    sub.add_parser("setup-alloy")
    a = ap.parse_args(argv)

    if a.cmd == "setup-alloy":
        print(find_jar())
        return 0
    if a.cmd == "init":
        g = Path(a.glossary)
        return init(g, a.mode, Path(a.output) if a.output else g.parent / "ONTOLOGY.md")
    onto = parse(Path(a.ontology))
    if a.cmd == "lint":
        return report(a.ontology, lint(onto), a.verbose, a.json)
    if a.cmd == "scan":
        return report(a.ontology, scan(onto, a.paths), True, a.json)
    if a.cmd == "alloy":
        src = generate_alloy(onto)[0]
        if a.output:
            Path(a.output).write_text(src, encoding="utf-8")
        else:
            sys.stdout.write(src)
        return 0
    findings = lint(onto)
    if (a.mode or onto.mode) == "alloy":
        if any(f.level == "error" for f in findings):
            findings.append(Finding("error", "SKIP", "lint の error があるので Alloy の検証は走らせていない"))
        else:
            fs, work = verify_alloy(onto, explain=not a.no_explain, keep=a.keep)
            findings += fs
            if a.keep and work:
                print(f"Alloy モデル: {work / 'model.als'}", file=sys.stderr)
    return report(a.ontology, findings, a.verbose, a.json)


if __name__ == "__main__":
    sys.exit(main())
