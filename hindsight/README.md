# hindsight

[Hindsight](https://github.com/vectorize-io/hindsight) をエージェントの長期記憶として使うためのセットアップ資産。

サーバー側（AWS、[ADR 0011](../docs/adr/0011-hindsight-on-aws.md)）とクライアント側を分けている。
以前のローカル常駐構成（[ADR 0007](../docs/adr/0007-hindsight-setup-assets.md)）は AWS 移行にともない削除した。

```
サーバー側 (AWS)                                       クライアント側
hindsight.akmaru.dev (EC2 / Docker Compose)  ←────  Claude Code / VS Code / GitLab Duo
  ├─ caddy         TLS 終端 (Let's Encrypt)           MCP: https://hindsight.akmaru.dev/mcp
  ├─ hindsight-api ApiKeyTenantExtension で認証            Authorization: Bearer <key>
  └─ postgres      pgvector、EBS 上、日次スナップショット
```

## AWS へのデプロイ (`aws/`, `compose/`)

```
aws/       Terraform: EC2 (t4g.medium, AL2023 arm64) / データ用 EBS / EIP / SG / IAM / SSM / DLM / Route 53 レコード
compose/   サーバー上で動く docker-compose.yml, Caddyfile, deploy.sh
```

ゾーン `akmaru.dev` と tfstate バケットは別リポジトリ [akmaru/akmaru.dev](https://github.com/akmaru/akmaru.dev)（private）が持つ。
ここはゾーンを名前引きして `hindsight` の A レコードを 1 本足すだけ。アカウント固有の値（バケット名・profile）は
`backend.hcl` / `terraform.tfvars`（gitignore）に置き、雛形は `*.example` にある。

### 初回

1. 秘密を SSM Parameter Store に置く（Terraform の state に載せないため Terraform 外で行う）

   ```bash
   aws ssm put-parameter --type SecureString --name /hindsight/anthropic_api_key --value "$(security find-generic-password -a "${USER}" -s hindsight-anthropic-api-key -w)"
   aws ssm put-parameter --type SecureString --name /hindsight/tenant_api_key    --value "$(openssl rand -hex 32)"
   aws ssm put-parameter --type SecureString --name /hindsight/postgres_password --value "$(openssl rand -hex 24)"
   ```

2. apply

   ```bash
   cd aws
   cp backend.hcl.example backend.hcl && cp terraform.tfvars.example terraform.tfvars  # 埋める
   terraform init -backend-config=backend.hcl
   terraform apply
   ```

   `aws_ssm_parameter.plain` が接続先ドメインとイメージのタグを `/hindsight/domain`, `/hindsight/version` に書き、
   EC2 の user-data がこのリポジトリを `/opt/dotagents` に clone して `compose/deploy.sh` を実行する。
   `deploy.sh` は SSM から `.env` を生成し `docker compose up -d` する。Caddy が証明書を取るまで含めて数分かかる。

3. 疎通確認

   ```bash
   curl -s https://hindsight.akmaru.dev/health
   curl -s -H "Authorization: Bearer $(aws ssm get-parameter --name /hindsight/tenant_api_key --with-decryption --query Parameter.Value --output text)" https://hindsight.akmaru.dev/v1/default/banks
   ```

4. クライアント側にキーを登録して配布（下記「クライアント側のセットアップ」）

### 運用

| やること | 方法 |
|---|---|
| サーバーに入る | `aws ssm start-session --target $(terraform output -raw instance_id)`（SSH は開けていない） |
| バージョンを上げる | `variables.tf` の `hindsight_version` を変えて `terraform apply`（SSM の値が変わる）→ サーバーで `git -C /opt/dotagents pull && /opt/dotagents/hindsight/compose/deploy.sh` |
| compose / Caddyfile を変える | push → サーバーで上と同じ `pull && deploy.sh` |
| ログ | サーバーで `docker compose -f /opt/dotagents/hindsight/compose/docker-compose.yml logs -f hindsight-api` |
| バックアップ | DLM がデータ用 EBS を毎日 JST 03:00 にスナップショット、7 日保持。復元はスナップショットからボリュームを作って差し替える |
| インスタンスの作り直し | `terraform taint aws_instance.hindsight && terraform apply`。データ用 EBS は `prevent_destroy` で残り、再アタッチされる |

user-data は初回起動時にしか走らない。`user-data.sh.tftpl` を変えても既存インスタンスには反映されないので、
必要なら手で同じ操作をするか作り直す。

### 他インスタンスからの移行

```bash
hindsight-admin export-bank -b <bank_id> -o <archive>   # 移行元で。埋め込みを含まないポータブルな ZIP
# ZIP をサーバーへ送り (S3 の presigned URL 経由が楽)、サーバーで
cd /opt/dotagents/hindsight/compose
docker compose cp <archive> hindsight-api:/tmp/bank.zip
docker compose exec -T hindsight-api hindsight-admin import-bank -a /tmp/bank.zip
```

## クライアント側のセットアップ

ルートの `install.sh` から呼ばれる。単独でも実行できる。

```bash
./install-client.sh
```

`${XDG_CONFIG_HOME}/mcp/master-mcp.d/hindsight.json` を生成し、`mcp/sync-mcp.sh` を実行する。これで Claude Code / Claude Desktop / VS Code / GitLab Duo すべてに配布される。
接続先は既定で `https://hindsight.akmaru.dev/mcp`（`HINDSIGHT_MCP_URL` で上書き可）。

### API キーの登録

値は SSM Parameter Store にある。

```bash
aws ssm get-parameter --profile maru --name /hindsight/tenant_api_key --with-decryption --query Parameter.Value --output text
```

`api-key.sh` が次の順で探す。macOS と Linux のどちらでも使える。

| 順 | 場所 | 登録方法 | 向き |
|---|---|---|---|
| 1 | 環境変数 `HINDSIGHT_MCP_API_KEY` | `export` | CI・コンテナ |
| 2 | macOS Keychain | `security add-generic-password -a "${USER}" -s hindsight-mcp-api-key -w` | Mac |
| 2 | libsecret（`secret-tool`） | `secret-tool store --label='Hindsight MCP API key' service hindsight-mcp-api-key` | Linux デスクトップ |
| 3 | `~/.config/hindsight/mcp-api-key`（600） | `mkdir -p ~/.config/hindsight && (umask 077 && printf '%s\n' '<key>' > ~/.config/hindsight/mcp-api-key)` | ヘッドレス Linux |

キーが無い場合、既定 URL 向けにはフラグメントを書かず、上の登録方法を案内して正常終了する（キー無しの設定を配ると
全クライアントが 401 になるだけなので）。`install.sh` 全体は止まらない。`HINDSIGHT_MCP_URL` を明示した場合は
認証を無効にした開発用インスタンスとみなし、ヘッダなしで書く。

確認:

```bash
claude mcp list | grep hindsight
```

以前 `claude mcp add --scope local` で個別に登録していた場合は、user スコープと二重になるので削除する。

```bash
claude mcp remove --scope local hindsight
```

## Control Plane (Web UI)

サーバーには置かず、見たいときにローカルで起動して AWS の API に繋ぐ。

```bash
./control-plane.sh        # http://localhost:19999
```

`npx -y @vectorize-io/hindsight-control-plane` を、Keychain `hindsight-mcp-api-key` のキーを
`HINDSIGHT_CP_DATAPLANE_API_KEY` に載せて起動する。バンクとメモリの一覧、エンティティのグラフ、取り込み履歴、
recall の試験実行ができる。UI 自体に認証はないので `--hostname localhost`（ループバック限定）を外してはいけない。

Control Plane の既定ポートは 9999 だが、ありふれた番号で他のローカルサービスと衝突しやすいため 19999 にずらしている。

**`--hostname 127.0.0.1` にしてはいけない。** 全ページが 307 で自己リダイレクトし `ERR_TOO_MANY_REDIRECTS` になる。next-intl のミドルウェアが生成する rewrite 先が常に `localhost` という綴りで組み立てられ、サーバー自身の HOSTNAME 文字列が一致しないと rewrite が内部処理されずリダイレクトとして漏れるため（[issue #1926](https://github.com/vectorize-io/hindsight/issues/1926)、CLOSED だが 0.9.2 でも未修正）。どちらの指定でもループバック限定でバインドするので、露出の差はない。

macOS では `localhost` 指定時に IPv6 ループバック `[::1]` のみに bind されるため、`127.0.0.1:19999` ではなく `localhost:19999` でアクセスする。

## 既知の罠

- **`HINDSIGHT_API_LLM_PROVIDER` を設定し忘れると 401 になる。** 未設定だと `config.py` の `DEFAULT_LLM_PROVIDER="openai"` にフォールバックし、Anthropic のキーを OpenAI のエンドポイントへ送る。`compose/docker-compose.yml` で設定済み。
- **retain が投入テキストを別言語に翻訳する。** 日本語で `retain` しても fact が英語や中国語で保存されることがある。`llm_output_language` は「未設定ならソースの言語を保持する」建前だが実際には保持されない。`compose/docker-compose.yml` で `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese` を指定して回避している。retain / consolidation / reflect すべてに一律で効く。副作用として、fact 本文の人名が漢字に変換されることがある (`entities` 側は原綴りを保つ)。
- **`reflect` は記憶にない情報を捏造する。** 既定の `claude-haiku-4-5` では顕著で、directive も無視する。`compose/docker-compose.yml` で reflect のみ `claude-sonnet-5` に上げている。事実確認には `recall`（保存された fact をそのまま返す）を使い、`reflect` の出力は検証する。

## hindsight-admin

`export-bank` / `import-bank`（埋め込みを含まないポータブルな ZIP）のほか
`backup` / `restore` / `run-db-migration` / `worker-status` などがある。
