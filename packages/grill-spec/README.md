# grill-spec

リポジトリの中で「何を・なぜ作るか」を問い詰め、課題・ユーザーストーリー・ユーザージャーニー・受け入れ
基準・スコープ外・制約・設計上の論点を持つ仕様書に**その場で**書き残すスキル。共通理解に至っても即座には
確定せず、既定では会話の履歴を持たない別文脈のリファインメント（整合の観点 / 反対の立場の観点の 2 本）を
挟んでから確定（accepted）する。

## `grill-with-docs` との住み分け

- `grill-spec`: 「何を・なぜ作るか」を問い詰め、**仕様書**（`docs/internal/specs/` など）に残す。設計判断や
  実装方法そのものには踏み込まず、出典付きの制約か設計上の論点に振り分けるだけ
- `grill-with-docs`: 設計判断・実装方法を問い詰め、用語集（`CONTEXT.md`）と ADR に残す

`grill-spec` が出す accepted の仕様書が、後段（設計判断 → ADR → 実装）の入力になる。用語集の書式は両スキル
で共通で、どちらも `glossary` パッケージの `CONTEXT-FORMAT.md` を参照する。`grill-spec` が依存するのは
`glossary` だけで、`grill-with-docs` を入れていない環境でも動く。

## インストール

プロジェクトスコープ:

```bash
apm marketplace add akmaru/dotagents
apm install grill-spec@dotagents
```

ユーザースコープ（任意のリポジトリで使えるようにする）:

```bash
apm marketplace add akmaru/dotagents
apm install -g grill-spec@dotagents
```

## 使い方

```
/grill-spec <作りたい機能の要望>              # 新しい仕様書を起こす
/grill-spec <仕様書のパス>                    # draft / revising の続きから始める
/grill-spec <仕様書のパス> <変えたい点>        # accepted の仕様書を改訂する
```

セッションから出てくるもの:

| 決まったもの | 行き先 |
|---|---|
| 課題・ストーリー・ジャーニー・受け入れ基準・スコープ外 | 仕様書（決まった瞬間にその場で） |
| プロジェクト固有の用語 | 用語集（`CONTEXT.md` など。決まった瞬間にその場で） |
| 実装の技術選定・内部構造・実装手順の発言 | 仕様書の制約（出典が要る）か設計上の論点 |
| 未回答の指摘・改訂の変えたい点・リファインメントの周回 | 台帳（`.claude/grill-spec/` 配下。バージョン管理しない） |

## 開発者向け

- 用語集の書式は `glossary` パッケージの `CONTEXT-FORMAT.md` だけにある（コピーは持たない。
  [ADR 0026](../../docs/adr/0026-glossary-format-package-and-structure-in-glossary.md)）
- 仕様書・台帳の書式は [SPEC-FORMAT.md](.apm/skills/grill-spec/SPEC-FORMAT.md)、リファインメントの手順は
  [REFINEMENT.md](.apm/skills/grill-spec/REFINEMENT.md) にある
- 仕様と、このパッケージを `grill-with-docs` と分けた決定は
  [docs/internal/specs/0001-grill-spec.md](docs/internal/specs/0001-grill-spec.md) と
  [ADR 0022](../../docs/adr/0022-grill-spec-separate-self-contained-package.md)（書式のコピーの部分は ADR 0026 で置き換えた）
