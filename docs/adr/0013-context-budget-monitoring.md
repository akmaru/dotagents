---
status: proposed
date: 2026-09-22
decision-makers: akmaru
---

# コンテキスト使用量は SessionStart hook の非対話 `/context` と transcript 解析でローカルに監視する

## Context and Problem Statement

Claude Code の各セッションが「どこに」「どれくらい」コンテキストを使っているかが見えない。
statusLine（[ADR 0009](0009-settings-json-merge.md) で配る `claude-statusline.sh`）は合計しか出さず、
`/context` は対話中に手で叩かないと見られない。2026-09-22 に memory MCP を外した際は、48 個の
transcript を手で数えて「呼び出し 0 回、毎セッション約 1.7k tokens」を確認した。この確認を人手で
繰り返すのは現実的でなく、放っておくと MCP・プラグイン・メモリファイルは増える一方になる。

欲しいのは次の 3 つ。

1. 起動直後のベースライン（システムツール・MCP・メモリ・スキル）の内訳と、その推移
2. セッション中の増加分の内訳（どのツールの結果が積み上がっているか）
3. 「減らせる」候補が、頼まなくても目に入ること

## Decision Drivers

* 計測のために API を叩かない（課金ゼロ、レイテンシ影響なし）
* 追加のデーモン・コレクタ・外部サービスを増やさない（個人用途、運用の手数を増やさない）
* 既存の配布経路（`user/install.sh`、[ADR 0004](0004-user-config-distribution-symlink-import.md)）に乗る
* herdr の SessionStart hook（[ADR 0008](0008-herdr-config-in-dotagents.md)）を壊さない
* 削減の判断と適用はエージェント（人）が行い、計測器は勝手に設定を変えない
* Claude Code の内部形式（transcript）に依存する箇所は、壊れたときに気づける

## Considered Options

計測手段:

1. `claude -p "/context" --output-format json` を非対話で叩く + transcript JSONL を解析する
2. OpenTelemetry（`CLAUDE_CODE_ENABLE_TELEMETRY=1` + OTLP collector）
3. statusLine の JSON を毎回ログに落とす
4. Claude Code 組み込みの `/insights`

自律的に動かすトリガ:

1. SessionStart hook（1 日 1 回に間引き、裏で取得）
2. launchd の定期ジョブ
3. Claude の cloud routine（`/schedule`）
4. herdr プラグイン

## Decision Outcome

選択: **非対話 `/context` + transcript 解析**を **SessionStart hook** で動かす。
実体は `user/bin/claude-context.py`（標準ライブラリのみ）で、3 つの入口を持つ。

* `snapshot`: `claude -p /context --output-format json --no-session-persistence` でベースラインの内訳を
  JSON に保存する。`local_command` として処理され API は呼ばれない（`total_cost_usd: 0`、約 2.5 秒）。
  `--no-session-persistence` で transcript を残さないので、集計対象に混ざらない
* `report`: `~/.claude/projects/**/*.jsonl` の各 assistant 行にある `usage`（input + cache_creation +
  cache_read = その時点のコンテキスト量）を時系列に並べ、連続する 2 リクエスト間の差分を、その間に入った
  要素（前ターンの出力・ツール結果・ユーザー入力・attachment）へ推定トークン比で按分する。差分は API の
  実測値なので合計は正確、内訳は推定。これにスナップショットを突き合わせ、MCP サーバーごとの
  「定義トークン × 実際の呼び出し回数」、メモリファイルの肥大、支配的なツール、巨大な単発結果、
  前回スナップショットからの増加、をルールで指摘する
* `session-start`: hook 本体。スナップショットが 24 時間より古ければ裏で取り直し、前回の分析で出た
  削減候補の先頭 3 行を標準出力に出す（SessionStart の stdout はセッションのコンテキストに入るので、
  エージェントがそのまま拾える）

削減の**適用**は `packages/context-budget` スキルが担う。計測器は設定を変えない。

### なぜ OpenTelemetry ではないか

トークン数の**合計**は取れるが、`/context` が出す区分別の内訳（MCP ツール単位・メモリファイル単位）は
出ない。collector を常駐させる必要もある。合計だけなら transcript に既にある。

### なぜ statusLine のログではないか

statusLine が受け取る JSON も合計だけで、内訳が無い。transcript を読めば同じ値が後から再構成できる。

### なぜ `/insights` ではないか

Claude Code 組み込みの HTML レポートで、作業内容の振り返りが目的。MCP やメモリファイルの
トークン内訳は出ず、機械可読でもない。

### なぜ launchd / routine / herdr プラグインではないか

