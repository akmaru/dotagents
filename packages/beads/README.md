# beads

Beads issue tracking workflow スキル。タスク着手前に beads issue を作成し、作業中に更新、完了時にクローズする運用をエージェントに徹底させる。

前提として [beads](https://github.com/Dicklesworthstone/beads_rust) の CLI（`br`/`bd`）がインストールされている必要がある。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install beads@dotagents
```

## スキル一覧

| スキル | 内容 |
|--------|------|
| `beads` | タスクごとに beads issue を作成・更新・クローズするワークフロー |
