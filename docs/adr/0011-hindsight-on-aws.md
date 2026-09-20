---
status: accepted
date: 2026-09-20
decision-makers: akmaru
---

# Hindsight サーバーは AWS の EC2 1 台に Docker Compose で常駐させ、公開 HTTPS + API キーで繋ぐ

## Context and Problem Statement

[ADR 0007](0007-hindsight-setup-assets.md) で Hindsight をローカル Mac に `--daemon` で手動起動する形にしたが、
再起動・クラッシュのたびに手で上げ直す必要があり、Mac を閉じている間は他マシンから記憶を参照できない。
「消えない」「どこからでも繋がる」を満たす常駐先が要る。第一候補は AWS。

## Decision Drivers

* 記憶が消えないこと（永続ストレージとバックアップ）
* 複数のクライアント（Mac、他マシン、将来の CI）からいつでも繋がること
* 個人用途なので月額を抑えること
* 秘密（Anthropic キー・認証キー）を public リポジトリと Terraform state のどちらにも載せないこと
* dotagents は public なので、アカウント固有の情報（ドメイン全体・tfstate バケット名）を持ち込まないこと
* 既存のローカル構成（評価・開発用）を壊さないこと

## Considered Options

到達経路:

1. Tailscale で閉域
2. 公開 HTTPS + API キー（`ApiKeyTenantExtension`）
3. SSM Session Manager のポートフォワード

コンピュートと DB:

1. EC2 1 台 + Docker Compose（Postgres 同居、EBS + スナップショット）
2. ECS Fargate + RDS Postgres
3. Lightsail

ドメイン・IaC の置き場所:

1. すべて dotagents に置く
2. ドメインとアカウント基盤は private リポジトリ、Hindsight のスタックは dotagents

## Decision Outcome

