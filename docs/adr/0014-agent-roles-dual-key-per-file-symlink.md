---
status: accepted
date: 2026-09-22
decision-makers: akmaru
---

# エージェントの役割定義は user/agents/ に dual-key frontmatter で置き、ファイル単位 symlink で配り、役割ごとに既定の実行形態を定める

## Context and Problem Statement

メインセッションをオーケストレータ（ユーザーと対話する唯一の窓口）とし、調査・設計・批評などの仕事を
独立した文脈で行う役割に委譲したい。役割の定義（system prompt とツール制限）を dotagents で一元管理し、
Claude Code と OpenCode の両方で使えるようにする（[ADR 0001](0001-target-claude-code-and-opencode.md)）。

決めるべきことは 3 つある。(1) 定義ファイルの形式と、両ツールで frontmatter の書式が衝突する問題への対処、
(2) 定義の置き場所と配布方式、(3) どの役割をサブエージェント（Agent ツールのプロセス内実行）にし、
どの役割を別セッション（`claude --agent <name>`）や fork（`--resume --fork-session`）にするか。

調査で確認した制約:

* Claude Code のサブエージェントはユーザーと対話できず（`AskUserQuestion` が必ず剥奪される）、会話履歴も
  引き継がない。同じ定義ファイルを Agent ツール、`claude --agent`、fork の 3 形態で使える。
* OpenCode は frontmatter の `tools` を `{tool: bool}` オブジェクトとしてしか受け付けず、Claude 形式の
  カンマ区切り文字列や配列だとデコード失敗で設定全体のロードが止まり得る。`color` と `model` の書式も
  異なる。未知キーはエラーにならず provider options として渡される。
* APM は `.apm/agents/` を verbatim コピーするだけで frontmatter を変換しない。
* このリポジトリの `user/settings.json` は `permissions.defaultMode: auto` なので、プロンプトで
  「書き込まない」と書くだけでは防壁にならない。

## Decision Drivers

* 両ツールで同じ定義を使い、二重管理によるドリフトを避けたい（[ADR 0001](0001-target-claude-code-and-opencode.md)）
* ツール固有機能（Claude のツール制限）を失いたくない（同 ADR の decision driver）
* 編集を即時反映したい（[ADR 0004](0004-user-config-distribution-symlink-import.md) と同じ性質の個人設定）
* `defaultMode: auto` 下でも、読み取り専用の役割が書き込み・再委譲できないことをツールレベルで担保したい
* `/agents` UI のような外部ツールが書き込む場所を symlink でリポジトリに直結させない（[ADR 0009](0009-settings-json-merge.md) の教訓）
* 役割を足すたびに「サブエージェントか別セッションか」で再燃する判断基準を残したい

## Considered Options

1. ファイル形式（frontmatter）
    - 1.1. dual-key 共用: Claude 用 `disallowedTools` と OpenCode 用 `permission` を 1 ファイルに同居させ、
      書式が衝突するキー（`tools` / `color` / `model`）は禁止する
    - 1.2. 両ツール安全な最小集合（`name` / `description` / `mode`）に絞り、ツール制限を諦める
    - 1.3. Claude 専用で開始し、OpenCode 対応は後回し（[ADR 0006](0006-file-scoped-rules-claude-only.md) 型）
    - 1.4. 共通ソースから install 時に各ツール向けへ変換する（[ADR 0009](0009-settings-json-merge.md) 型）
2. 置き場所と配布
    - 2.1. `user/agents/` を `install.sh` でファイル単位 symlink
    - 2.2. `user/agents/` をディレクトリごと symlink
    - 2.3. APM パッケージ `.apm/agents/` を `apm install -g` で配布
    - 2.4. Claude プラグインの `agents/` で配布
3. 役割ごとの実行形態
    - 3.1. 既定はサブエージェント。ユーザー対話・別セッションからの会話・権限プロンプトの分離・会話履歴の
      いずれかが要る役割だけ別セッションまたは fork にする
    - 3.2. 全役割をサブエージェントにする
    - 3.3. 全役割を別セッション（Agent Teams を含む）にする

1 は「衝突するキーをどう扱うか」、2 は「即時反映と外部ツールの書き込みをどう両立するか」、3 は
「役割の性質と実行形態の対応」の軸で分かれる。

## Decision Outcome

選択: **1.1 dual-key 共用 + 2.1 ファイル単位 symlink + 3.1 既定サブエージェント**。

- 定義は `user/agents/<name>.md`。`.md` 以外は置かない（description の無い `.md` は Claude がスキップし
  OpenCode は agent として読むため、役割定義以外を混ぜない）。
