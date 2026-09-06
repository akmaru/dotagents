# hindsight

[Hindsight](https://github.com/vectorize-io/hindsight) をエージェントの長期記憶として使うためのセットアップ資産。

サーバー側とクライアント側を分けている。将来サーバーをリモート（AWS 等）へ移す場合、クライアントは接続先 URL を変えるだけで済み、サーバーのインストールは不要になる。

```
サーバー側                              クライアント側
hindsight-api (127.0.0.1:8888)  ←────  Claude Code / VS Code / GitLab Duo
  ├─ pg0 (~/.pg0)                       MCP: http://localhost:8888/mcp
  └─ ローカル埋め込みモデル
```

## サーバー側のセットアップ

Hindsight を実際に動かすマシンでのみ実行する。ローカル埋め込みモデルを含むため常駐時の RSS が 800MB を超える。

```bash
./install-server.sh
```

`hindsight-api` を pip で導入し、`hindsight-start.sh` / `hindsight-stop.sh` を `~/.local/bin` に配置する。

### API キーの登録

macOS では Keychain から取得する。

```bash
security add-generic-password -a "${USER}" -s hindsight-anthropic-api-key -w
```

Linux では Keychain を使わない。`HINDSIGHT_API_LLM_API_KEY` を環境に設定しておけば、そちらが優先される。秘密の管理は systemd やクラウドの secret manager に任せる。

### 起動・停止

```bash
hindsight-start.sh
hindsight-stop.sh
tail -f ~/.hindsight/daemon.log
```

`hindsight-start.sh` は起動前にポート衝突を確認し、起動後に `/health` で疎通を確認する。デーモンが正しく上がったかは次で判定できる。

```bash
ps -o pid,ppid,tty,args= -p "$(lsof -nP -iTCP:8888 -sTCP:LISTEN -t | head -1)"
```

`PPID 1` かつ `TTY ??` ならデーモン化に成功している。

デーモンはターミナルを閉じても、ログアウトして再ログインしても生き続ける。止まるのは再起動・シャットダウン・クラッシュのときで、その場合は手動で `hindsight-start.sh` を実行する。

## クライアント側のセットアップ

```bash
./install-client.sh
```

`${XDG_CONFIG_HOME}/mcp/master-mcp.d/hindsight.json` を生成し、`mcp/sync-mcp.sh` を実行する。これで Claude Code / Claude Desktop / VS Code / GitLab Duo すべてに配布される。

リモートのサーバーに繋ぐ場合は URL を指定する。

```bash
HINDSIGHT_MCP_URL=https://hindsight.example.ts.net/mcp ./install-client.sh
```

確認:

```bash
claude mcp list | grep hindsight
```

以前 `claude mcp add --scope local` で個別に登録していた場合は、user スコープと二重になるので削除する。

```bash
claude mcp remove --scope local hindsight
```

## Control Plane (Web UI)

使用頻度が低いので起動スクリプトは用意していない。

```bash
npx -y @vectorize-io/hindsight-control-plane \
  --api-url http://127.0.0.1:8888 --hostname localhost --port 19999
```

バンクとメモリの一覧、エンティティのグラフ、取り込み履歴、recall の試験実行ができる。認証がないので `--hostname` を省略してはいけない。

Control Plane の既定ポートは 9999 だが、ありふれた番号で他のローカルサービスと衝突しやすいため 19999 にずらしている。

**`--hostname 127.0.0.1` にしてはいけない。** 全ページが 307 で自己リダイレクトし `ERR_TOO_MANY_REDIRECTS` になる。next-intl のミドルウェアが生成する rewrite 先が常に `localhost` という綴りで組み立てられ、サーバー自身の HOSTNAME 文字列が一致しないと rewrite が内部処理されずリダイレクトとして漏れるため（[issue #1926](https://github.com/vectorize-io/hindsight/issues/1926)、CLOSED だが 0.9.2 でも未修正）。どちらの指定でもループバック限定でバインドするので、露出の差はない。

macOS では `localhost` 指定時に IPv6 ループバック `[::1]` のみに bind されるため、`127.0.0.1:19999` ではなく `localhost:19999` でアクセスする。

## 既知の罠

- **`HINDSIGHT_API_LLM_PROVIDER` を設定し忘れると 401 になる。** 未設定だと `config.py` の `DEFAULT_LLM_PROVIDER="openai"` にフォールバックし、Anthropic のキーを OpenAI のエンドポイントへ送る。`config.sh` で設定済み。
- **`--daemon` は失敗しても無言。** 親が即座に `exit(0)` するため、ポート衝突などでバインドに失敗してもシェルには何も出ない。しかも古いプロセスが応答するので `/health` も通ってしまう。`hindsight-start.sh` はこれを検知する。
- **retain が投入テキストを別言語に翻訳する。** 日本語で `retain` しても fact が英語や中国語で保存されることがある。`llm_output_language` は「未設定ならソースの言語を保持する」建前だが実際には保持されない。`config.sh` で `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese` を指定して回避している。retain / consolidation / reflect すべてに一律で効く。副作用として、fact 本文の人名が漢字に変換されることがある (`entities` 側は原綴りを保つ)。
- **`reflect` は記憶にない情報を捏造する。** 既定の `claude-haiku-4-5` では顕著で、directive も無視する。`config.sh` で reflect のみ `claude-sonnet-5` に上げている。事実確認には `recall`（保存された fact をそのまま返す）を使い、`reflect` の出力は検証する。

## バンクの移行

将来サーバーをリモートへ移す場合は、埋め込みを含まないポータブルな ZIP で出し入れできる。

```bash
hindsight-admin export-bank <bank_id>
hindsight-admin import-bank <archive>
```

`hindsight-admin` にはこのほか `backup` / `restore` / `run-db-migration` / `worker-status` などがある。
