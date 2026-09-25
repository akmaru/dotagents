# dotagents

個人用 AI エージェントの SKILL/AGENTS をまとめた APM マーケットプレイス。
[APM (Agent Package Manager)](https://github.com/microsoft/apm) で管理し、Claude Code で使用する。

## 構造

標準の APM マーケットプレイス構成に従う。

```
dotagents/
├── apm.yml                          # marketplace: マニフェスト
├── .claude-plugin/marketplace.json  # apm pack で生成（コミット対象）
├── CLAUDE.md                        # このファイル（Claude Code 向けプロジェクト説明）
├── packages/
│   └── <name>/
│       ├── apm.yml                  # パッケージマニフェスト
│       ├── README.md
│       ├── LICENSE
│       └── .apm/skills/<name>/SKILL.md  # スキル定義（agentskills.io spec 準拠）
├── user/                            # 個人ユーザースコープ設定（非 APM・symlink 配布）
│   └── agents/<role>.md             # 役割定義（researcher / designer / critic）。~/.claude/agents/ へファイル単位 symlink
└── docs/adr/                        # Architecture Decision Records
```

各プリミティブは必ず `.apm/<type>/` 配下に置くこと。パッケージルート直下に置くと `apm pack` は通るが `apm install` 時に黙って欠落する。

`user/` は marketplace とは別概念の個人ユーザーレベル設定（グローバルプロンプト・rules・settings・herdr 設定）で、`apm compile` ではなくネイティブ symlink で `~/.claude` / `~/.config/herdr` へ配布する（`settings.json` のみ、マシン固有のキーを残すため symlink ではなく jq マージ）。詳細は [docs/adr/](docs/adr/) 参照。

## スキルの追加

1. `packages/<name>/` を作成（`name` は lowercase + ハイフンのみ）
2. `packages/<name>/.apm/skills/<name>/SKILL.md` を [agentskills.io spec](https://agentskills.io/specification) に従って作成

```markdown
---
name: <name>
description: <何をするか、いつ使うかを 1024 文字以内で>
compatibility: Designed for Claude Code  # 必要な場合のみ
---

## スキルの指示（Markdown）
```

3. `packages/<name>/apm.yml`（name / version / description / author / license / `includes: auto`）を作成。`name` はディレクトリ名・スキルディレクトリ名と一致させること
4. ルート `apm.yml` の `marketplace.packages` にエントリを追加し、`apm pack` で `.claude-plugin/marketplace.json` を再生成する

## スキル一覧

| スキル | 説明 |
|--------|------|
| [grill-me](packages/grill-me/.apm/skills/grill-me/SKILL.md) | プランや設計をリレントレスに質問して検証する |
| [grill-with-docs](packages/grill-with-docs/.apm/skills/grill-with-docs/SKILL.md) | リポジトリの中でラウンド形式に問い詰めつつ、用語を `CONTEXT.md`、戻しにくい決定を ADR（MADR）にその場で書き残す |
| [beads](packages/beads/.apm/skills/beads/SKILL.md) | タスクごとに beads issue を作成・更新・クローズするワークフロー |
| [rust](packages/rust/.apm/skills/rust/SKILL.md) | rust-analyzer LSP を用いた Rust 開発ワークフロー |
| [madr-writer](packages/madr-writer/.apm/skills/madr-writer/SKILL.md) | MADR 形式で ADR を作成・レビューするスキル |
| [refine-design](packages/refine-design/.apm/skills/refine-design/SKILL.md) | 設計判断を代替案・トレードオフ・既存決定との整合で審議・リファインするスキル |
| [context-budget](packages/context-budget/.apm/skills/context-budget/SKILL.md) | コンテキスト使用量を計測し、削減候補を提案・適用・再計測するスキル（計測は `user/bin/claude-context.py`） |
| [workflow-graph](packages/workflow-graph/.apm/skills/workflow-graph/SKILL.md) | 作業を 3 つの SCC のグラフとして回すメインセッション向けの規約（ワークフロー本体は `user/workflows/`、hook は `user/bin/`） |

## 役割（サブエージェント）

`user/agents/` の役割定義をメインセッションが委譲先として使う（[ADR 0014](docs/adr/0014-agent-roles-dual-key-per-file-symlink.md)）。
frontmatter は Claude Code のフィールドを自由に書けるが、`disallowedTools` に `Edit` / `Write` / `NotebookEdit` /
`Agent` を必ず含め、`permissionMode` は書かない（[ADR 0014](docs/adr/0014-agent-roles-dual-key-per-file-symlink.md)
の独立した理由）。委譲の指示は `user/AGENTS.md` の Delegation 節。

| 役割 | 用途 |
|------|------|
| [researcher](user/agents/researcher.md) | 仕様・一次情報・実現可能性を出典付きで調べる |
| [designer](user/agents/designer.md) | 代替案とトレードオフを整理し推奨案を出す |
| [critic](user/agents/critic.md) | 別文脈から反対の立場で成果物を検証する |
| [verifier](user/agents/verifier.md) | 検証項目を実行し、fail の原因を「実装 / 設計の前提」で分類する |
| [reviewer](user/agents/reviewer.md) | 差分を決定との整合・正しさ・テストの観点で読み、file:line 付きで指摘する |
| [explainer](user/agents/explainer.md) | herdr の固定 pane に常駐する解説役（[設計書](docs/design/explainer-pane.md)） |

## ワークフローグラフ

作業全体を 3 つの強連結成分（deliberate / build / review）としてモデル化し、各 SCC は台帳 1 枚と
「再発」による離脱条件を持つ（[ADR 0018](docs/adr/0018-workflow-graph-three-sccs.md)）。
SCC の内側は保存ワークフロー `/deliberate` `/build` `/review`（`user/workflows/*.js`、`install.sh` が
`~/.claude/workflows/` へ symlink）が回し、人間ノードと SCC 間は `workflow-graph` skill に従って
メインセッションが担い、抜ける条件は hook（`user/bin/workflow-graph-guard.sh`）が守る
（[ADR 0020](docs/adr/0020-workflow-graph-control-flow.md)）。
機構と運用は [docs/design/workflow-graph.md](docs/design/workflow-graph.md)、
図は [docs/design/workflow-graph.drawio](docs/design/workflow-graph.drawio)。

## 利用方法

### APM Marketplace 経由（推奨）

```bash
apm marketplace add akmaru/dotagents
apm install grill-me@dotagents
```

### APM 依存関係として追加（他リポジトリの apm.yml）

```yaml
dependencies:
  apm:
    - akmaru/dotagents/packages/grill-me
```

### 手動インストール（Claude Code）

```bash
mkdir -p ~/.claude/skills/grill-me
cp packages/grill-me/.apm/skills/grill-me/SKILL.md ~/.claude/skills/grill-me/
```

<!-- br-agent-instructions-v1 -->

---

## Beads Workflow Integration

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`/`bd`) for issue tracking. Issues are stored in `.beads/` and tracked in git.

### Essential Commands

```bash
# View ready issues (open, unblocked, not deferred)
br ready              # or: bd ready

# List and search
br list --status=open # All open issues
br show <id>          # Full issue details with dependencies
br search "keyword"   # Full-text search

# Create and update
br create --title="..." --description="..." --type=task --priority=2
br update <id> --status=in_progress
br close <id> --reason="Completed"
br close <id1> <id2>  # Close multiple issues at once

# Sync with git
br sync --flush-only  # Export DB to JSONL
br sync --status      # Check sync status
```

### Workflow Pattern

1. **Start**: Run `br ready` to find actionable work
2. **Claim**: Use `br update <id> --status=in_progress`
3. **Work**: Implement the task
4. **Complete**: Use `br close <id>`
5. **Sync**: Always run `br sync --flush-only` at session end

### Key Concepts

- **Dependencies**: Issues can block other issues. `br ready` shows only open, unblocked work.
- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4, not words)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Blocking**: `br dep add <issue> <depends-on>` to add dependencies

### Session Protocol

**Before ending any session, run this checklist:**

```bash
git status              # Check what changed
git add <files>         # Stage code changes
br sync --flush-only    # Export beads changes to JSONL
git commit -m "..."     # Commit everything
git push                # Push to remote
```

### Best Practices

- Check `br ready` at session start to find available work
- Update status as you work (in_progress → closed)
- Create new issues with `br create` when you discover tasks
- Use descriptive titles and set appropriate priority/type
- Always sync before ending session

<!-- end-br-agent-instructions -->
