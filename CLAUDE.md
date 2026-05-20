# dotagents

個人用 AI エージェントの SKILL/AGENTS をまとめた APM パッケージ。
[APM (Agent Package Manager)](https://github.com/microsoft/apm) で管理し、Claude Code と OpenCode の両方で使用できる。

## 構造

```
dotagents/
├── apm.yml              # APM パッケージマニフェスト
├── CLAUDE.md            # このファイル（Claude Code 向けプロジェクト説明）
└── plugins/
    └── <name>/
        └── SKILL.md     # スキル定義（agentskills.io spec 準拠）
```

## スキルの追加

1. `plugins/<name>/` ディレクトリを作成（`name` は lowercase + ハイフンのみ）
2. `plugins/<name>/SKILL.md` を [agentskills.io spec](https://agentskills.io/specification) に従って作成

```markdown
---
name: <name>
description: <何をするか、いつ使うかを 1024 文字以内で>
compatibility: Designed for Claude Code and OpenCode  # 必要な場合のみ
---

## スキルの指示（Markdown）
```

3. `name` フィールドはディレクトリ名と一致させること

## スキル一覧

| スキル | 説明 |
|--------|------|
| [grill-me](plugins/grill-me/SKILL.md) | プランや設計をリレントレスに質問して検証する |

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
    - akmaru/dotagents/plugins/grill-me
```

### 手動インストール（Claude Code）

```bash
mkdir -p ~/.claude/skills/grill-me
cp plugins/grill-me/SKILL.md ~/.claude/skills/grill-me/
```

### 手動インストール（OpenCode）

```bash
mkdir -p ~/.config/opencode/skills/grill-me
cp plugins/grill-me/SKILL.md ~/.config/opencode/skills/grill-me/
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
