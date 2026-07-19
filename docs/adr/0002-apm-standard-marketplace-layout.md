---
status: accepted
date: 2026-07-19
decision-makers: akmaru
---

# APM を採用し標準マーケットプレイス構成を用いる

## Context and Problem Statement

スキル/エージェント群を配布・再利用可能にする仕組みが必要。初期は独自の `plugin.json` ベースで
構成していたが、パッケージの配布方式が定まっておらず、`apm install` 時に一部プリミティブが配布
されないなどの不安定さがあった。どのパッケージマネージャ／ディレクトリ構成を採るか。

## Decision Drivers

* `apm pack` / `apm install` が安定して primitives を配布できること
* 参照リポジトリ（他の APM マーケットプレイス）と同じレイアウトに揃えたい
* 実運用で **primitives をパッケージルート直下に置くと `apm install` 時に黙って欠落する**問題を確認
* 新パッケージ追加手順を定型化したい

## Considered Options

1. 独自 `plugin.json` ベースの構成を続ける
2. APM の標準マーケットプレイス構成に移行する
3. パッケージマネージャを使わず手動 symlink / コピーで配布する

## Decision Outcome

選択: **「APM の標準マーケットプレイス構成に移行する」**。

- パッケージ単位は `packages/<name>/`。各パッケージに `apm.yml`（`includes: auto`）を置く。
- primitives は必ず `.apm/<type>/` 配下に置く（例: `.apm/skills/<name>/SKILL.md`）。
- ルート `apm.yml` は marketplace マニフェスト（`marketplace:` ブロック）とし、自己インストールは廃止。
- 外部プラグイン（例: `skill-creator`）は `git-subdir` + ref pin で登録する。

構成例:

```
dotagents/
├── apm.yml                          # marketplace: マニフェスト（source of truth → ADR 0003）
├── .claude-plugin/marketplace.json  # apm pack で生成（コミット対象 → ADR 0003）
├── packages/
│   └── <name>/
│       ├── apm.yml                  # パッケージマニフェスト（includes: auto）
│       ├── README.md
│       ├── LICENSE
│       └── .apm/                    # primitives は必ずこの配下
│           └── skills/<name>/SKILL.md
└── tests/                           # 構造検証（test_apm.py / test_skills.py / test_marketplace_json.py）
```

### Consequences

* Good: `apm pack` / `apm install` が `.apm/` 配下を確実に配布できる。
* Good: 新パッケージ追加手順が定型化される（README の "Adding a skill"）。
* Bad: `.apm/<type>/` 必須という非自明な制約を守る必要がある（`CLAUDE.md` に明記）。
* Neutral: 個人ユーザー設定（`user/`）はこの構成に載せず別方式で配布する
  （[ADR 0004](0004-user-config-distribution-symlink-import.md)）。

### Confirmation

`tests/test_apm.py`（各 `packages/*/apm.yml` の必須フィールド・ディレクトリ整合）と
`tests/test_skills.py`（`.apm/skills/*` の spec 準拠）で構造を検証する。

## Pros and Cons of the Options

### 1. 独自 `plugin.json` ベース

* Good: 既存の実装をそのまま使える。
* Bad: 配布挙動が APM 標準と噛み合わず、primitives 欠落などの不安定さが残る。

### 2. APM 標準マーケットプレイス構成（採用）

* Good: `apm pack`/`install` の挙動が安定し、参照リポジトリと整合する。
* Good: パッケージ追加・依存解決・外部プラグイン取り込みが APM の作法に乗る。
* Bad: `.apm/<type>/` 配下必須という落とし穴を意識し続ける必要がある。

### 3. 手動 symlink / コピー

* Good: 仕組みが単純で依存が無い。
* Bad: 依存解決・バージョニング・他リポジトリからの再利用ができず、マーケットプレイスにならない。

## More Information

既存決定を遡って記録したもの。source of truth の置き場所は [ADR 0003](0003-marketplace-source-of-truth.md)
で別途固定する。
