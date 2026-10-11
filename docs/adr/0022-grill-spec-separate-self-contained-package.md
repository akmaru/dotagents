---
status: accepted
date: 2026-10-10
decision-makers: akmaru
---

# grill-spec を grill-with-docs と別の自己完結パッケージにする

## Context and Problem Statement

作業を「何を作るかを詰めて仕様書に残す」→「設計判断を ADR に残す」→「実装する」の順に分けたい。既存の
`grill-with-docs` は用語集と ADR を残すスキルで、後ろ 2 段の入口にあたる。前の段を担うスキル `grill-spec` の
仕様は [packages/grill-spec/docs/internal/specs/0001-grill-spec.md](../../packages/grill-spec/docs/internal/specs/0001-grill-spec.md)
（accepted）で定めた。

仕様書は「`grill-with-docs` とは別パッケージにし、`grill-with-docs` 自体は変更しない」「用語集の書式は
`grill-with-docs` の `CONTEXT-FORMAT.md` から外れない」を制約に置き、この決定を ADR にするかを設計上の論点 D1 に
回した。決めることは 2 つある。(1) `grill-with-docs` に仕様の段を足すか、別のパッケージにするか。
(2) 別にするなら、用語集の書式とリファインメント（確定前の別文脈の点検）をパッケージの中でどう持つか。

## Decision Drivers

* 仕様の段と設計の段を、別々に呼べる単位に分ける（仕様書のスコープは仕様書の出力まで）
* 任意のリポジトリに `apm install grill-spec@dotagents` / `apm install -g` で入れて動く（仕様書 AC8・AC9）
* 用語集は `grill-with-docs` と同じ書式で書き、後段が同じ用語集を読める（仕様書 AC4・AC19）
* dotagents の個人設定（`user/agents/` の役割）が無い環境でもリファインメントが動く
* ユーザーの委譲の規則（役割は名前で指示したときだけ起動する。`user/AGENTS.md` の Delegation 節）を崩さない
* 長い grill の終盤で行うリファインメントの指示が、コンテキストの圧縮で落ちない
* 仕組みと検査を増やしすぎない

## Considered Options

1. `grill-with-docs` に仕様の段（モード）を足す
2. 別パッケージにし、`grill-with-docs` を APM の依存にして `CONTEXT-FORMAT.md` を参照する
3. 別パッケージにし、必要なものをすべて同梱する（自己完結）
    - 3.1. リファインメントは汎用のサブエージェントで行い、観点と報告の書式を同梱の手順ファイルに置く
    - 3.2. 観点を持つエージェント定義 2 つをパッケージに同梱し、名前で呼ぶ
    - 3.3. dotagents の `reviewer` / `critic` 役割を使う
4. 別パッケージにし、`SKILL.md` 1 ファイルに書式も手順も書く

1 と 2〜4 は「段を分けるか」で、2〜4 は「書式とリファインメントをどこに持つか」で分かれる。

## Decision Outcome

選択: **3.1. 別の自己完結パッケージにし、リファインメントは汎用のサブエージェント + 同梱の手順ファイルで行う**
（段を分けたまま、どの環境でも依存なしで動き、委譲の規則とも衝突しない）。

- パッケージは `packages/grill-spec/` に置き、`.apm/skills/grill-spec/` に次の 4 ファイルを同梱する
  （[ADR 0002](0002-apm-standard-marketplace-layout.md)）。APM の依存は持たない（`dependencies.apm: []`）。
  - `SKILL.md`: 手順の本体
  - `SPEC-FORMAT.md`: 仕様書の書式（節の順・ID・status・決まり文句の対訳）
  - `CONTEXT-FORMAT.md`: `grill-with-docs` の同名ファイルと**バイト一致のコピー**。変えるときは `grill-with-docs`
    側を直してコピーし直す
  - `REFINEMENT.md`: リファインメントの手順（観点と報告の書式の固定文、渡すもの、振り分けの条件）。リファインメントの
    直前に読み込む
- リファインメントは `general-purpose` のサブエージェントを 2 つ並列に起動し、`REFINEMENT.md` の観点の固定文を
  依頼文に入れる。報告はサブエージェントに書かせず、メインが受け取って作業ディレクトリに保存する
- `grill-with-docs` は変更しない

### Consequences

