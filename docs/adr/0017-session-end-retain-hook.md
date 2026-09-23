---
status: accepted
date: 2026-09-23
decision-makers: akmaru
---

# 記憶の投入は SessionEnd hook が会話テキストだけを投げ、要約はサーバーに任せる

## Context and Problem Statement

[ADR 0015](0015-memory-ingestion-path.md) では「投入はメインセッションのモデルが行う（現状維持）」を選び、
hook による自動化は設計として記録するにとどめた。その判断は「秘密を止められる主体はモデルしかいない」
という前提に立っていた。

その後 2 つの事実が判明し、前提が変わった。

1. **Memory Defense** — Hindsight にはバンク単位の秘密スクラバがある。45 パターンの正規表現で、
   memory unit にも document body にも届く前に `[REDACTED:type]` に置換する。確率的なモデル判断とは
   性質の違う、決定的な網が使える
2. **コストの実測** — 生ログをそのまま投げる案と、会話テキストだけに絞る案の差は**月 $48.6 対 $1.3**
   で、得られる記憶はほぼ同じ。差は `jq` のフィルタ 1 枚

秘密を「絶対に入れない」から「なるべく弾く」に置き直すなら、投入経路を変える余地がある。

## Decision Drivers

* メインセッションのコンテキストを消費しないこと（[ADR 0013](0013-context-budget-monitoring.md) と同じ関心）
* 取りこぼさないこと。モデルが忘れれば記録されない状態をやめる
* 秘密は best-effort で弾ければよい。そもそも transcript に秘密が載っている時点で上流の問題であり、
  Hindsight は認証の内側にある
* 投入量に比例して増えるもの（課金・識別子破損・recall のノイズ）を増やさないこと
* 運用の手数を増やさないこと。常時動く部品をできるだけ持たない

## Considered Options

1. プロンプト方式の維持（ADR 0015 の決定）
2. hook から transcript の生ログをそのまま投入する
3. **hook から会話テキストだけを抽出して投入する**
    - 3.1. `SessionEnd` のみで発火する
    - 3.2. `Stop` でデバウンスしつつ発火し、`SessionEnd` で残りを回収する
4. hook から別プロセスの headless（`claude -p`）を起動し、選別もモデルにやらせる

2 と 3 の違いは `jq` のフィルタ 1 枚だけで、トリガも発火の保証もメインの消費ゼロも同じ。
3.1 と 3.2 は「そのセッション中に引けるか」と「途中で覆った案が事実として残るか」のトレードオフ。

## Decision Outcome

選択: **3.1 — `SessionEnd` hook が会話テキストだけを投入する**（採用）。

- 投入は `user/bin/hindsight-retain-hook.sh`。`POST /v1/default/banks/personal/memories`
  （`{"items": [...], "async": true}`）
- 残すのは `user` / `assistant` の `text` ブロックだけ。`thinking` / `tool_use` / `tool_result` /
  `attachment` / `system` は落とす。実測で 1,399,148 B の transcript が 15,777 文字になる
- `!` で実行したコマンドの出力（`<bash-stdout>` などのタグ）は文字列の user メッセージに紛れ込むため、
  タグごと落とす。打ったコマンド自体（`<bash-input>`）は短く文脈として役立つので残す
- 会話が 500 B 未満のセッションは投げない。挨拶や打ち間違いだけで抽出 LLM を焚かないため
- 要約はサーバー側の `concise` 抽出に任せる。**投入側とサーバー側の両方で要約しない**
- 秘密はバンクの `memory_defense`（`sensitive_data` → `redact`）で弾く
- 何が失敗しても `exit 0`。理由は `${XDG_STATE_HOME:-~/.local/state}/hindsight-retain/log` に残す

### なぜ `SessionEnd` だけか

`Stop`（3.2）なら数ターン後には同じセッションで引けるが、**途中で覆った案が事実として残る**。
2026-09-22 の会話では「Claude Mods で実装する」「`mcp_enabled_tools` を 7 ツールに絞る」が中間状態として
存在し、どちらも後に撤回された。`Stop` で拾っていればこれらが world fact になっていた。
加えてデバウンス閾値・多重起動のロック・水位管理という常時動く部品が増える。

代償として、hook が入れた記憶はそのセッション中には引けない。これを補うため、`user/AGENTS.md` には
「そのセッション中に引き直す必要があるものだけ `sync_retain`」という例外を 1 行だけ残す。

### なぜ headless（4）ではないか

メインの消費ゼロと発火保証に加えて判断主体も残せる唯一の案だが、`SessionEnd` の hook 予算が
全 hook 合計 1.5 秒しかないため detach が必須で、hooks は `-p` モードでも動くので再帰ガードも要る。
Memory Defense が決定的な網を用意してくれる以上、その複雑さを抱える理由が薄い。

### `document_id` に `session_id` を使う

`SessionEnd` は `clear` / `resume` / `logout` などで 1 セッション中に複数回発火しうる。
`document_id` を `session_id` に固定すると、`update_mode` の既定 `replace` が同じ文書を入れ替えるので
**再発火が自然に冪等になる**。代償として、再発火のたびに全量を再投入するので抽出コストは再度かかる。

### Consequences

[ADR 0015](0015-memory-ingestion-path.md) の 6 軸に対する位置。

* Good（軸 C: 発火の決定性）— hook が発火を保証する。モデルが忘れても記録される
* Good（軸 D: 投入主体の場所）— メインのコンテキストを消費しない
* Bad（軸 A: 投入タイミング）— そのセッション中には引けない。`sync_retain` の例外でしか補えない
* Bad（軸 B: 投入単位）— 議論の完結単位ではなく `retain_chunk_size = 3000` の機械的分割になる。
  chunk 境界をまたぐ因果は抽出器から見えない
