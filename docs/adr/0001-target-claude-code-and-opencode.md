---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# Claude Code と OpenCode の両方をターゲットにする

## Context and Problem Statement

個人用の AI エージェント設定（スキル・グローバルプロンプト・rules）を、単一のエージェントに縛られず
複数のツールで使い回したい。実際にメインで Claude Code、併用で OpenCode を使っている。

ツールごとに独自形式の設定を二重管理するとドリフトし、片方だけ更新される事故が起きる。どのツールを
第一級のターゲットとし、設定をどの形式で記述するか。

## Decision Drivers

* 同じスキル・プロンプトを複数ツールで再利用したい
* 二重管理によるドリフトを避けたい
* [agentskills.io spec](https://agentskills.io/specification) が複数クライアント間で共有できる `SKILL.md` を定義している
* ツール固有機能（例: Claude の `paths:` ファイルスコープ rules）は失いたくない

## Considered Options

1. Claude Code のみをターゲットにする
2. Claude Code と OpenCode の両方をターゲットにする
3. 抽象レイヤーを自作して任意ツールへ変換する

## Decision Outcome

選択: **「Claude Code と OpenCode の両方をターゲットにする」**。

- スキルは agentskills.io spec 準拠の `SKILL.md` で記述し、両ツールが読める形にする。
- ユーザーレベル設定も両対応させる（`AGENTS.md` を正典とする → [ADR 0005](0005-agents-md-canonical.md)）。
- 一方にしか無い機能は、そのツール専用として切り出す（[ADR 0006](0006-file-scoped-rules-claude-only.md)）。

### Consequences

* Good: 記述が cross-tool 互換になり、両ツールで同じ設定が効く。
* Good: このリポジトリ全体の基盤制約となり、後続判断（[ADR 0004](0004-user-config-distribution-symlink-import.md)
  ・[ADR 0005](0005-agents-md-canonical.md)・[ADR 0006](0006-file-scoped-rules-claude-only.md)）の前提を与える。
* Bad: 片方専用の構文・パスを共有ファイルに混ぜられない制約が生じる。
* Bad: ツール固有機能はツールごとに分離が必要で、設定が完全に一元化はできない。

### Confirmation

各ツールで実際に設定がロードされることを確認する（Claude: `/context`、OpenCode: 起動して挙動確認）。
スキル構造は `tests/test_skills.py` が agentskills.io spec 準拠を検証する。

## Pros and Cons of the Options

### 1. Claude Code のみ

* Good: 実装が単純。Claude ネイティブ機能をフル活用できる。
* Bad: OpenCode で同じ設定が使えず、要求（複数ツール併用）を満たさない。

### 2. Claude Code と OpenCode の両方（採用）

* Good: 併用ツールの双方で設定を共有できる。
* Good: agentskills.io / `AGENTS.md` という既存の共有規約に乗れる。
* Bad: cross-tool 互換の制約と、ツール固有部分の分離コストがかかる。

### 3. 抽象レイヤーを自作

* Good: 理論上は任意ツールへ拡張できる。
* Bad: 過剰。YAGNI。メンテコストが高く、対象は実質2ツールで足りる。

## More Information

このリポジトリの初期設定時（APM マーケットプレイスとしての立ち上げ）からの前提を遡って記録したもの。
関連: [ADR 0002](0002-apm-standard-marketplace-layout.md)（配布に APM を採用）。
