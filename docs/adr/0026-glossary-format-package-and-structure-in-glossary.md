---
status: accepted
date: 2026-10-13
decision-makers: akmaru
---

# 用語集の書式を glossary パッケージに 1 つだけ置き、語の構造も用語集に書く

## Context and Problem Statement

語どうしの構造（種別・上位・排他と網羅・関係・公理）を整理して検証する `ontology` パッケージを足す。構造を
どのファイルに書くか、そして用語集の書式をどのパッケージが持ち、パッケージどうしがどう依存するかを決める。

これまで用語集の書式 `CONTEXT-FORMAT.md` は `grill-with-docs` にあり、`grill-spec` はそのバイト一致のコピーを
同梱していた（[ADR 0022](0022-grill-spec-separate-self-contained-package.md)）。用語集の置き場は `project-layout`
が定める（[ADR 0024](0024-new-project-standard-layout.md)、[ADR 0025](0025-project-layout-knowledge-skill.md)）。

## Decision Drivers

* 語を読むとき、定義と構造の間でファイルを行き来しない
* 定義（「当事者のうち、注文を出したもの」）と構造（上位: 当事者）は同じことの言い換えなので、2 か所に分けて
  ずれる余地を作らない
* 用語集を扱うパッケージは、インストールしたときに書式のファイルも使える
* 書式のファイルは 1 つだけにする（SSOT）
* `ontology` を入れていない環境でも、`grill-with-docs` / `grill-spec` は今までどおり動く
* 確かめた配備経路（1 段の相対パスの依存。ADR 0025）だけに頼る

## Considered Options

構造の置き場:

1. 用語集とは別の `ONTOLOGY.md` に書く（PR #47 の最初の版）
2. 用語集（`CONTEXT.md`）に書く。語ごとの構造は定義のすぐ下の行に、語にまたがる命題は後半の節に
3. 2 ファイルのまま、両方から読み物を生成する

書式の持ち方:

* A. コピーを 3 つ（`grill-with-docs` / `grill-spec` / `ontology`）に増やし、一致を検査で守る
* B. 参照専用のパッケージ `glossary` に 1 つだけ置き、用語集を扱うパッケージが直接依存する
* C. `ontology` に置き、`grill-with-docs` / `grill-spec` が `ontology` に依存する
* D. `project-layout` に置く

## Decision Outcome

選択: **2 と B**（行き来とずれが無くなり、書式が 1 か所になり、どのパッケージも単体で入れて書式を使える）。

- 用語集の書式は `packages/glossary/.apm/skills/glossary/CONTEXT-FORMAT.md` だけに置く。語の定義と `_使わない_`
  に加え、構造の行（`_種別_` / `_上位_` / `_分割_` / `_排他な下位_` / `_網羅する下位_` / `_重なりうる下位_` /
  `_網羅_` / `_排他_` / `_重なりうる_` / `_状態_` / `_コード_` / `_ID_`）と、語にまたがる節（関係・公理・帰結・
  事例・未決事項・対象外）、`CONTEXT-MAP.md` の中身の書式を持つ。置き場（単一か複数のコンテキストかの推定を
  含む）は `project-layout` に移した
- 依存（すべて相対パス）:

  | パッケージ | 依存 |
  |---|---|
  | `glossary` | なし |
  | `project-layout` | なし |
  | `grill-with-docs` | `../project-layout`、`../glossary` |
  | `grill-spec` | `../glossary` |
  | `ontology` | `../project-layout`、`../glossary` |
  | `init-project` | `../project-layout`（変更なし。`CONTEXT.md` を作らないので書式は要らない） |

  用語集を扱うパッケージは `glossary` に**直接**依存する。ADR 0025 で確かめたのは 1 段の相対パスの依存までで、
  間接の依存が配備されるかは確かめていない
- 書く分担: 語の定義と `_使わない_` は語を決めたスキル（`grill-with-docs` / `grill-spec`）が、構造は `ontology`
  が書く。構造を書かないスキルは構造の行と節を消さずに残し、語を改名したら参照も書き換え、構造を持つ語の
  定義を変えたら終わりのまとめで知らせる（`glossary` の SKILL.md）
