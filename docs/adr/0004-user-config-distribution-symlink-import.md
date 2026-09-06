---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# ユーザーレベル設定の配布はネイティブ symlink + @import で行う

## Context and Problem Statement

個人用のユーザーレベル設定（グローバルプロンプト・rules・settings）を dotagents に一元管理し、
Claude Code だけでなく OpenCode など他エージェントからもユーザーレベルプロンプトとして使えるように
したい（[ADR 0001](0001-target-claude-code-and-opencode.md)）。この設定群をどの方式で各エージェントの
ユーザースコープへ配布するか。

## Decision Drivers

* Claude の `~/.claude/rules/` が持つネイティブ機能（サブディレクトリ再帰・`paths:` グロブスコープ・symlink）
  を活かしたい
* 編集を即時反映したい（ビルド/生成サイクルを挟みたくない）
* cross-agent でプロンプトを共有したい
* 二重管理・ドリフトを避けたい

## Considered Options

1. APM の `apm compile --global` で各エージェントのユーザースコープファイルを生成する
2. ネイティブ symlink + `@import` で配布する
3. ツールごとに手動でコピーする

## Decision Outcome

選択: **「ネイティブ symlink + `@import`」**。

- 設定ファイル群は dotagents の `user/` に置き、`user/install.sh` が `~/.claude/` および
  `~/.config/opencode/` へ symlink する。
- Claude が `AGENTS.md` を取り込むために `@import` を用いる（[ADR 0005](0005-agents-md-canonical.md)）。

APM compile は、instructions discovery が `.apm/instructions/` を `glob("*.instructions.md")` で
**1階層のみ**走査する（`instruction_integrator.py` / `base_integrator.py` で実装確認）ためサブディレクトリ
分類ができず、Claude ネイティブ rules の能力をダウングレードさせる。また編集のたびに
「push → `apm install -g` → `apm compile --global`」のサイクルを要する。OpenCode は
`~/.config/opencode/AGENTS.md` を読み、無ければ `~/.claude/CLAUDE.md` にフォールバックするため、
cross-agent 共有に生成処理は不要。以上より symlink 方式が要件に最も合致する。

### Consequences

* Good: 編集が即時反映される（symlink のため build/compile 不要）。
* Good: Claude の rules ネイティブ機能（サブディレクトリ・`paths:`）をフルに使える。
* Bad: 各エージェントごとの配置先・形式差を install スクリプトで吸収する必要がある（自動変換は無い）。
* Neutral: dotagents は APM マーケットプレイス（`packages/`）と個人設定（`user/`）の二重用途になる。
  `user/` は marketplace 非掲載・`packages/` 外なので既存テストに影響しない。

### Confirmation

`tests/test_install.py` が一時 HOME で `install.sh` を実行し、symlink が `user/` の各ファイルを指すこと・
べき等性・stale リンク置換を検証する。実挙動は Claude の `/context` と OpenCode 起動で確認する。

## Pros and Cons of the Options

### 1. APM `apm compile --global`

* Good: 1ソースから各エージェント形式を生成でき、APM に一貫する。
* Bad: `.apm/instructions/` がフラット限定で Claude の rules サブディレクトリを再現できない。
* Bad: 生成サイクルが必要で即時反映できない。

### 2. ネイティブ symlink + `@import`（採用）

* Good: 即時反映。Claude ネイティブ機能をそのまま使える。
* Good: OpenCode の `AGENTS.md` / CLAUDE.md フォールバックにそのまま乗れる。
* Bad: エージェントごとの差異を install スクリプトで扱う。

### 3. ツールごとに手動コピー

* Good: 仕組みが最も単純。
* Bad: 複製がドリフトし、一元管理という目的に反する。

## More Information

settings.json のみ、外部ツールがマシン固有のキーを書き込むため後に symlink をやめ、
マージ方式へ変更した（[ADR 0009](0009-settings-json-merge.md)）。

関連: [ADR 0001](0001-target-claude-code-and-opencode.md)（両ツール対応の基盤制約）、
[ADR 0005](0005-agents-md-canonical.md)（AGENTS.md 正典化）、
[ADR 0006](0006-file-scoped-rules-claude-only.md)（rules は Claude 専用）。
参考: [Claude memory docs](https://code.claude.com/docs/en/memory)、[OpenCode rules](https://opencode.ai/docs/rules/)。