* launchd: 動くが、どのプロジェクトで測るかを別途宣言する必要がある。hook なら実際に使っている
  プロジェクトで自然に測れる
* cloud routine: ローカルの transcript を読めない
* herdr プラグイン: herdr 無しの環境（OpenCode、SSH 先）で動かない。hook は Claude Code だけで完結する

### 入れ子起動の扱い

hook から `claude -p` を起動すると、その claude でも SessionStart hook が走る。無限連鎖を避けるため
環境変数 `DOTAGENTS_CONTEXT_SNAPSHOT=1` を立てて起動し、hook はこれを見て何もしない。
また herdr の hook が入れ子の claude を pane に紐付けてしまうので、`HERDR_*` は渡さない。

### hook の登録場所

`hooks.SessionStart` は herdr も書き込む配列で、`install.sh` の `jq` deep merge では配列が丸ごと置換される
（[ADR 0009](0009-settings-json-merge.md)）。`user/settings.json` に持たせると herdr の hook を消してしまう
ので、`install.sh` が `~/.claude/settings.json` に「無ければ追記」する。

### Consequences

* Good: 課金ゼロで、起動直後の内訳と会話中の増加要因が数字で出る。
  初回のレポートで `claude_ai_Google_Drive`（11 ツール 5.9k）と `drawio`（7 ツール 4.5k）が
  14 日間 1 度も呼ばれていないこと、増加分の 23% が Bash 出力であることが分かった
* Good: 気づきが SessionStart で 1〜3 行だけ流れるので、頼まなくても目に入る
* Bad: `claude -p /context` の非対話実行は公式ドキュメントに無い（`local_command` の挙動に依存）。
  壊れたら `snapshot` は例外で止まり、`report` は「スナップショットなし」になる。対話中に打った
  `/context` の出力も transcript に残るので、最悪そこから拾う手はある
* Bad: transcript の形式は Claude Code の内部仕様で、バージョンで変わり得る。読めない行は飛ばし、
  fixture ベースのテストで壊れたことに気づく方針
* Bad: セッション開始時に `claude` プロセスが 1 つ余分に立つ（1 日 1 プロジェクト 1 回、約 2.5 秒、裏で）
* Bad: `-p` モードは対話モードより組み込みツールが少なく、System tools の値は対話時より小さく出る
  （22.4k vs 45.2k）。MCP・メモリ・スキル・エージェントの内訳は同じ
* Neutral: 「assistant output」には thinking が含まれ、実際に残る量より大きめに出る。
  按分の重みとして使っているだけで、他の要因の絶対値には影響が小さい

### Confirmation

`tests/test_context_budget.py` が、2.1.278 で実際に出た `/context` の Markdown と transcript の形を縮めた
fixture で、パース・差分の帰属・提案ルール・hook の入れ子ガードと `HERDR_*` の除去を検証する。
`tests/test_install.py` が、hook が 1 つだけ追記され既存の hook が残ることを検証する。

## Pros and Cons of the Options

### 計測 1. 非対話 `/context` + transcript 解析

* Good: 課金ゼロ、依存なし、内訳が MCP ツール単位で出る
* Bad: どちらも内部仕様依存

### 計測 2. OpenTelemetry

* Good: 公式にサポートされた計測経路。他ツールとの統合が容易
* Bad: 内訳が出ない。collector の常駐が要る

### 計測 3. statusLine ログ

* Good: 既に動いているスクリプトに数行足すだけ
* Bad: 内訳が出ない。5 秒ごとの書き込みが増える

### 計測 4. `/insights`

* Good: 組み込み。メンテ不要
* Bad: 目的が違う（振り返り用）。機械可読でない

### トリガ 1. SessionStart hook

* Good: 実際に使うプロジェクトで自動的に測れる。気づきをその場で流せる
* Bad: 入れ子起動と herdr との干渉に対処が要る

### トリガ 2. launchd

* Good: セッションに影響しない
* Bad: 対象プロジェクトを別に管理する。macOS 限定

### トリガ 3. cloud routine

* Bad: ローカルの transcript を読めない

### トリガ 4. herdr プラグイン

* Good: pane と紐付いた表示ができる
* Bad: herdr 無しの環境で動かない

## More Information

* Claude Code の hook 仕様: [Hooks reference](https://code.claude.com/docs/en/hooks.md)
* コンテキスト削減の公式ガイド: [Reduce token usage](https://code.claude.com/docs/en/costs.md#reduce-token-usage)
* transcript の場所と「内部形式」の注意: [Sessions](https://code.claude.com/docs/en/sessions.md#export-and-locate-session-data)
* 関連: [ADR 0008](0008-herdr-config-in-dotagents.md)、[ADR 0009](0009-settings-json-merge.md)
