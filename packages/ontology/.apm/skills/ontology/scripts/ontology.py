#!/usr/bin/env python3
"""ontology.py — 用語集（CONTEXT.md）の語の構造を検査し、仕様・実装とのずれを探し、Alloy で検証する。

書式は glossary スキルの CONTEXT-FORMAT.md（語の構造の行と、関係・公理・帰結・事例の節）。

サブコマンド:
  lint   CONTEXT.md               構造の静的検査（Markdown 検証の機械部分）
  scan   CONTEXT.md PATH...       仕様・実装とのずれ（使わない語、識別子の消失、未登録の概念）を探す
  alloy  CONTEXT.md [-o out.als]  Alloy モデルを生成して出力
  verify CONTEXT.md [--mode M]    lint +（alloy なら）Alloy で無矛盾性・帰結・事例を検証
  setup-alloy                     Alloy の jar を取得してパスを表示

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
STATUSES = {"confirmed", "assumed", "open"}
MULTS = {"one", "lone", "some", "set"}
ACTIVE = {"confirmed", "assumed"}  # 制約として採用する状態

# 構造の行のラベル（日本語 / English）→ 内部のキー
LABELS = {
    "使わない": "avoid", "avoid": "avoid",
    "種別": "kind", "kind": "kind",
    "上位": "is-a", "is-a": "is-a",
    "分割": "partition", "partition": "partition",
    "排他な下位": "disjoint-children", "disjoint-children": "disjoint-children",
    "網羅する下位": "covering", "covering": "covering",
    "重なりうる下位": "overlapping-children", "overlapping-children": "overlapping-children",
    "網羅": "complete", "complete": "complete",
    "排他": "disjoint", "disjoint": "disjoint",
    "重なりうる": "overlaps", "overlaps": "overlaps",
    "状態": "status", "status": "status",
    "コード": "code", "code": "code",
    "id": "id",
}
STRUCTURE_KEYS = set(LABELS.values()) - {"avoid"}


def label_key(label: str):
    """構造の行のラベル（`_種別_` の中身、英語は大文字小文字を問わない）を内部のキーにする。"""
    label = label.strip()
    return LABELS.get(label) or LABELS.get(label.lower())

SECTION_ALIASES = {
    "terms": ["用語", "terms", "language"],
    "relations": ["関係", "relations"],
    "axioms": ["公理", "axioms"],
    "checks": ["帰結", "checks", "consequences"],
    "scenarios": ["事例", "cases", "scenarios"],
    "questions": ["未決事項", "open questions"],
    "nongoals": ["対象外", "non-goals", "out of scope"],
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
TERM_RE = re.compile(r"^\*\*(.+?)\*\*\s*[:：]\s*(.*)$")
LABEL_RE = re.compile(r"^_([^_]+)_\s*[:：]\s*(.*)$")


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
        v = "、".join(v)
    return [s.strip().strip("`「」『』\"' ") for s in re.split(r"[,、]", v) if s.strip().strip("`「」『』\"' ")]


# ---------------------------------------------------------------- model

@dataclass
class Term:
    name: str
    aliases: list
    line: int
    definition: str = ""
    lines: dict = field(default_factory=dict)  # key -> [raw value, ...]（同じラベルの行を繰り返せる）
    unknown: list = field(default_factory=list)

    def get(self, key, default=None):
        v = self.lines.get(key)
        return v[0].strip() if v else default

    def lst(self, key):
        return split_list(self.lines.get(key))

    def groups(self, key):
        return [split_list(v) for v in self.lines.get(key, []) if split_list(v)]

    @property
    def avoid(self):
        # 括弧の注記を外す（例: 「課題（「課題」は Problem の意味に限る）」→ 課題）
        return split_list([re.sub(r"[（(][^）)]*[）)]", "", v) for v in self.lines.get("avoid", [])])

    @property
    def structured(self):
        return any(k in STRUCTURE_KEYS for k in self.lines)

    @property
    def kind(self):
        return self.get("kind")

    @property
    def status(self):
        return self.get("status", "confirmed")


@dataclass
class Item:
    """公理・帰結・事例・未決事項・対象外の 1 件。"""
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

    @property
    def ident(self):
        return re.split(r"[:：]", self.title, maxsplit=1)[0].strip()


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
class Glossary:
    path: Path
    meta: dict
    terms: list
    items: dict
    relations: list

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

    @property
    def structured_terms(self):
        return [t for t in self.terms if t.kind]


def _section_key(heading: str):
    h = heading.strip().lower()
    for key, names in SECTION_ALIASES.items():
        if any(h.startswith(n) for n in names):
            return key
    return None


def parse(path: Path) -> Glossary:
    lines = path.read_text(encoding="utf-8").splitlines()
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

    terms, items, relations = [], {}, []
    section = None
    term: Term | None = None
    cur: Item | None = None
    last_key = None
    in_fence, fence_lang, fence_buf = False, "", []
    header = None

    def flush_item():
        nonlocal cur
        if cur is not None:
            items.setdefault(cur.section, []).append(cur)
        cur = None

    while i < len(lines):
        ln, lineno = lines[i], i + 1
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
            flush_item()
            term, section, header = None, _section_key(ln[3:]), None
            continue

        if section == "terms":
            m = TERM_RE.match(ln.strip())
            if m and not ln.startswith(" "):
                name, aliases = split_name(m.group(1))
                term = Term(name, aliases, lineno, definition=m.group(2).strip())
                terms.append(term)
                continue
            if term is None:
                continue
            if not ln.strip() or ln.startswith("#"):
                term = None
                continue
            m = LABEL_RE.match(ln.strip())
            if m:
                key = label_key(m.group(1))
                if key:
                    term.lines.setdefault(key, []).append(m.group(2).strip())
                else:
                    term.unknown.append(m.group(1))
                continue
            term.definition = (term.definition + " " + ln.strip()).strip()
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
        if section in ("axioms", "checks", "scenarios"):
            if ln.startswith("### "):
                flush_item()
                cur, last_key = Item(section=section, title=ln[4:].strip(), line=lineno), None
                continue
            if cur is None:
                continue
            m = re.match(r"^-\s+([A-Za-z][\w-]*)\s*:\s*(.*)$", ln)
            if m:
                key, val = m.group(1).lower(), m.group(2).strip()
                if key == "alloy":
                    cur.alloy = val.strip("`").strip() or cur.alloy
                    last_key = None
                else:
                    cur.fields[key], last_key = val, key
                continue
            if ln.startswith("  ") and ln.strip() and last_key:
                cur.fields[last_key] += " " + ln.strip()
                continue
            if ln.strip():
                cur.body += ln + "\n"
            continue
        if section in ("questions", "nongoals"):
            m = re.match(r"^\s*-\s+(.*)$", ln)
            if m:
                txt = m.group(1)
                mm = re.match(r"^`?([^`:：\s]+)`?\s*[:：]\s*(.*)$", txt)
                it = Item(section=section, title=mm.group(1) if mm else txt[:30], line=lineno, body=txt)
                rel = re.search(r"[（(]related\s*[:：]\s*([^)）]*)[)）]", txt)
                if rel:
                    it.fields["related"] = rel.group(1)
                items.setdefault(section, []).append(it)
    flush_item()
    return Glossary(path=path, meta=meta, terms=terms, items=items, relations=relations)


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
    """語・別名・_ID_ から語を引く。使わない語の表も持つ。"""

    def __init__(self, g: Glossary):
        self.lookup = {}
        self.collisions = []
        for t in g.terms:
            for key in [t.name, t.get("id")] + t.aliases:
                if not key:
                    continue
                if key in self.lookup and self.lookup[key] is not t:
                    self.collisions.append((key, self.lookup[key], t))
                self.lookup[key] = t
        self.avoid = {}
        for t in g.terms:
            for a in t.avoid:
                # 別の語として定義されている語は、使わない語として扱わない（定義が優先）
                if a not in self.lookup:
                    self.avoid[a] = t

    def resolve(self, name):
        return self.lookup.get(name.strip().strip("`")) if name else None


def alloy_name(t: Term) -> str:
    """_ID_、見出しの括弧内の英語名（識別子にできるもの）、語そのもの、の順に採る。"""
    if t.get("id"):
        return t.get("id")
    for a in t.aliases:
        if IDENT_RE.match(a) and a not in ALLOY_KEYWORDS:
            return a
    return t.name


DISJOINT_SETS = ("partition", "disjoint-children")
COVERING_SETS = ("partition", "covering")


def children_of(g, idx):
    ch = {}
    for t in g.structured_terms:
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


def sibling_facts(t: Term, idx):
    """親 t の行から、排他な組・網羅する組・重なりうると明言した組を返す。"""
    disj, cover, overlap = [], [], []
    for key in DISJOINT_SETS:
        for grp in t.groups(key):
            ms = [idx.resolve(x) for x in grp]
            disj += [(a, b) for i, a in enumerate(ms) for b in ms[i + 1:] if a and b]
    for key in COVERING_SETS:
        for grp in t.groups(key):
            cover.append([m for m in (idx.resolve(x) for x in grp) if m])
    for grp in t.groups("overlapping-children"):
        ms = [idx.resolve(x) for x in grp]
        overlap += [(a, b) for i, a in enumerate(ms) for b in ms[i + 1:] if a and b]
    return disj, cover, overlap


def declared_overlaps(g, idx):
    pairs = set()
    for t in g.structured_terms:
        for o in t.lst("overlaps"):
            ot = idx.resolve(o)
            if ot:
                pairs.add(frozenset((t.name, ot.name)))
        for a, b in sibling_facts(t, idx)[2]:
            pairs.add(frozenset((a.name, b.name)))
    return pairs


# ---------------------------------------------------------------- lint

def lint(g: Glossary) -> list:
    F = []
    idx = Index(g)
    mode = g.mode
    structured = g.structured_terms

    if mode not in ("markdown", "alloy"):
        F.append(Finding("error", "META", f"verification は markdown か alloy（'{mode}'）"))
    if not g.terms:
        F.append(Finding("error", "EMPTY", "「用語」の節に語が 1 つも無い"))
    for key, a, b in idx.collisions:
        F.append(Finding("error", "DUP", f"名前/別名 '{key}' が '{a.name}' と '{b.name}' で衝突", b.line))

    q_related = set()
    for q in g.section("questions"):
        for r in q.lst("related") + REF_RE.findall(q.body):
            t = idx.resolve(r)
            if t:
                q_related.add(t.name)
            else:
                F.append(Finding("error", "REF", f"未決事項 {q.title} が未定義の '{r}' を参照", q.line))

    ch = children_of(g, idx)
    referenced = set()

    def need_structured(ref, owner, where, line):
        """構造の行・関係から参照される語は、定義されていて _種別_ を持つ。"""
        t = idx.resolve(ref)
        if not t:
            hint = f"（使わない語。→ {idx.avoid[ref].name}）" if ref in idx.avoid else ""
            F.append(Finding("error", "REF", f"{owner}: {where} の '{ref}' が未定義{hint}", line))
            return None
        if not t.kind:
            F.append(Finding("error", "UNSTRUCTURED-REF", f"{owner}: {where} の '{t.name}' に _種別_ が無い（先に種別を決める）", line))
            return None
        referenced.add(t.name)
        return t

    def check_text_refs(text, owner, where, line):
        for r in REF_RE.findall(str(text or "")):
            if r in idx.avoid:
                F.append(Finding("error", "AVOID", f"{owner}: {where} の [[{r}]] は使わない語（→ {idx.avoid[r].name}）", line))
                continue
            t = idx.resolve(r)
            if not t:
                F.append(Finding("error", "REF", f"{owner}: {where} の [[{r}]] が未定義", line))
            else:
                referenced.add(t.name)

    for t in g.terms:
        if not t.definition:
            F.append(Finding("error", "DEF", f"{t.name}: 定義が無い", t.line))
        for u in t.unknown:
            F.append(Finding("warning", "LABEL", f"{t.name}: 知らないラベル _{u}_（glossary の CONTEXT-FORMAT.md を確かめる）", t.line))
        for key in [t.name] + t.aliases:
            if key in idx.avoid:
                F.append(Finding("error", "AVOID", f"{t.name}: '{key}' は {idx.avoid[key].name} の使わない語", t.line))
        if not t.structured:
            continue
        kd, st = t.kind, t.status
        if not kd:
            F.append(Finding("error", "KIND", f"{t.name}: 構造の行があるのに _種別_ が無い", t.line))
            continue
        if kd not in KINDS:
            F.append(Finding("error", "KIND", f"{t.name}: _種別_ は {'/'.join(sorted(KINDS))} のいずれか（'{kd}'）", t.line))
        if st not in STATUSES:
            F.append(Finding("error", "STATUS", f"{t.name}: _状態_ は {'/'.join(sorted(STATUSES))} のいずれか（'{st}'）", t.line))
        if st in ("assumed", "open") and t.name not in q_related:
            F.append(Finding("warning", "OPENQ", f"{t.name}: _状態_ が {st} なのに未決事項から参照されていない", t.line))
        if kd in ("subkind", "role", "phase") and not t.lst("is-a"):
            F.append(Finding("error", "ISA", f"{t.name}: {kd} は _上位_ を持つ", t.line))
        if mode == "alloy" and (not IDENT_RE.match(alloy_name(t)) or alloy_name(t) in ALLOY_KEYWORDS):
            F.append(Finding("error", "IDENT", f"{t.name}: Alloy の識別子にできない。見出しの括弧に英語名を入れるか _ID_ を書く", t.line))
        parents = [p for p in (need_structured(x, t.name, "_上位_", t.line) for x in t.lst("is-a")) if p]
        if parents and t.definition and not any(n in t.definition for p in parents for n in [p.name] + p.aliases):
            F.append(Finding("warning", "GENUS", f"{t.name}: 定義が _上位_ の {'・'.join(p.name for p in parents)} に触れていない（定義と構造がずれていないか）", t.line))
        anc = ancestors(t, idx)
        if t.name in anc:
            F.append(Finding("error", "CYCLE", f"{t.name}: _上位_ が循環している", t.line))
        for d in t.lst("disjoint"):
            dt = need_structured(d, t.name, "_排他_", t.line)
            if dt and (dt.name in anc or t.name in ancestors(dt, idx)):
                F.append(Finding("error", "CONTRA", f"{t.name} と {dt.name} は上位・下位の関係なのに _排他_", t.line))
        for o in t.lst("overlaps"):
            ot = need_structured(o, t.name, "_重なりうる_", t.line)
            if ot and (ot.name in anc or t.name in ancestors(ot, idx)):
                F.append(Finding("warning", "OVERLAP", f"{t.name}: '{o}' とは上位・下位の関係なので _重なりうる_ は意味を持たない", t.line))
        kids = ch.get(t.name, [])
        kid_names = {k.name for k in kids}
        for key in DISJOINT_SETS + ("covering", "overlapping-children"):
            for grp in t.groups(key):
                for x in grp:
                    xt = need_structured(x, t.name, key, t.line)
                    if xt and xt.name not in kid_names:
                        F.append(Finding("error", "GENSET", f"{t.name}: '{x}' は {t.name} を _上位_ に持たない", t.line))
                if len(grp) < 2 and key != "covering":
                    F.append(Finding("error", "GENSET", f"{t.name}: 排他・重なりの組には 2 つ以上の語を並べる", t.line))
        cp = t.get("complete")
        if cp and cp not in ("no", "open"):
            F.append(Finding("error", "FIELD", f"{t.name}: _網羅_ は no / open（網羅するなら _分割_ か _網羅する下位_）", t.line))
        _, cover, _ = sibling_facts(t, idx)
        if kids and not cover and not cp:
            F.append(Finding("warning", "UNSTATED", f"{t.name}: 下位の語で網羅されるか書いていない（_分割_ / _網羅する下位_ か _網羅_: no|open）", t.line))
        for c in t.lst("code"):
            if not re.fullmatch(r"[\w.:$-]+", c):
                F.append(Finding("warning", "CODE", f"{t.name}: _コード_ '{c}' は識別子に見えない", t.line))

    overlaps_all = declared_overlaps(g, idx)
    for t in structured:
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
    for r in g.relations:
        tag = r.id or r.name
        if r.status not in STATUSES:
            F.append(Finding("error", "STATUS", f"関係 {tag}: status が不正（'{r.status}'）", r.line))
        for end in (r.frm, r.to):
            need_structured(end, f"関係 {tag}", "from/to", r.line)
        for mv, nm in ((r.mult, "mult"), (r.inverse, "inverse")):
            if mv not in MULTS:
                F.append(Finding("error", "MULT", f"関係 {tag}: {nm} は {'/'.join(sorted(MULTS))}（'{mv}'）", r.line))
        if not r.meaning:
            F.append(Finding("warning", "MEANING", f"関係 {tag}: meaning が無い", r.line))
        if r.name in names:
            F.append(Finding("error", "DUP", f"関係名 '{r.name}' が重複", r.line))
        names[r.name] = r
        if idx.resolve(r.name):
            F.append(Finding("error", "DUP", f"関係名 '{r.name}' が語と衝突", r.line))
        if mode == "alloy" and (not IDENT_RE.match(r.name) or r.name in ALLOY_KEYWORDS):
            F.append(Finding("error", "IDENT", f"関係 {tag}: name '{r.name}' は Alloy の識別子にできない", r.line))
        check_text_refs(r.meaning, f"関係 {tag}", "meaning", r.line)

    for sec, label in (("axioms", "公理"), ("checks", "帰結"), ("scenarios", "事例")):
        seen = set()
        for it in g.section(sec):
            if it.ident in seen:
                F.append(Finding("error", "DUP", f"{label} の ID '{it.ident}' が重複", it.line))
            seen.add(it.ident)
            st = it.get("status", "confirmed")
            if st not in STATUSES:
                F.append(Finding("error", "STATUS", f"{label} {it.ident}: status が不正（'{st}'）", it.line))
            if not it.get("statement"):
                F.append(Finding("error", "STMT", f"{label} {it.ident}: statement（自然言語の命題）が無い", it.line))
            check_text_refs(it.get("statement"), f"{label} {it.ident}", "statement", it.line)
            if sec == "scenarios" and it.get("expect") not in ("possible", "impossible"):
                F.append(Finding("error", "EXPECT", f"事例 {it.ident}: expect は possible|impossible", it.line))
            if mode == "alloy" and st in ACTIVE and not it.alloy:
                F.append(Finding("warning", "NOALLOY", f"{label} {it.ident}: alloy 式が無いので機械検証されない", it.line))

    for t in structured:
        if t.name not in referenced and t.name not in ch:
            F.append(Finding("info", "ISOLATED", f"{t.name}: どの _上位_・関係・命題からも参照されていない", t.line))
    bare = [t.name for t in g.terms if not t.structured]
    if bare:
        F.append(Finding("info", "UNSTRUCTURED", f"構造が未記述の語（{len(bare)}/{len(g.terms)}）: {', '.join(bare)}"))
    if structured and not g.section("nongoals"):
        F.append(Finding("info", "NONGOALS", "「対象外」が空。言っていないことの境界を書くと誤読が減る"))
    return F


# ---------------------------------------------------------------- scan (drift)

SCAN_SUFFIXES = {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".rs", ".go", ".java", ".kt", ".cpp", ".cc",
                 ".h", ".hpp", ".c", ".cs", ".rb", ".swift", ".scala", ".td", ".mlir", ".yaml", ".yml",
                 ".json", ".toml", ".sql"}


def scan(g: Glossary, paths: list) -> list:
    F = []
    idx = Index(g)
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += [f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SCAN_SUFFIXES
                      and not any(part.startswith(".") for part in f.relative_to(p).parts)]
        elif p.is_file():
            files.append(p)
    corpus = {}
    for f in files:
        if f.resolve() == g.path.resolve():
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

    for word, t in idx.avoid.items():
        hits = where(word)
        if hits:
            F.append(Finding("warning", "AVOID-USE", f"使わない語 '{word}'（→ {t.name}）が出てくる: {', '.join(hits)}", t.line))
    for t in g.terms:
        codes = t.lst("code")
        for c in codes:
            if not where(c, 1):
                F.append(Finding("warning", "CODE-DRIFT", f"{t.name}: _コード_ '{c}' が対象ファイルに無い（改名・削除の可能性）", t.line))
        if not any(where(n, 1) for n in [t.name] + t.aliases + codes):
            F.append(Finding("info", "UNUSED", f"{t.name}: 対象ファイルのどこにも出てこない", t.line))

    known = set(idx.lookup) | set(idx.avoid) | {r.name for r in g.relations}
    for t in g.terms:
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
        F.append(Finding("info", "CANDIDATE", f"用語集に無い概念の候補 '{tk}'（{n} 箇所）"))
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


def generate_alloy(g: Glossary, exclude: set | None = None):
    """(Alloy ソース, Command の一覧, 外せる fact のラベル一覧, ラベル→説明) を返す。"""
    exclude = exclude or set()
    idx = Index(g)
    scope = g.scope
    terms = [t for t in g.structured_terms if t.status in ACTIVE]
    active = {t.name for t in terms}
    ch = children_of(g, idx)
    out = [f"// {g.path.name} の構造から ontology.py が生成。手で編集しない。",
           "// fact のラベルは用語集の項目に対応する。", ""]
    facts = []  # (label, body, comment)

    def ok(name):
        t = idx.resolve(name)
        return t if t and t.name in active else None

    fields_of = {}
    for r in g.relations:
        ft, tt = ok(r.frm), ok(r.to)
        if r.status in ACTIVE and ft and tt:
            fields_of.setdefault(ft.name, []).append(f"{r.name}: set {alloy_name(tt)}")

    for t in terms:
        name = alloy_name(t)
        parents = [p for p in (ok(x) for x in t.lst("is-a")) if p]
        fl = fields_of.get(t.name, [])
        body = "{ " + ", ".join(fl) + " }" if fl else "{}"
        out.append(f"// {t.name} [{t.kind}, {t.status}]: {t.definition[:100]}")
        if parents:
            out.append(f"sig {name} in {alloy_name(parents[0])} {body}")
            for p in parents[1:]:
                facts.append((f"isa_{_cid(name)}_{_cid(alloy_name(p))}", f"{name} in {alloy_name(p)}", f"{t.name} は {p.name} の一種"))
        else:
            out.append(f"sig {name} {body}")
        for d in t.lst("disjoint"):
            dt = ok(d)
            if dt:
                a, b = sorted([name, alloy_name(dt)])
                lbl = f"disj_{_cid(a)}_{_cid(b)}"
                if lbl not in {f[0] for f in facts}:
                    facts.append((lbl, f"no {a} & {b}", f"{t.name} と {dt.name} は排他"))
        for key in DISJOINT_SETS:
            for n, grp in enumerate(t.groups(key), 1):
                ks = [alloy_name(k) for k in (ok(x) for x in grp) if k]
                if len(ks) >= 2:
                    facts.append((f"{key.split('-')[0]}{n}_disj_{_cid(name)}",
                                  " and ".join(f"no {a} & {b}" for i, a in enumerate(ks) for b in ks[i + 1:]),
                                  f"{t.name} の {key}: {'・'.join(grp)} は互いに排他"))
        for key in COVERING_SETS:
            for n, grp in enumerate(t.groups(key), 1):
                ks = [alloy_name(k) for k in (ok(x) for x in grp) if k]
                if ks:
                    facts.append((f"{key}{n}_cover_{_cid(name)}", f"{name} = " + " + ".join(ks),
                                  f"{t.name} の {key}: {'・'.join(grp)} で網羅される"))

    for r in g.relations:
        ft, tt = ok(r.frm), ok(r.to)
        if r.status not in ACTIVE or not ft or not tt:
            continue
        tag = _cid(r.id or r.name)
        if r.mult != "set":
            facts.append((f"mult_{tag}", f"all x: {alloy_name(ft)} | {r.mult} x.{r.name}",
                          f"{r.id}: 各 {ft.name} の {r.name} 先の {tt.name} は {r.mult}"))
        if r.inverse != "set":
            facts.append((f"inv_{tag}", f"all y: {alloy_name(tt)} | {r.inverse} {r.name}.y",
                          f"{r.id}: 各 {tt.name} を {r.name} する {ft.name} は {r.inverse}"))

    for ax in g.section("axioms"):
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

    add_run("consistency", "", "sat", "構造と公理の全体に少なくとも 1 つのモデルがある（無矛盾）")
    for t in terms:
        add_run(f"inhabited_{_cid(alloy_name(t))}", f"some {alloy_name(t)}", "sat", f"{t.name} が実例を持ちうる", t.line)
    for r in g.relations:
        if r.status in ACTIVE and ok(r.frm) and ok(r.to):
            add_run(f"used_{_cid(r.id or r.name)}", f"some {r.name}", "sat",
                    f"関係 {r.id}（{r.name}）が成り立ちうる", r.line, "warning")
    for pr in sorted(declared_overlaps(g, idx), key=lambda p: sorted(p)):
        a, b = sorted(pr)
        ta, tb = ok(a), ok(b)
        if ta and tb:
            add_run(f"overlap_{_cid(alloy_name(ta))}_{_cid(alloy_name(tb))}", f"some {alloy_name(ta)} & {alloy_name(tb)}", "sat",
                    f"重なりうると書いた {a} と {b} が実際に重なりうる", ta.line)
    for c in g.section("checks"):
        if c.alloy and c.get("status", "confirmed") in ACTIVE:
            nm = f"check_{_cid(c.ident)}"
            cmds.append(Command(nm, "check", "unsat", f"帰結 {c.title} が公理から導かれる", c.line))
            out += [f"assert {nm} {{\n  {c.alloy}\n}}", f"check {nm} for {c.get('scope') or scope}"]
    for s in g.section("scenarios"):
        if s.alloy and s.get("status", "confirmed") in ACTIVE:
            add_run(f"case_{_cid(s.ident)}", s.alloy, "sat" if s.get("expect") == "possible" else "unsat",
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


def unsat_core(g, jar, cmd: Command, labels, workdir):
    """削除法で、cmd を充足不能にしている fact の極小集合を求める。"""
    removed = set()
    for lbl in labels:
        src, _, _, _ = generate_alloy(g, exclude=removed | {lbl})
        try:
            res = run_alloy(jar, src, workdir / "core", command=cmd.name)
        except AlloyError:
            continue
        if not res.get(cmd.name, True):
            removed.add(lbl)
    return [l for l in labels if l not in removed]


def verify_alloy(g: Glossary, explain=True, keep=None):
    F = []
    try:
        jar = find_jar()
    except Exception as e:  # noqa: BLE001
        return [Finding("error", "ALLOY-SETUP", f"Alloy の jar を用意できない: {e}")], None
    src, cmds, labels, comments = generate_alloy(g)
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
            F.append(Finding(c.severity, "UNSAT", f"{c.purpose} はずが充足不能（全体が矛盾しているため。先に consistency を直す）", c.line))
        else:
            msg = f"{c.purpose} はずが充足不能"
            if explain:
                core = unsat_core(g, jar, c, labels, work)
                msg += ("。衝突している制約:\n" + "\n".join(f"      - {l}: {comments[l]}" for l in core)) if core \
                    else "（_上位_ と、最上位の語どうしが排他という前提だけで矛盾している）"
            F.append(Finding(c.severity, "UNSAT", msg, c.line))
    return F, work


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
    for name in ("lint", "scan", "alloy", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("glossary", help="用語集（CONTEXT.md）のパス")
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
    g = parse(Path(a.glossary))
    if a.cmd == "lint":
        return report(a.glossary, lint(g), a.verbose, a.json)
    if a.cmd == "scan":
        return report(a.glossary, scan(g, a.paths), True, a.json)
    if a.cmd == "alloy":
        src = generate_alloy(g)[0]
        if a.output:
            Path(a.output).write_text(src, encoding="utf-8")
        else:
            sys.stdout.write(src)
        return 0
    findings = lint(g)
    if (a.mode or g.mode) == "alloy":
        if any(f.level == "error" for f in findings):
            findings.append(Finding("error", "SKIP", "lint の error があるので Alloy の検証は走らせていない"))
        else:
            fs, work = verify_alloy(g, explain=not a.no_explain, keep=a.keep)
            findings += fs
            if a.keep and work:
                print(f"Alloy モデル: {work / 'model.als'}", file=sys.stderr)
    return report(a.glossary, findings, a.verbose, a.json)


if __name__ == "__main__":
    sys.exit(main())
