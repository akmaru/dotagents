---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# ファイルスコープ rules は Claude 専用とする

## Context and Problem Statement

C/C++ など言語固有のコーディング指針は、対象ファイルを編集するときだけ読み込みたい（常時ロードは
コンテキストの無駄）。Claude Code は `~/.claude/rules/` 配下の `.md` を再帰的に自動ロードし、`paths:`
frontmatter でグロブに一致するファイルを開いたときだけ発火させられる。一方 OpenCode には rules
ディレクトリ機構が無い。ファイルスコープの条件ロードを cross-agent でどう扱うか。

## Decision Drivers

* 言語固有指針は該当ファイル編集時だけ効かせ、コンテキストを節約したい
* OpenCode には `paths:` 相当のファイルスコープ機構が無い（`AGENTS.md` 単一ファイルと
  `opencode.json` の `instructions` 参照のみで、frontmatter 条件ロード非対応）
* 実利の乏しい対応に工数をかけたくない（YAGNI）

## Considered Options

1. ファイルスコープ rules を Claude 専用とする
2. rules 内容を `AGENTS.md` にインライン化して両エージェントで常時ロードする
3. `opencode.json` の `instructions` で rules ファイルを参照する（無条件ロード）

## Decision Outcome

選択: **「ファイルスコープ rules（`paths:` frontmatter を持つ `user/rules/**`）は Claude 専用とする」**。

- `user/rules/` は `~/.claude/rules` にのみ symlink し、OpenCode には配置しない。
- OpenCode でも同等の指針を効かせたくなった場合は、`opencode.json` の `instructions` で参照する
  （無条件ロードになる点を許容する）ことを将来検討する。現時点では YAGNI として対象外。

### Consequences

* Good: Claude では言語固有指針がファイルを開いたときだけ発火し、コンテキストを節約できる。
* Good: rules をサブディレクトリで種別分類できる（Claude のネイティブ再帰ロードを活用）。
* Bad: OpenCode では言語固有のファイルスコープ指針は効かない（共通の `AGENTS.md` のみ）。

### Confirmation

`tests/test_user_config.py` が rules の `paths:` frontmatter を検証し、`tests/test_install.py` が
rules symlink 経由で `paths:` スコープ rule に到達できることを検証する。

## Pros and Cons of the Options

### 1. Claude 専用（採用）

* Good: Claude のファイルスコープ・サブディレクトリ機能をフル活用でき、コンテキスト効率が良い。
* Bad: OpenCode ではファイルスコープ指針が効かない。

### 2. AGENTS.md にインライン化

* Good: 両エージェントで指針が効く。
* Bad: 常時ロードになり、C/C++ 以外の作業でもコンテキストを消費する。

### 3. opencode.json の instructions で参照

* Good: OpenCode でも指針を読み込める。
* Bad: 無条件ロードで条件発火にならない。現時点で必要性が薄く YAGNI。

## More Information

関連: [ADR 0001](0001-target-claude-code-and-opencode.md)、[ADR 0004](0004-user-config-distribution-symlink-import.md)。
参考: [Claude memory docs](https://code.claude.com/docs/en/memory)、[OpenCode rules](https://opencode.ai/docs/rules/)。
