---
status: accepted
date: 2026-09-22
decision-makers: akmaru
---

# 解説役（explainer）は同じ herdr タブの固定 pane に常駐させ、メインのトランスクリプトを整形して読む

## Context and Problem Statement

タスクの方針・経過・結果・用語について、ユーザーがメインセッションの作業を止めずに対話的に質問できる
解説役が欲しい。[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md) の判断基準では、解説役は
「ユーザーと直接会話する」「メインの会話履歴が要る」の両方を満たすためサブエージェントにできない。

ユーザーの要件は 3 つ: (1) 質問のたびに pane やセッションが増えない、(2) メインと同じタブの別 pane に
常にあり、話題ごとに文脈を区切れる、(3) メインの作業状態と会話状態を explainer に食わせる手段がある。
どの実行形態と、どの状態受け渡しの方式で満たすかを決める。

## Decision Drivers

* 質問のコスト（トークン・待ち時間）が小さいこと
* メインの最新状態に追従できること
* 既存の herdr 資産（pane と Claude セッション ID の紐付け、fork スクリプト、キーバインド）に乗ること
* 非公開の内部形式（トランスクリプト JSONL）への依存が壊れたときに気づけること

## Considered Options

1. 話題ごとにメインから fork（`--resume --fork-session --agent explainer`）し、固定 pane に上書きする
2. 常駐セッション（`claude --agent explainer`）が、herdr 経由で特定したメインのトランスクリプトを整形して読む
3. メインが節目ごとにセッション間メッセージで要約を push する

1 と 2 は「状態の受け渡しを fork の履歴継承で済ませるか、ファイルの読み込みで済ませるか」で分かれる。

## Decision Outcome

選択: **2. 常駐セッション + トランスクリプト整形**（ユーザー決定）。

- 起動は herdr のキーバインド 1 つ（`prefix+alt+f`）。キーを押した時点のフォーカス pane をメインとみなし、
  `pane split --env HERDR_MAIN_PANE_ID=<pane_id>` で初期値を渡し、ラベル `main` を付ける。explainer は
  質問のたびに `herdr pane get` で**現在の** session id を引き直す（`/clear` や resume に追従）。
- explainer pane にはラベル `explainer` を付け、再利用はラベルで判定する（herdr のエージェント名は
  スクリプト起動時しか付かないため）。
- 整形は `user/bin/claude-main-digest.sh`。既定は直近 6 ターン・上限 1.2 万字から始め、同じ話題の 2 問目
  以降は差分（`--since`）を読む。
- 話題の区切りは explainer pane の `/clear`。区切る前に理解度を Hindsight に 1 件 retain する。
- 起動スクリプトは `user/herdr/scripts/explainer-pane.sh` を新設し、既存の fork スクリプトは改造しない。
- 機構の詳細は [docs/design/explainer-pane.md](../design/explainer-pane.md)。

### Consequences

* Good: pane はタブ内に常に 1 つ。質問ごとに最新のメイン状態に追従する。起動時のコンテキストは空。
* Good: 話題を `/clear` で区切りつつ、理解度は Hindsight で持ち越せる。
* Bad: トランスクリプト JSONL（非公開形式）と herdr の `agent_session` に依存する。Claude Code の更新で
  整形が壊れ得るため、fixture とローカルスモークで検知する。
* Bad: 整形スクリプトの実装と保守が要る（fork 方式なら不要だった）。
* Neutral: fork 方式（`prefix+f`）は手動フォールバックとして残る。

### Confirmation

段階 1b で追加した（設計書は [docs/design/explainer-pane.md](../design/explainer-pane.md)）。

* `tests/test_herdr.py`: `test_explainer_keybinding_points_at_an_executable_script` が
  `prefix+alt+f` のバインドが `type = "shell"` で実行可能な `explainer-pane.sh` を指すことを、
  `test_explainer_pane_script_starts_a_role_that_exists` が同スクリプトの `--agent <x>` の `<x>` が
  `user/agents/<x>.md` に実在することを検証する。
* `tests/test_user_config.py`: `test_main_digest_script_is_executable` /
  `test_main_digest_script_is_distributed_by_install_sh` が `claude-main-digest.sh` の実行権と
  `install.sh` による `~/.local/bin` への配布を、`test_explainer_description_says_it_is_not_a_subagent`
  が `explainer.md` の description に「サブエージェントとしては起動しない」の趣旨があることを検証する。
  `TestAgentDefinition`（`user/agents/*.md` 共通）は `explainer` にも及ぶが、
  `INTERACTIVE_AGENTS` に含めているため「未決事項」の必須化は対象外にしている。
* `tests/test_transcript_digest.py` + `tests/fixtures/transcript-sample.jsonl`: `--file` 経路で
  選別規則（`isSidechain` / `isMeta` / tool_result ラッパー / thinking / 壊れた行の除外、
  `message.id` によるブロック束ね）、`--turns` の窓、`--since`（既知 UUID と未知 UUID の
  フォールバック警告）、`--max-chars` の古い側からの切り詰め、`--resolve-only`、
  終了コード（0 / 5 / 4）を検証する。`DOTAGENTS_REAL_TRANSCRIPT=1` のときだけ手元の最新
  トランスクリプトに対するスモークが走り、形式ドリフトを早期検知する。
* 実機（未実施、手動確認の予定）: 設計書「テスト」節の手動シナリオ（`prefix+alt+f` でのラベル付け、
  pane 再利用、`/clear` 後の session id の引き直し）。

## Pros and Cons of the Options

### 1. 話題ごとに fork し固定 pane に上書き

* Good: 状態の受け渡しが fork の履歴継承で済み、実装がほぼ不要。
* Bad: メインの会話が長いと fork も同じ文脈量で始まり残り容量が少ない。fork 後のメインの進捗は見えず、
  再 fork が要る。`--agent` の system prompt が fork 直後に切り替わるか未確認。

### 2. 常駐セッション + トランスクリプト整形（採用）

* Good: 質問ごとに最新に追従し、読む量を制御できる。理解度を話題を跨いで持てる。
* Bad: 非公開形式への依存と整形スクリプトの保守。

### 3. メインが要約を push

* Bad: メインの手間とトークンを毎回消費し、権限モードが違うと承認待ちになり、要約に漏れた情報は
  explainer が知り得ない。

## More Information

関連: [ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)（役割定義と実行形態）、
[ADR 0008](0008-herdr-config-in-dotagents.md)（herdr 設定の置き場所）、
[ADR 0010](0010-herdr-plugins-declared-in-install-sh.md)（herdr スクリプトの PATH 規則）。
設計書: [docs/design/explainer-pane.md](../design/explainer-pane.md)。
