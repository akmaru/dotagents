---
status: accepted
date: 2026-09-25
decision-makers: akmaru
---

# Claude Code のみをターゲットにし、OpenCode 両対応の制約を畳む

## Context and Problem Statement

[ADR 0001](0001-target-claude-code-and-opencode.md)（2026-07-19）は「メインで Claude Code、併用で OpenCode」を
前提に両対応を決め、後続の ADR 0004 / 0005 / 0006 / 0014 / 0015 / 0018 の decision driver になった。
その後 OpenCode は導入されないまま 2 か月が経ち、両対応の制約は次の 4 箇所で手数を生んでいる。

* (a) `tests/test_user_config.py`: 役割 frontmatter のホワイトリスト（`tools` / `model` / `color` 禁止）、
  `permission: {edit: deny, task: deny}` の必須化、`mode` の値の限定。役割を足すたびに定型 2 キーが要り、
  ノードごとのモデル指定を役割ファイルに書けないため呼び出しごとに渡している（[ADR 0020](0020-workflow-graph-control-flow.md)）
* (b) `user/install.sh`: `~/.config/opencode/AGENTS.md` への symlink と、その検証テスト
* (c) `user/AGENTS.md` / `user/CLAUDE.md` の 2 段構成と「AGENTS.md に Claude 固有識別子を書かない」テスト
* (d) `CLAUDE.md` / `README.md` / `apm.yml` / 各 `SKILL.md` の「Claude Code and OpenCode」宣言

ユーザーは 2026-09-23 に「Claude Code を前提にしてよい。OpenCode は当面考えない」と決めた。
決めるべきは、4 箇所のどれを畳み、どれを残し、どの順で畳むかである。

この決定は `/deliberate`（[ADR 0020](0020-workflow-graph-control-flow.md)）を 1 周回して得た。
designer の設計報告、critic の批評、`/web-research` による一次情報の裏取り（agents.md の互換一覧に
Claude Code は載っていない、AGENTS.md 仕様に frontmatter / @import は無い）を台帳に持つ。

## Decision Drivers

