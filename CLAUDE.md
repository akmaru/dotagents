# dotagents

個人用 AI エージェントの SKILL/AGENTS をまとめた APM パッケージ。
[APM (Agent Package Manager)](https://github.com/microsoft/apm) で管理し、Claude Code と OpenCode の両方で使用できる。

## 構造

```
dotagents/
├── apm.yml              # APM パッケージマニフェスト
├── CLAUDE.md            # このファイル（Claude Code 向けプロジェクト説明）
└── skills/
    └── <name>/
        └── SKILL.md     # スキル定義（agentskills.io spec 準拠）
```

## スキルの追加

1. `skills/<name>/` ディレクトリを作成（`name` は lowercase + ハイフンのみ）
2. `skills/<name>/SKILL.md` を [agentskills.io spec](https://agentskills.io/specification) に従って作成

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
| [grill-me](skills/grill-me/SKILL.md) | プランや設計をリレントレスに質問して検証する |

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
    - akmaru/dotagents/skills/grill-me
```

### 手動インストール（Claude Code）

```bash
mkdir -p ~/.claude/skills/grill-me
cp skills/grill-me/SKILL.md ~/.claude/skills/grill-me/
```

### 手動インストール（OpenCode）

```bash
mkdir -p ~/.config/opencode/skills/grill-me
cp skills/grill-me/SKILL.md ~/.config/opencode/skills/grill-me/
```
