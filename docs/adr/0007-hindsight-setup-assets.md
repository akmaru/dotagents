---
status: accepted
date: 2026-09-06
decision-makers: akmaru
---

# Hindsight のセットアップ資産は dotagents に置き、サーバーとクライアントを分離する

## Context and Problem Statement

エージェントの長期記憶として [Hindsight](https://github.com/vectorize-io/hindsight) をローカルで評価し、
実用できることを確認した。しかし導入・起動・MCP 登録がすべて手作業で再現性がなく、API キーがシェル履歴に
残り、`--hostname localhost` 必須といった罠がどこにも記録されていない。これを資産化するにあたり、
どのリポジトリにどう置くか、また常駐をどう扱うかを決める。

## Decision Drivers

* 別マシンでも同じ環境を再現できること
* API キーをリポジトリにもシェル履歴にも残さないこと
* 将来サーバーをリモート（AWS 等）へ移す可能性があること
* 踏んだ罠を実行時に再度踏まない形で残すこと
* `packages/`（APM マーケットプレイス掲載物）を汚さないこと

## Considered Options

1. dotfiles に置く
2. dotagents に置く
    1. サーバーとクライアントを 1 つのスクリプトにまとめる
    2. サーバーとクライアントを別スクリプトに分ける

常駐方式については別途:

1. launchd LaunchAgent で管理する
2. `hindsight-api --daemon` を手動で起動する

## Decision Outcome

選択: **「dotagents に置き、サーバーとクライアントを別スクリプトに分ける」**および
**「`--daemon` を手動起動する」**。

dotagents はエージェント関連の設定を集約するリポジトリであり、Hindsight はエージェントの記憶基盤なので
ここに属する。`packages/` は APM 掲載物、`user/` は symlink 配布のエージェント設定なので、どちらでもない
トップレベル `hindsight/` を新設する。

サーバー側（`install-server.sh`）はローカル埋め込みモデルを含み常駐時の RSS が 800MB を超えるため、
動かすマシンでのみ手動実行する。クライアント側（`install-client.sh`）は接続先 URL だけを持つ軽量な設定で、
リモートへ移した後もそのまま使える。

MCP 設定は dotfiles の `mcp/sync-mcp.sh` が持つ `master-mcp.d/` インクルード機構に相乗りする。
この仕組みは「別リポジトリからの追加設定」用に設計されており、`install/mcp.sh` が既に
`${XDG_CONFIG_HOME}/mcp/master-mcp.d` を作成している。dotagents 側に MCP 配布機構を新設しない。

秘密は macOS Keychain（`security find-generic-password`）から取得し、`HINDSIGHT_API_LLM_API_KEY` が
既に環境にあればそちらを優先する。Linux のキーストア（libsecret）には対応しない。ヘッドレスなサーバーでは
キーリングのアンロックが問題になり、その用途では環境変数の方が素直なため。

### Consequences

* Good: 別マシンでの再現が 2 コマンド（`install-server.sh` / `install-client.sh`）になる。
* Good: リモートへ移す際、クライアントは `HINDSIGHT_MCP_URL` を変えるだけで済む。
* Good: 踏んだ罠が実行時のチェック（ポート衝突・疎通確認）と README に残る。
* Bad: 再起動・シャットダウン・クラッシュ後は手動で `hindsight-start.sh` を実行する必要がある。
* Bad: クライアント側が dotfiles の `sync-mcp.sh` に依存する。dotfiles 未導入のマシンでは
  フラグメントを生成するだけで配布まで至らない（その旨をスクリプトが警告する）。
* Neutral: dotagents に `packages/` / `user/` 以外のトップレベルディレクトリが増える。
  marketplace 非掲載なので `apm pack` および既存テストには影響しない。

### Confirmation

`tests/test_hindsight.py` が、一時 HOME と `XDG_CONFIG_HOME` で `install-client.sh` を実行し、
生成されたフラグメントが valid JSON であること・`HINDSIGHT_MCP_URL` が反映されること・べき等であることを
検証する。あわせて `hindsight/` 配下の各スクリプトの shebang と実行権限を検証する。

`install-server.sh` は `pip install` を伴うためテストから実行せず、構造的な検証のみとする。
サーバーの実挙動は `hindsight-start.sh` の疎通確認と `claude mcp list` で確認する。

## Pros and Cons of the Options

### 1. dotfiles に置く

* Good: 既存の `install/` と `bin/` の枠組みにそのまま乗る。
* Bad: エージェント関連の設定は dotagents へ移管済みで、逆行する。
* Bad: dotfiles は 3 OS 対応なので、macOS 前提の Keychain 依存が浮く。

### 2.1. dotagents・サーバーとクライアントを 1 スクリプトに

* Good: 実行するコマンドが 1 つで済む。
* Bad: クライアントとしてのみ使うマシンでも、重いサーバーの導入を強いる。
* Bad: リモートへ移した際に分離し直すことになる。

### 2.2. dotagents・サーバーとクライアントを別スクリプトに（採用）

* Good: マシンの役割に応じて必要な方だけ実行できる。
* Good: リモート移行時にクライアント側の変更が URL だけで済む。
* Bad: スクリプトが 2 本になり、README で使い分けを説明する必要がある。

### 常駐方式 1. launchd LaunchAgent

* Good: ログイン時起動・クラッシュ時の自動復帰・`launchctl` での状態確認ができる。
* Good: 起動失敗が終了コードとして観測できる。
* Bad: シェル環境を継承しないため、PATH と環境変数をすべて plist に明示する必要がある。
* Bad: plist に秘密を書くか、ラッパーを挟むかの判断が追加で必要になる。

### 常駐方式 2. `--daemon` を手動起動（採用）

* Good: シェルの環境をそのまま継承でき、設定が単純になる。
* Good: `setsid(2)` によりターミナルを閉じても、ログアウトして再ログインしても生存する（実測）。
* Bad: 再起動・クラッシュ後の復帰が手動になる。
* Bad: PID ファイルを持たないため、停止は待ち受けポートから引く必要がある。

## More Information

関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)（`user/` の symlink 配布方針。
本 ADR のクライアント側フラグメントは接続先 URL がマシン依存のため symlink ではなく生成する点で異なる）。

参考: [Hindsight installation](https://hindsight.vectorize.io/developer/installation)、
[Control Plane のリダイレクトループ issue #1926](https://github.com/vectorize-io/hindsight/issues/1926)。