* Good: 仕様の段だけを単独で入れて使える。`grill-with-docs` を入れていない環境でも用語集を書ける
* Good: 役割の定義や Claude Code の追加の仕組みに頼らないので、導入直後の再起動や第二のエージェント定義の置き場が要らない
* Good: サブエージェントに書き込みをさせないので、仕様書が点検の途中で書き換わらない
* Bad: `CONTEXT-FORMAT.md` が 2 か所にあり、ずれを検査で防ぐ必要がある
* Bad: 観点の固定文を毎回の依頼文に入れるので、依頼文が長くなる
* Neutral: `grill-with-docs` が英語のリポジトリで決まり文句をどう書くかとの整合は、この決定の外に残る（仕様書のスコープ外）

### Confirmation

* `tests/test_apm.py::test_marketplace_packages_match_directories` が、`packages/` の下のディレクトリとルート
  `apm.yml` の `marketplace.packages` が一致することを検査する。`packages/grill-spec/` を登録しないと落ちる
  （2026-10-10 時点、パッケージの骨組みが未作成のためこのテストは落ちている）
* `CONTEXT-FORMAT.md` のバイト一致と同梱 4 ファイルの存在を検査するテスト（`tests/test_grill_spec.py`）は、
  実装のときに先に書く。この ADR の時点ではまだ無い

## Pros and Cons of the Options

### 1. `grill-with-docs` に仕様の段（モード）を足す

* Good: 用語集の書式と規則が 1 か所で済む
* Good: 設計の段から仕様の段に戻る道を、同じスキルの中で扱える
* Bad: `grill-with-docs` が太り、仕様の段だけを使うことができない
* Bad: 仕様書のスコープ（仕様書の出力まで）と合わない

### 2. 別パッケージにし、`grill-with-docs` を APM の依存にする

* Good: `CONTEXT-FORMAT.md` が 1 か所で済む
* Bad: `grill-spec` を入れると `grill-with-docs` も必ず入る
* Bad: marketplace 経由で推移的な依存が配備されるかを確かめていない。兄弟パッケージへのリンクはソースツリーでは解決しない

### 3. 別パッケージにし、必要なものをすべて同梱する（採用）

* Good: 確かめた配備経路（パッケージ単体の `apm install`）だけで動く
* Bad: 同梱物の一致を検査で守る必要がある

#### 3.1. 汎用のサブエージェント + 同梱の手順ファイル（採用）

* Good: 仕組みが増えない。役割の無い環境でも動く
* Good: 役割を自動で起動しないので、ユーザーの委譲の規則を崩さない
* Bad: 観点を依頼文で渡すので、仕様書 AC24 の「渡す指示」に観点と報告の書式を含めると読む必要がある（仕様 v3 で明記した）

#### 3.2. 観点を持つエージェント定義を同梱する

* Good: 観点と書式が定義に固定され、依頼文が短い
* Bad: `user/agents/` と並ぶ第二のエージェント定義の置き場ができ、ADR と検査が要る
* Bad: 導入した直後はセッションの再起動が要る。導入したすべてのセッションのエージェント一覧に 2 件載る
* Bad: 報告を書かせるには Write を許す必要があり、ツール制限で仕様書を守れない

#### 3.3. dotagents の `reviewer` / `critic` 役割を使う

* Good: 既にある役割を使える
* Bad: APM で入れただけの環境には役割が無い
* Bad: 役割を自動で起動することになり、委譲の規則に反する

### 4. `SKILL.md` 1 ファイルに書式も手順も書く

* Good: ファイルが 1 つで済む
* Bad: 本文が長くなり、終盤のリファインメントの指示がコンテキストの圧縮で落ちる恐れがある
* Bad: `CONTEXT-FORMAT.md` との一致を機械的に確かめられない

## More Information

* 仕様: [packages/grill-spec/docs/internal/specs/0001-grill-spec.md](../../packages/grill-spec/docs/internal/specs/0001-grill-spec.md)
  の制約と D1・D5・D7
* 役割の配布と frontmatter の制約: [ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)
* 対象を Claude Code に絞った決定: [ADR 0021](0021-target-claude-code-only.md)
* 設計の判断材料は `/design` の 2 回の実行で得た（台帳と報告はバージョン管理しない作業ツリーに置いた）
* この ADR は、文書をスコープ（全体 / パッケージ）ごとに分ける未作成の仕様書（beads `dotagents-vhd`）の移行対象に含める
