# madr-writer

[MADR](https://adr.github.io/madr/) 形式で Architecture Decision Record (ADR) を書くためのスキル。設計上の
重要な決定と、却下した代替案をあわせて `docs/adr/` に残す。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install madr-writer@dotagents
```

## 使い方

スラッシュコマンドで起動する:

```
/madr-writer
```

決定を記録したいときに使う。MADR のセクション（Context and Problem Statement / Decision Drivers /
Considered Options / Decision Outcome + Consequences + Confirmation / Pros and Cons / More Information）
に沿って、番号付き Considered Options・番号を揃えた Pros and Cons 見出し・関連 ADR への相互リンクで
記述する。Confirmation は実在する検証（テスト・CI・pre-commit）と突き合わせて書く。

## スキル一覧

| スキル | 内容 |
|--------|------|
| `madr-writer` | MADR 形式で ADR を作成・レビューするスキル |
