---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# マーケットプレイスの source of truth は root apm.yml、marketplace.json は生成物

## Context and Problem Statement

`.claude-plugin/marketplace.json` は **Claude Code のプラグインマーケットプレイス機能**
（`/plugin marketplace add <repo>` / `/plugin install`）がリポジトリルートから読む発見カタログである。
これが無いと Claude Code の `/plugin` 経路でこのリポジトリのプラグインを発見・インストールできない
（APM 経由の `apm install ...@dotagents` は `apm.yml` を読むため影響しない）。したがって Claude Code
ユーザー向けにこのファイルを用意する必要がある。

問題は、同種のメタデータ（パッケージ一覧・owner・version 等）を `marketplace.json`（Claude Code 用）と
`apm.yml`（APM 用）の両方が持つ点にある。両方を独立に手で保守すると二重管理になり、片方だけ更新されて
不整合が生じる。どちらを source of truth とし、もう一方との整合をどう保つか（手編集か生成か）を決める
必要がある。

## Decision Drivers

* 二重管理と不整合を避け、パッケージの追加・変更フローを一本化したい
* APM の標準マーケットプレイス構成（[ADR 0002](0002-apm-standard-marketplace-layout.md)）と整合させたい
* `.claude-plugin/marketplace.json` を消費するのは **Claude Code のプラグインマーケットプレイス機能**
  （`/plugin marketplace add <repo>` / `/plugin install`）で、リポジトリルートのこのファイルを直接読む。
  APM 非導入の環境でもこの機能から参照できるようにしたい（OpenCode 等は `marketplace.json` を使わない）

## Considered Options

1. `marketplace.json` を手編集して source of truth にする
2. `apm.yml` を source of truth とし、`apm pack` で `marketplace.json` を生成する
    - 2.1. 生成物をコミットする（git 管理下に置く）
    - 2.2. 生成物を gitignore する（git 非管理）

1 と 2 は source of truth が `marketplace.json` か `apm.yml` かで異なる。2 を採る場合、さらに生成物を
git 管理下に置くか（2.1 / 2.2）を決める。

## Decision Outcome

選択: **「2. `apm.yml` を source of truth + `apm pack` 生成」かつ「2.1. 生成物をコミット」**。

- パッケージの追加・変更は `apm.yml` を編集し、`apm pack` で `.claude-plugin/marketplace.json` を再生成する。
- `marketplace.json` は生成物だがコミット対象とする。手編集しない。

### Consequences

* Good: 変更フローが一本化される（`apm.yml` 編集 → `apm pack`）。
* Good: 生成物をコミットするため、生成器が無い環境でも `marketplace.json` を参照できる。
* Bad: `apm.yml` を変更したら `apm pack` の再実行が要る
  * 忘れても下記 pre-commit フックが drift を検出して commit を止めるため、実害には至りにくい。
* Neutral: 生成物を版管理に含めるため、差分ノイズが出る。

### Confirmation

pre-commitにて下記を検査する。
*  `apm pack --check-clean --dry-run` で、 `apm.yml` から生成される `marketplace.json` と、現在のgit管理下にある `marketplace.json` が一致していることを検査する。

テストにて下記を検査する。
* `marketplace.json` の構造妥当性（valid JSON・必須フィールド・各ローカル source の実在）は `tests/test_marketplace_json.py` で確認する。
* `apm.yml` 自体の妥当性と、`marketplace.packages` が `packages/` ディレクトリと完全一致することは `tests/test_apm.py` で確認する。

## Pros and Cons of the Options

### 1. `marketplace.json` を手編集

* Good: Claude Code が読むファイルを直接管理でき、生成ステップが要らない。
* Bad: `apm.yml` との二重管理になり、片方だけ更新されて不整合を起こしやすい。

### 2. `apm.yml` を source of truth + `apm pack` 生成（採用）

* Good: 記述の一次情報が `apm.yml` に集約され、生成物が自動で追従する（1 の二重管理を回避）。
* Bad: `apm.yml` 変更時に `apm pack` を実行する運用規律が要る。

#### 2.1. 生成物をコミット（採用）

* Good: `apm pack` 未実行の clone でも Claude Code の `/plugin` から参照できる。
* Bad: 生成物を版管理に含めるため差分ノイズが出る。

#### 2.2. 生成物を gitignore

* Good: 版管理から生成ノイズを排除できる。
* Bad: `apm pack` 未実行の clone では `marketplace.json` が無く、Claude Code の `/plugin` 経路が使えない。

## More Information

`marketplace.json` と `apm.yml` の二重管理を避けるための決定。関連: [ADR 0002](0002-apm-standard-marketplace-layout.md)。