- frontmatter のホワイトリストは現時点で `name` / `description` / `mode` / `disallowedTools` / `permission`
  / `initialPrompt`。原則は「両ツールで形が衝突するキーは禁止、片方の固有キーは同居可。追加時は OpenCode の
  provider options への流出が拒否されないことを確認してから足す」。`name` はファイル名と一致させる
  （OpenCode は `name` で ID を上書きする）。
- 読み取り専用の役割は `disallowedTools: [Edit, Write, NotebookEdit, Agent]` と
  `permission: {edit: deny, task: deny}` を必ず持つ。`permissionMode` は書かない（`auto` 下では無視され、
  セッション間で権限クラスが割れる原因になる）。
- `install.sh` は `~/.claude/agents/<name>.md` へファイル単位で symlink する。同名の実ファイルは
  `~/.claude/agents.pre-dotagents/` に退避し、dotagents 由来の壊れたリンクだけ掃除する。OpenCode
  （`~/.config/opencode/agents/`）への配布は、未知キーの provider 流出を実機で検証してから足す。
- 役割と既定の実行形態:

  | 役割 | 既定 | 理由 |
  |---|---|---|
  | `researcher` | サブエージェント | 一発の報告で足りる。履歴・対話不要 |
  | `designer` | サブエージェント | 独立文脈がアンカリング回避になる |
  | `critic` | サブエージェント | 独立文脈そのものが価値 |
  | `explainer` | 常駐の別セッション | 対話と会話履歴が必須（[ADR 0016](0016-explainer-pane-transcript-digest.md)） |
  | `implementer`（拡張点） | 別セッション（worktree 付き） | 編集の権限プロンプトを自分の pane で処理したい |
  | `verifier`（拡張点） | サブエージェント（Bash 可、書き込み不可） | 結果は要約で十分 |

  判断基準は「ユーザーが直接会話したいか / メイン以外のセッションが会話したいか / 権限プロンプトと作業場所を
  分離したいか / 会話履歴そのものが要るか」の 4 つで、どれも満たさなければサブエージェント。
- ドッグフーディング中、オーケストレータは**ユーザーが役割名で指示したときだけ**委譲する（自動委譲の
  閾値を計測してから決める）。指示は `user/AGENTS.md` の Delegation 節に書き、Claude 固有のツール名は
  `user/CLAUDE.md` に分離する（[ADR 0005](0005-agents-md-canonical.md) と同じ規則）。
- 別セッション協調（brief ファイル + セッション間メッセージ + 完了通知）のプロトコルは、使う役割が
  `implementer` として実際に増えるまで AGENTS.md に書かず、拡張点として本 ADR に留める。

### Consequences

* Good: 1 ファイルで両ツール対応とツール制限を同時に満たし、[ADR 0001](0001-target-claude-code-and-opencode.md)
  の「固有機能を失いたくない」との緊張が消える。変換層も不要。
* Good: 編集は symlink で即時反映（ただしカスタムエージェントの一覧はセッション開始時に確定するため、
  実際には Claude Code の再起動または再 resume が要る）。
* Good: `/agents` UI が書いた定義はローカルに留まり、リポジトリにも OpenCode にも漏れない。
* Bad: `disallowedTools` はツールを剥がすだけで、Bash 経由の書き込み（`echo > file`）は防げない。読み取り
  専用はツール制限とプロンプト制約の二段で担保する。
* Bad: OpenCode 側は未検証（ローカルに未インストール）。未知キーが provider に拒否される場合は、install 時に
  Claude 固有キーを剥いだコピーを OpenCode に置く（1.4）か、Claude 専用に後退する（1.3）。
* Bad: 汎用名（`critic` 等）は他リポジトリの `.claude/agents/` の同名定義に上書きされ得る（project > user）。
* Neutral: 役割定義（`user/`）とスキル（`packages/`）が別の層に置かれる。「独立文脈が価値なら役割、
  ユーザーとの往復が要るならスキル」で使い分ける。

### Confirmation

* `tests/test_user_config.py` の `TestAgentDefinition` が、`user/agents/*.md` の frontmatter がホワイトリスト
  内であること、`name` がファイル名と一致すること、`disallowedTools` と `permission` が書き込み・再委譲を
  塞いでいること、報告形式に「未決事項」があることを検証する。同ファイルの
  `test_delegation_table_lists_every_agent` が全役割が AGENTS.md の Delegation 表に載ることを、
  `test_agents_md_has_no_claude_specific_identifiers` が AGENTS.md に Claude 固有の識別子が無いことを検証する。
