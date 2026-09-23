# workflow-graph

作業を 3 つの強連結成分（① deliberate / ② build / ③ review）のグラフとして回すための、
メインセッション向けの規約スキル。SCC の内側は保存ワークフロー `/deliberate` `/build` `/review`
（dotagents の `user/workflows/`、`user/install.sh` が `~/.claude/workflows/` へ配布）が回し、
人間ノードと SCC 間の遷移をこのスキルに従ってメインセッションが担う。
抜ける条件は hook（`user/bin/workflow-graph-guard.sh`）が機械的に守る。

設計: `docs/adr/0018-workflow-graph-three-sccs.md`（グラフの形）、
`docs/adr/0019-workflow-graph-control-flow.md`（制御の分担）、`docs/design/workflow-graph.md`（機構）。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install workflow-graph@dotagents
```

ワークフロー本体と hook は APM パッケージではなく `user/install.sh` が配る（ADR 0019）。

## 使い方

```
/workflow-graph
```

調査・設計が要るタスクを始めるとき、決定を実装に移すとき、PR をレビューに回すときに読み込む。