* Neutral（軸 E: 投入前の選別）— 判断主体がモデルから正規表現に変わる。広さと確からしさを引き換えにした。
  ダミーの秘密を実際に投入して測ったところ、`sk-ant-...` → `[REDACTED:anthropic_key]`、
  `AKIA...` → `[REDACTED:aws_access_key]`、`ghp_...` → `[REDACTED:github_token]` はいずれも
  **保存されるドキュメント本文の時点で**置換された。一方 **prefix のない 64 桁 hex は素通りした**。
  `tenant_api_key` はまさにその形（`openssl rand -hex 32`）なので、既知の穴として受け入れる
* Neutral（軸 F: サーバー側の抽出）— `concise` のまま。投入側が要約しなくなったので、二重要約は解消する。
  ただし [ADR 0012](0012-hindsight-identifier-scanner.md) の識別子破損は投入量に比例して増える。
  会話テキストだけに絞ったので、生ログ投入に比べれば 1/37 に収まる
* Bad（コスト）— 月 $0.04 → $1.3 に増える（63 本の transcript から、平均 648,833 B・会話実体 2.6%・
  80 セッション/月・haiku 4.5 の $1/$5 で試算）。生ログをそのまま投げる案 2 なら月 $48.6 だった
* Neutral（移植性）— Claude Code 専用。OpenCode 側は記憶が増えなくなる（了承済み）

### Confirmation

`tests/test_retain_hook.py` が `HINDSIGHT_RETAIN_DRY_RUN=1`（POST せずペイロードを stdout に出す）で
スクリプトを実際に動かして検証する。

- `TestFiltering` — `thinking` / `tool_use` / `tool_result` / `attachment` / `system` /
  `file-history-snapshot` の中身が投入されないこと、`<bash-stdout>` などハーネス由来の
  コマンド出力が落ちること、`<bash-input>` は残ること
- `TestPayload` — タグが `project:<名前>` と `source:session-hook`、`document_id` が `session_id` であること
- `TestSkips` — 閾値未満・transcript 不在・API キー不在のいずれでも `exit 0` し、理由がログに残ること
- `TestRegistration` — `user/settings.json` に `hooks.SessionEnd` があり、`user/install.sh` が symlink を張ること
- `tests/test_install.py::test_settings_merge_keeps_local_keys` — `install.sh` のマージ後も
  herdr の `SessionStart` が残ること

Memory Defense が実際に何を弾くかは**自動検証していない**（サーバー側のバンク設定で、リポジトリに
コードが無いため）。網の穴を測るときは、ダミーの秘密を含む文を `document_id` を決めて投入し、
`GET /v1/default/banks/personal/documents/{document_id}` の `original_text` を見てから削除する。
`dry-run-extract` は保存経路を通らないため置換が起きず、この確認には**使えない**。

## Pros and Cons of the Options

### 1. プロンプト方式の維持

* Good: 文脈を見て判断できる。出所が分かるので秘密を見分けやすい
* Good: Claude Code と OpenCode の両方で効く
* Bad: 発火の保証がない
* Bad: メインのコンテキストを消費する

### 2. 生ログをそのまま投入

* Good: フィルタを書かなくてよい
* Bad: 月 $48.6。会話実体は 2.6% しかないので、払った額のほとんどが捨てられる
* Bad: 一時的な値（ファイルサイズ、grep のヒット）が事実化され、observation の質が落ちる
* Bad: `attachment` に `CLAUDE.md` / `AGENTS.md` が入るため、自分への指示を「事実」として記憶する
* Bad: 識別子破損が投入量に比例する

### 3. 会話テキストだけを投入（採用）

* Good: 2 の欠点のうちコストとノイズが 1/37 になる。得られる記憶はほぼ同じ
* Good: 部品が 1 本のシェルスクリプトだけで済む
* Bad: 秘密のゲートがモデルから正規表現に変わる
* Bad: Claude Code 専用

#### 3.1. `SessionEnd` のみ（採用）

* Good: 水位管理もロックも要らない。1 セッション 1 回の投入で完結する
* Good: 議論が完結してから投入するので、撤回された案が事実として残りにくい
* Bad: そのセッション中には引けない

#### 3.2. `Stop` でデバウンス

* Good: 数ターン後には同じセッションで引ける
* Bad: 途中で覆った案が肯定形の事実として残る
* Bad: デバウンス閾値・ロック・水位という調整点が増える

### 4. headless に選別させる

* Good: 軸 C・D・E を同時に満たす唯一の案
* Bad: 1.5 秒の hook 予算のため detach 必須、`-p` でも hooks が動くため再帰ガード必須
* Bad: 常時動く部品が増える

## More Information

* [ADR 0015](0015-memory-ingestion-path.md) — 本 ADR が supersede する。6 軸の定義と、案 1〜7 の全体像はそちら
* [ADR 0012](0012-hindsight-identifier-scanner.md) — 識別子破損。軸 F は未着手で、`retain_extraction_mode` を
  `verbatim` にすれば本文の書き直しが止まる。投入経路とは独立に判断できる。
  **2026-09-23 追記**: [ADR 0019](0019-output-language-via-retain-mission.md) で出力言語の固定をやめ、
  識別子保護ルールがプロンプトに戻った。破損の主因が取れたので、`verbatim` を持ち出す必要は薄い
* [ADR 0013](0013-context-budget-monitoring.md) — 軸 D を数値で追う手段
* [Memory Defense](https://hindsight.vectorize.io/developer/memory-defense/) — 45 パターンの一覧と
  `redact` / `block` の意味
* 検討時点の実測値: `retain_extraction_mode = concise` / `retain_chunk_size = 3000` /
  `retain_chunk_batch_size = 100`