* `tests/test_install.py` の `test_agent_definition_is_linked_per_file` がファイル単位 symlink であること、
  `test_preserves_pre_existing_agent_file` が同名の実ファイルを退避すること、
  `test_removes_dangling_dotagents_agent_links_only` が dotagents 由来の壊れたリンクだけを掃除することを
  一時 HOME で検証する。
* 実機: `claude --agent <name>` および Agent ツールで `disallowedTools` が効くことを `claude -p` の使い捨て
  プロジェクトで確認済み（2.1.278）。

## Pros and Cons of the Options

### 1.1. dual-key 共用（採用）

* Good: 両ツールで読める 1 ファイルのまま Claude のツール制限が効く（実機確認済み）。
* Good: 変換層が不要で、APM 経由でも壊れない。
* Bad: OpenCode 側で未知キーが provider に拒否される可能性が未検証。

### 1.2. 最小集合に絞りツール制限を諦める

* Good: 両ツールで確実に読める。
* Bad: `defaultMode: auto` 下では読み取り専用がプロンプト頼みになり、ドッグフーディング期間に最も要る
  ツール制限を失う。`isolation` 等を使う `implementer` を将来定義できない。

### 1.3. Claude 専用で開始

* Good: Claude の全フィールドを自由に使える。
* Bad: [ADR 0006](0006-file-scoped-rules-claude-only.md) の状況（OpenCode に対応物が無い）と違い、
  OpenCode には対応物（`permission`）があるので、同居できるのに諦める理由が無い。

### 1.4. install 時に変換

* Good: 各ツールの機能をフルに使える。
* Bad: bash + jq で YAML frontmatter を書き換えるのは脆く、OpenCode 未導入の今は検証できない変換器を
  書くことになる。1.1 が否になったときのフォールバックとして残す。

### 2.1. ファイル単位 symlink（採用）

* Good: 編集即時反映。`/agents` UI の書き込みがリポジトリに入らない。Claude がファイル symlink を読むことは
  実機確認済み。
* Bad: リポジトリ側で消した役割のリンクを掃除する処理が要る。

### 2.2. ディレクトリごと symlink

* Good: 処理が最も単純。
* Bad: `/agents` UI が `tools: Read, Grep` 形式で書いたファイルがリポジトリに入り、OpenCode へ配ると設定全体を
  壊す。[ADR 0009](0009-settings-json-merge.md) と同型の問題。

### 2.3. APM `.apm/agents/` で配布

* Good: 他リポジトリ・他人に配れる。
* Bad: verbatim コピーなので編集のたびに push → install が要る（[ADR 0004](0004-user-config-distribution-symlink-import.md)
  が `user/` で退けた理由そのもの）。公開したくなったら symlink の参照先を `packages/` 内へ向ければよい。

### 2.4. Claude プラグインで配布

* Bad: Claude 専用で `<plugin>:<name>` の接頭辞が付き、`permissionMode` 等が無視され、反映に
  `/reload-plugins` が要る。

### 3.1. 既定サブエージェント + 例外基準（採用）

* Good: 要約だけが戻るサブエージェントが最も安く、メインがユーザーの唯一の窓口という前提を守れる。
* Good: サブエージェントのトランスクリプトは永続化され再開できるので、寿命は判断基準にならない。
* Bad: 別セッションが要る役割（explainer）は起動の仕組みを別途持つ。

### 3.2. 全役割をサブエージェント

* Bad: 解説役はユーザー対話と会話履歴が無いと成立しない。

### 3.3. 全役割を別セッション

* Bad: idle セッションへのメッセージ配送はフルコンテキストのターンを起こしコストが高い。Agent Teams は
  実験的で、名前付きサブエージェントが勝手にチームメイト化する副作用がある。

## More Information

関連: [ADR 0001](0001-target-claude-code-and-opencode.md)（両ツール対応）、
[ADR 0004](0004-user-config-distribution-symlink-import.md)（`user/` の symlink 配布。本 ADR はその延長だが、
外部ツールが書き込む場所なのでファイル単位にする）、[ADR 0005](0005-agents-md-canonical.md)（AGENTS.md と
CLAUDE.md の分離）、[ADR 0006](0006-file-scoped-rules-claude-only.md)（Claude 専用にした先例。本件は OpenCode に
対応物があるため判断基準が異なる）、[ADR 0009](0009-settings-json-merge.md)（外部ツールの書き込みと symlink）、
[ADR 0016](0016-explainer-pane-transcript-digest.md)（explainer の実行形態）。

参考: [Claude Code sub-agents](https://code.claude.com/docs/en/sub-agents)、
[OpenCode agents](https://opencode.ai/docs/agents/)、[cross-session messaging](https://code.claude.com/docs/en/cross-session-messaging)。
設計書: [docs/design/explainer-pane.md](../design/explainer-pane.md)。