* 役割を足すたびに払う手数（定型キー、ホワイトリストの更新）を消したい
* 「OpenCode の設定ロードを壊す」という理由のテストを、理由が消えた後に残さない（ADR とコードの理由を一致させる）
* 既存の役割定義の動作を壊さない。テストは各コミットで緑のまま
* Claude Code は未知の frontmatter キーを無言で無視する（[公式](https://code.claude.com/docs/en/sub-agents)）ため、
  `defaultMode: auto` 下の防壁である `disallowedTools` の欠落だけは検査で止めたい
* 他ツールへの再対応を排除しないが、備えもしない（YAGNI）
* 個人用途なので運用の手数を増やさない

## Considered Options

1. 案 A: 宣言 (d) + 配布 (b) + OpenCode 由来のテスト・キー (a) を畳み、2 段構成 (c) は残す
    - 1.1. (c) の識別子禁止テストも残し、理由を「agents.md 準拠の共通指示」に書き換える
    - 1.2. (c) のファイル分割は残すが、識別子禁止テストは外す
2. 案 B: 構造まで畳む（`user/AGENTS.md` を `user/CLAUDE.md` に統合。ADR 0005 も supersede）
3. 案 C: 宣言 (d) と ADR だけ畳み、コード（テスト・install.sh・役割ファイル）は触らない

役割 frontmatter の検査の形は別の軸で分かれる:

4. Claude 公式フィールド集合のホワイトリスト（`permissionMode` 除外）
5. `permissionMode` だけ禁止するブラックリスト
6. キー検査を廃止し、`disallowedTools` 必須 + `permissionMode` 禁止だけ残す

1 と 2 は「ファイル分割を OpenCode のためのものとみなすか」で、1.1 と 1.2 は「Claude 以外の AGENTS.md ツールを
試す余地を残すか」で分かれる。4〜6 は「未知キーを無言で無視する Claude に対して何を検査で止めるか」で分かれる。

## Decision Outcome

選択: **1.1（案 A、識別子禁止テストは残す）+ 6（キー検査は廃止）**（ユーザー決定 2026-09-25）。

適用するルール:

- **(d) 宣言を畳む**: `apm.yml` / `CLAUDE.md` / `README.md` / 各 `SKILL.md` の `compatibility` から OpenCode を外す。
  `CLAUDE.md` の「手動インストール（OpenCode）」節を削る。
- **(b) 配布を畳む**: `user/install.sh` の `~/.config/opencode/` ブロックを削り、`tests/test_install.py` の
  `EXPECTED_LINKS` から外す。ローカルに残る `~/.config/opencode/AGENTS.md` の symlink は手で消す
  （1 回きりの後始末に恒久コードを持たない）。
- **(a) テスト制約を畳む**: `tests/test_user_config.py` の frontmatter ホワイトリスト、`permission` 必須、
  `mode` の値検査を削る。残すのは `disallowedTools` に `Edit` / `Write` / `NotebookEdit` / `Agent` が揃うことと、
  `permissionMode` を書かないこと（[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md) の独立した理由:
  `auto` 下で無視されセッション間で権限クラスが割れる）。役割ファイル 5 本から `mode:` と `permission:` を削る。
- **(c) は残す**: `user/AGENTS.md` / `user/CLAUDE.md` の 2 段と識別子禁止テストは維持し、理由を
  「OpenCode が読む」から「AGENTS.md はツール非依存の共通指示（[agents.md](https://agents.md/)）。Claude 固有の
  ツール名は `user/CLAUDE.md` の対応表へ」に書き換える（[ADR 0005](0005-agents-md-canonical.md) は有効のまま）。
- **順序**: 1 PR に 3 コミット、(d) + 本 ADR → (b) → (a)。各コミットでテストが緑。
- **影響を受ける ADR**: [ADR 0001](0001-target-claude-code-and-opencode.md) は本 ADR が supersede。
  [ADR 0004](0004-user-config-distribution-symlink-import.md) は決定文の `~/.config/opencode/` 部分だけが失効する
  ので `amended by ADR-0021`（symlink 方式は維持）。[ADR 0006](0006-file-scoped-rules-claude-only.md) の
  「OpenCode には配置しない」は対象が消えて空文になるが、決定は変わらないので触らない。
  [ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md) の「OpenCode への配布は検証してから」「Bad: OpenCode 側は
  未検証」は無効になるが、過去の記録として本文は触らない。[ADR 0018](0018-workflow-graph-three-sccs.md) /
  [ADR 0020](0020-workflow-graph-control-flow.md) の driver「両ツールで成立」と Bad「ADR 0001 と衝突」は解消。
- **拡張点（名前だけ）**: 他ツール再対応は ADR 0014 の 1.4（install 時に Claude 固有キーを剥いだコピーを置く）。
  AGENTS.md 統合は本 ADR の案 B。

### Consequences

* Good: 役割 frontmatter に Claude の全フィールド（`model` / `effort` / `isolation` / `skills` 等）が使える。
  ノードごとのモデルを役割ファイルに書けるようになり、[ADR 0020](0020-workflow-graph-control-flow.md) の
  「呼び出しごとに指定」は役割側へ移せる。
* Good: 役割を足すときの定型 2 キー（`mode` / `permission`）が不要になる。
* Good: 「OpenCode を壊す」という理由のテストが消え、ADR とコードの理由が一致する。
* Bad: OpenCode に戻るときは ADR 0014 の 1.4 から再出発になる。
* Bad: 識別子禁止テストを残すので、Delegation の指示は `user/AGENTS.md` と `user/CLAUDE.md` に分けて
  書き続ける（現状と同じ手数。増えはしない）。これは「Claude 以外の AGENTS.md ツールを試す余地」と引き換え。
* Neutral: `docs/design/explainer-pane.md` の OpenCode 前提 2 行は [ADR 0016](0016-explainer-pane-transcript-digest.md)
  を進めるときに直す（変更していない設計書には手を入れない）。

### Confirmation

* `tests/test_user_config.py` の `TestAgentDefinition`: `test_disallowed_tools_block_writes_and_redelegation` が
  `disallowedTools` の 4 ツールを、`test_permission_mode_is_not_set` が `permissionMode` を書かないことを検証する。
  ホワイトリスト・`permission`・`mode` の検査は存在しない。
  `test_agents_md_has_no_claude_specific_identifiers` は残り、docstring の理由が agents.md 準拠になっている。
* `tests/test_install.py`: `EXPECTED_LINKS` に `.config/opencode` が無く、`test_does_not_create_opencode_config`
  が一時 HOME で `~/.config/opencode` が作られないことを検証する。
* `grep -rniE 'opencode' --include='*.md' --include='*.yml' --include='*.py' --include='*.sh' . | grep -v '^./docs/adr/'`
  の残りが `docs/design/explainer-pane.md` の 2 行だけであること（ADR 本文は履歴として残す）。
* 実機: `user/install.sh` を実行して Claude Code を再起動し、`mode:` / `permission:` を消した役割が
  `Agent` ツールから起動でき、`Edit` / `Write` が剥がれていることを確認する。

## Pros and Cons of the Options

### 1. 案 A: (d)(b)(a) を畳み、(c) は残す（採用）

* Good: 手数を生んでいる箇所（役割追加ごとの定型キー、ホワイトリスト、「OpenCode を壊す」理由のテスト、配布）を
  全部消せる。
* Good: (c) は `@import` が Anthropic 公式の推奨パターン（[memory docs](https://code.claude.com/docs/en/memory)）、
  AGENTS.md が vendor 非依存の open format、`CLAUDE.work.md` の import を CLAUDE.md 側に置く必要がある、という
  OpenCode 以外の理由で立つので、ADR 0005 を supersede せずに済む。
* Bad: (c) を残す限り Delegation の指示は 2 ファイルに割れたまま。

#### 1.1. 識別子禁止テストも残す（採用）

* Good: Claude 以外の AGENTS.md 対応ツール（Codex / Cursor / Copilot CLI 等、一次情報で確認）を試す余地が残る。
* Bad: agents.md の互換一覧に Claude Code は無く、確定事項「Claude 専用」との距離がある（critic の指摘 3.2）。
  ADR に明記して引き受ける。

#### 1.2. 識別子禁止テストは外す

* Good: Delegation の対応表を `user/AGENTS.md` に戻せ、テストが 1 件減る。
* Bad: AGENTS.md に `Agent ツール` 等が入り、他ツールで読ませる前提が崩れる。

### 2. 案 B: 構造まで畳む

* Good: ファイルが 1 つになり、Claude 固有の対応表を本文に混ぜられる。
* Bad: ADR 0005 と 0004 の一部を同時に覆すので、1 本の ADR に 2 決定が入る。
* Bad: AGENTS.md は OpenCode 専用の都合ではないため、他ツールを試した瞬間に再分割が要る。
  `tests/test_user_config.py` の 4 テストと `tests/test_install.py` の import 解決テスト、README / CLAUDE.md の
  構成図の書き換えが増える。

### 3. 案 C: 宣言と ADR だけ

* Good: 最小差分。Claude は未知キーを無視するので、残しても無害。
* Bad: 「OpenCode の設定ロードを壊す」理由のテストが ADR と食い違ったまま残り、役割を足すたびに定型が要り続ける。
  Claude の `model` / `isolation` を使いたくなったときにホワイトリスト修正が結局発生する。

### 4. Claude 公式フィールドのホワイトリスト

* Good: 任意キー（`model` / `effort` 等）のタイポも止まる。
* Bad: Claude Code のフィールド表は増え続けており、写した集合は docs 追従の手数を生む。OpenCode 由来の手数を消す
  作業の中に Claude docs 由来の手数を新設することになる（critic の指摘 3.1）。

### 5. `permissionMode` だけ禁止するブラックリスト

* Good: docs 追従不要。
* Bad: 6 と実質同じ。`disallowedTools` 必須チェックを残すなら独立した意味が無い。

### 6. キー検査を廃止し、`disallowedTools` 必須 + `permissionMode` 禁止だけ残す（採用）

* Good: 防壁キーの欠落は既存テストが止める（`fm.get("disallowedTools")` が `None` なら落ちる）。任意キーのタイポは
  「効かない」以上の被害が無い。
* Good: 役割ファイルに Claude のフィールドを自由に書ける。
* Bad: `disallowedTool`（単数）のような任意キーのタイポには気づけない。実害は「効かない」だけ。

## More Information

* supersede: [ADR 0001](0001-target-claude-code-and-opencode.md)。amend: [ADR 0004](0004-user-config-distribution-symlink-import.md)。
* 判断材料（台帳 `adr0001-sunset`、worktree `.claude/workflow-graph/adr0001-sunset/`）: designer の設計報告 `design-v1.md`、
  critic の批評 `critique-v1.md`、`/web-research` の整形結果 `research-1.md`（22〜24 件の検証済み主張、一次情報のみ）。
* 一次情報: [agents.md](https://agents.md/)（互換一覧に Claude Code / Anthropic は無い。仕様は plain Markdown で
  frontmatter / @import 無し）、[Claude Code sub-agents](https://code.claude.com/docs/en/sub-agents)（未知キーは無視、
  `disallowedTools` が先に適用）、[Claude Code memory](https://code.claude.com/docs/en/memory)（AGENTS.md は
  CLAUDE.md から `@AGENTS.md` で import する）。
* 後始末: ローカルの `~/.config/opencode/AGENTS.md` を手で消す。