- ADR 0022 のうち「`grill-spec` が `CONTEXT-FORMAT.md` のバイト一致のコピーを同梱し、依存を持たない」部分は
  この ADR で置き換える。`grill-spec` を `grill-with-docs` と別のパッケージにする決定はそのまま

### Consequences

* Good: 語を 1 つ読めば定義と構造が分かる。`ontology` の lint は、定義が上位の語に触れていないこと（`GENUS`）を
  検出できる
* Good: 書式を変えるときに直すファイルが 1 つ
* Good: `grill-spec` を入れても `grill-with-docs` や `ontology`（Alloy の道具）は入らない
* Bad: 用語集が長くなり、読み込みの量が増える（構造は省略できるので、書いた分だけ）
* Bad: パッケージが 1 つ増え、`grill-spec` は依存を持つようになる
* Neutral: `grill-spec` の仕様書（`0001-grill-spec.md`）の AC19 と制約は「`grill-with-docs` の
  `CONTEXT-FORMAT.md` の書式に従う」と書いている。書式の中身は同じ規則を含み、意図（後段が同じ用語集を読める）は
  保たれるが、文言は改訂が要る（未作成の仕様書の改訂として残す）

### Confirmation

* `tests/test_glossary.py` が、`packages/` の下の `CONTEXT-FORMAT.md` が `glossary` の 1 つだけであること、
  スキルのファイルで `CONTEXT.md` に触れているパッケージ（置き場だけを知る `project-layout` / `init-project` を
  除く）がすべて `../glossary` に直接依存し、SKILL.md で `glossary` スキルを参照することを検査する。
  パッケージを足したときの依存の書き漏れも、この検索で見つかる
* `tests/test_e2e_marketplace.py` が、ローカルの marketplace から `grill-spec` を入れたとき `glossary` の書式が
  隣に入ること、GitHub の marketplace から `grill-spec` / `grill-with-docs` / `ontology` を入れたとき（両スコープ）
  `glossary` が同じコミットから隣に入ることを確かめる
* `tests/test_ontology.py` が、構造を書いた用語集の例を lint と Alloy で検証する

## Pros and Cons of the Options

### 1. 別の `ONTOLOGY.md` に書く

* Good: 用語集が短いまま。既存の書式に手を入れない
* Bad: 語を読むたびに 2 つのファイルを行き来する
* Bad: 定義と構造が同じことを 2 か所で言い、ずれる

### 2. 用語集に書く（採用）

* Good: 行き来が無く、定義と構造のずれを lint で見つけられる
* Bad: 書式を共有する全パッケージに影響する

### 3. 2 ファイルから読み物を生成する

* Good: 原本はそれぞれ短い
* Bad: 生成物がもう 1 つ増え、どれが正かが分かりにくい。ずれは残る

### A. コピーを 3 つにする

* Good: 依存が増えない
* Bad: SSOT にならない。一致の検査が 3 者分になる

### B. 参照専用のパッケージ `glossary`（採用）

* Good: 書式が 1 か所。どのパッケージも単体で入れて書式を使える
* Good: `project-layout`（ADR 0025）と同じ形で、確かめた配備経路に乗る
* Bad: パッケージが 1 つ増える

### C. `ontology` に置く

* Good: パッケージが増えない
* Bad: `grill-spec` を入れると、構造の道具と Alloy の手順まで入り、スキルの一覧にも載る

### D. `project-layout` に置く

* Good: 用語集を扱うパッケージの多くが既に依存している
* Bad: `project-layout` は置き場の知識であって、文書の中身の書式ではない（ADR 0025 の範囲を広げる）
* Bad: `grill-spec` は `project-layout` に依存していない

## More Information

* 置き場の決め方を `grill-spec` でも `project-layout` に寄せるかは、この ADR の外に残した（`grill-spec` は
  「共通」のコンテキストの判定を自分で持っており、寄せるにはそれを `project-layout` に移す必要がある）
* 構造の書き方と検証: `packages/ontology/`（[README](../../packages/ontology/README.md)）