選択: **公開 HTTPS + API キー**、**EC2 1 台 + Docker Compose**、**ドメインは private リポジトリ [akmaru/akmaru.dev](https://github.com/akmaru/akmaru.dev)・Hindsight は dotagents**。

* `hindsight.akmaru.dev` で公開する。TLS は Caddy が Let's Encrypt から自動取得し、認証は hindsight-api 組み込みの
  `ApiKeyTenantExtension`（`Authorization: Bearer <key>`、MCP endpoint にも効く）で行う。
  Tailscale を全クライアントに入れる手間と、SSM ポートフォワードを毎回張る手間を避けた。
* t4g.medium（4GB）に `caddy` / `hindsight-api` / `postgres (pgvector)` を Compose で同居させる。
  Postgres データはルートと別の EBS に置き、DLM で日次スナップショット（7 日保持）。
  インスタンスは `prevent_destroy` 付きのデータボリュームを再アタッチする前提で使い捨てられる。
* 秘密は SSM Parameter Store（SecureString）に Terraform 外で `put-parameter` する。Terraform は名前だけ知り、
  サーバー上の `deploy.sh` が起動時に取得して `.env` を生成する。state には載らない。
* Compose 定義はサーバーが dotagents（public）を `/opt/dotagents` に clone して使う。更新は `git pull && deploy.sh`。
* ゾーン `akmaru.dev` と tfstate バケットは akmaru.dev リポジトリが管理する。dotagents 側は
  `data "aws_route53_zone"` で名前引きして A レコードを 1 本足す。リポジトリ間の結合はゾーン名だけで、
  remote state は参照しない。バケット名・profile は `backend.hcl` / `terraform.tfvars`（gitignore）で渡す。
* ローカルの `install-server.sh` / `hindsight-start.sh` / `config.sh` は移行完了後に削除した（当初は評価・開発用に
  残す予定だったが、AWS 側で疎通とバンク移行を確認できたため同日に撤去）。
  `install-client.sh` は API キー（Keychain `hindsight-mcp-api-key` または `HINDSIGHT_MCP_API_KEY`）があれば
  ヘッダ付きのフラグメントを生成し、なければ認証なし（開発用インスタンス向け）を生成する。既定 URL は AWS 側。
* Control Plane はサーバーに置かず、`control-plane.sh` でローカルに起動して API キー付きで AWS の API に繋ぐ。

### Consequences

* Good: 再起動・クラッシュ後は `restart: unless-stopped` と docker の自動起動で復帰する。手動操作が不要になる。
* Good: 月額は t4g.medium + EBS 20GB + EIP + スナップショットで $30〜35 程度。
* Good: 将来 Postgres を RDS に移す場合は `HINDSIGHT_API_DATABASE_URL` の差し替えで済む。
* Bad: 公開エンドポイントなので API キーが漏れれば記憶を読み書きされる。キーは Keychain / SSM にのみ置き、
  漏洩時は SSM の値を差し替えて `deploy.sh` を再実行する。
* Bad: 単一 AZ・単一インスタンス。停止時は使えない（許容。記憶はスナップショットから復元できる）。
* Bad: OS パッチ・Docker の更新は自前。AL2023 の `dnf update` を定期的に SSM 経由で行う。
* Bad: user-data は初回のみ実行されるため、`user-data.sh.tftpl` の変更は既存インスタンスに反映されない。
* Neutral: ドメインは `.dev`（HSTS preload）なので HTTP では絶対に繋がらない。今回の用途では利点。
* Neutral: Anthropic のキーはサーバー専用に発行した静的キー（Service account key、有効期限つき）。
  Anthropic の Workload Identity Federation（AWS IAM の OIDC トークンを短命トークンに交換）は
  hindsight-api 0.9.2 の Anthropic プロバイダが静的キーしか受け付けないため採用しない。対応したら
  Issuer を AWS IAM にして切り替える。

### Confirmation

`tests/test_hindsight.py` の `TestServerAssets` が、compose の YAML 妥当性・サービス構成・API キー認証の有効化・
既知の罠を防ぐ設定値の存在・gitignore・`terraform fmt -check` と `validate` を検証する。
`TestInstallClient` が API キーの有無でフラグメントの `headers` が変わること、キー入りフラグメントが所有者のみ
読める権限であることを検証する。実挙動は `curl https://hindsight.akmaru.dev/health` と `claude mcp list` で確認する。

## Pros and Cons of the Options

### 到達経路 1. Tailscale

* Good: 公開ポートなし。認証を Tailscale に任せられる。
* Bad: 使う全マシンに Tailscale を入れる必要があり、CI や共有環境から繋げない。

### 到達経路 2. 公開 HTTPS + API キー（採用）

* Good: どこからでも URL とキーだけで繋がる。hindsight-api の組み込み機能で済む。
* Bad: インターネットに露出する。キー管理が自分の責任になる。

### 到達経路 3. SSM ポートフォワード

* Good: 公開ポートなし、追加ツールなし。
* Bad: 毎回トンネルを張る必要があり、常駐 MCP の接続先として不便。

### 構成 1. EC2 + Docker Compose（採用）

* Good: 最安。Terraform も Compose も小さく、ローカルの `docker compose up` で同じ構成を再現できる。
* Bad: OS と Postgres の運用が自前。

### 構成 2. ECS Fargate + RDS

* Good: OS 管理なし、DB バックアップがマネージド。
* Bad: 月額が 2 倍以上（ALB + RDS）。Terraform が 3 倍になる。埋め込みモデル込みのイメージはコールドスタートが遅い。

### 構成 3. Lightsail

* Good: 固定料金で最も簡単。
* Bad: Terraform のリソースが限定的で SSM / DLM / Parameter Store と繋ぎにくい。VPC 外なので拡張しにくい。

### 置き場所 1. すべて dotagents

* Good: 1 リポジトリで完結する。
* Bad: public リポジトリに個人ドメインの全体像・WHOIS 連絡先（state 経由）・バケット名が入る。

### 置き場所 2. private リポジトリ + dotagents（採用）

* Good: 所有権の境界（ドメインは共有資産、Hindsight はその一利用者）がリポジトリの境界と一致する。
* Bad: 2 リポジトリにまたがる。ゾーンのレコードを誰が持つかの規約が要る（サービス側が持つ、と README に明記）。

## More Information

関連: [ADR 0007](0007-hindsight-setup-assets.md)（ローカル構成。本 ADR はその「将来リモートへ移す」を実現し、
ローカル構成は評価・開発用として残す）。

参考: [Hindsight installation](https://hindsight.vectorize.io/developer/installation)（Docker イメージ、RAM 要件）、
`hindsight_api/extensions/builtin/tenant.py`（`ApiKeyTenantExtension`）。
