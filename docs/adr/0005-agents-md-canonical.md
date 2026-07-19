---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# AGENTS.md を単一正典とし CLAUDE.md は @import する

## Context and Problem Statement

複数エージェント（Claude Code / OpenCode）で同一のグローバルプロンプトを共有したい。各エージェントが
読むファイルは異なる（Claude: `~/.claude/CLAUDE.md`、OpenCode: `~/.config/opencode/AGENTS.md`）。
同じ内容を2ファイルに複製するとドリフトする。一方で Claude 固有の指示（例: `@~/.claude/CLAUDE.work.md`
の import は Claude の機能で、他エージェントでは無意味なテキストになる）は共有ファイルに混ぜたくない。
どのファイルを正典とし、どう共有するか。

## Decision Drivers

* 共通プロンプトの複製・ドリフトを避けたい
* Claude 固有の内容を cross-agent な共有ファイルに混ぜたくない
* import のパス解決を symlink の相対解決に依存させたくない
* 既存のベストプラクティスに沿いたい

## Considered Options

1. `CLAUDE.md` と `AGENTS.md` を別々に二重管理する
2. `AGENTS.md` を正典とし `CLAUDE.md` が `@import` する
3. `CLAUDE.md` を正典とし OpenCode の CLAUDE.md フォールバックに任せる
4. 単一ファイルを両方の場所へ symlink する

## Decision Outcome

選択: **「`AGENTS.md` を正典とし `CLAUDE.md` が `@import` する」**。これは Anthropic 公式ドキュメントが
推奨するパターン（AGENTS.md を使うリポジトリでは CLAUDE.md がそれを `@import` し、下に Claude 固有指示を
追記する）である。

- 共通プロンプト本文は `AGENTS.md` にのみ書く。
- `user/CLAUDE.md` は先頭で `@~/.claude/AGENTS.md` を import し、その下に Claude 固有セクションを置く。
- Claude 固有の work import（`@~/.claude/CLAUDE.work.md`）は `CLAUDE.md` 側にのみ置く。
- import 解決を symlink の相対解決に依存させないため、`~/.claude/AGENTS.md` にも symlink を張り、絶対
  `~` パスで import する。

### Consequences

* Good: 共通プロンプトの編集は `AGENTS.md` 1ファイルで済み、両エージェントに反映される。
* Good: `AGENTS.md` に Claude 専用構文が入らないため OpenCode でノイズにならない。
* Good: OpenCode は `~/.config/opencode/AGENTS.md`（存在時は CLAUDE.md より優先）を読むため、フォール
  バックに依存せず明示的に共通プロンプトが効く。
* Bad: `~/.claude/AGENTS.md` という補助 symlink を1つ増やす。

### Confirmation

`tests/test_user_config.py` が `CLAUDE.md` に `@~/.claude/AGENTS.md` があること・work import が CLAUDE.md
側にあること・`AGENTS.md` が cross-agent クリーンであることを検証する。`tests/test_install.py` が import
先 `~/.claude/AGENTS.md` が実ファイルに解決することを検証する。

## Pros and Cons of the Options

### 1. CLAUDE.md と AGENTS.md を二重管理

* Bad: 複製がドリフトし、片方だけ更新される事故が起きる。

### 2. AGENTS.md 正典 + CLAUDE.md @import（採用）

* Good: 単一正典。公式推奨パターン。Claude 固有分を綺麗に分離できる。
* Bad: 補助 symlink が1つ増える。

### 3. CLAUDE.md 正典 + OpenCode フォールバック

* Good: ファイルが1つで済む。
* Bad: OpenCode のフォールバック挙動に暗黙依存する。AGENTS.md が正になるべき OpenCode で不自然。

### 4. 単一ファイルを両所へ symlink

* Good: 複製なしで両対応。
* Bad: Claude 固有の追記（work import）を分離できない（同一実体のため）。

## More Information

関連: [ADR 0001](0001-target-claude-code-and-opencode.md)、[ADR 0004](0004-user-config-distribution-symlink-import.md)。
参考: [Claude memory docs](https://code.claude.com/docs/en/memory)（`@import` は絶対/`~` パス可・ネスト最大4段、
AGENTS.md import 推奨パターン）。
