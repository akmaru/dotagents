# clear-writing

読者が読み返さずに論理を追える文章を書くための規則と例をまとめたスキル。用語の定義、主語・目的語・
比較対象の省略、平文と式の使い分け、根拠の添え方、未確認の事項の扱いを扱う。

dotagents では、規則のうち毎回の返答に効かせたい核を `user/AGENTS.md` の Communication Style に常時置き、
詳細と例をこのスキルに分けて必要なときだけ読み込む（常時ロードされるプロンプトを小さく保つため）。
AGENTS.md と版を揃えるため、`user/install.sh` が checkout のこのディレクトリを `apm install -g` する
（[ADR 0023](../../docs/adr/0023-agents-md-dependent-skills-from-checkout.md)）。

## インストール

dotagents の `user/install.sh` を使う場合は自動で入る。単体で使う場合:

```bash
apm marketplace add akmaru/dotagents
apm install clear-writing@dotagents
```

## 使い方

報告・調査結果・設計文書・README・ADR・PR の説明など、まとまった文章を書くときに自動で起動する。
明示的に起動する場合:

```
/clear-writing
```

## スキル一覧

| スキル | 内容 |
|--------|------|
| `clear-writing` | 読み返さずに論理を追える文章を書くための規則と例 |
