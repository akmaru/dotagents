# agent-dx

エージェントを使っていて感じた利用体験の課題や、実現したいことを、その場で dotagents の GitHub Issue に起票するスキル。
`agent-dx` ラベルの付いた Issue は、GitHub Actions のエージェントがトリアージ・設計・実装を進めて PR を出す。
オーナーは PR を隔離した環境で試し、approve すると merge される
（[ADR 0027](../../docs/adr/0027-agent-dx-improvement-loop-via-github-issues.md)）。

スキル名とラベル名の `agent-dx` は仮の名前（ADR 0027 の未決事項）。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install agent-dx@dotagents
```

`gh` が akmaru/dotagents に Issue を作れる状態で認証されている必要がある。

## 使い方

作業中に `/agent-dx <一言>` と打つ。スキルが今のセッションの文脈を添えて Issue の下書きを作り、確認を取ってから起票する。
