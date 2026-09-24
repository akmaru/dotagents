---
status: accepted
date: 2026-09-23
decision-makers: akmaru
---

# グラフの制御は SCC 内を保存ワークフローが、人間ノードと SCC 間をメインセッションが担い、抜ける条件は hook で強制する

## Context and Problem Statement

[ADR 0018](0018-workflow-graph-three-sccs.md) でワークフローを 3 つの強連結成分（SCC）としてモデル化した。
残る問いは「**その遷移を誰が回すか**」である。グラフを `docs/` に書いただけでは、メインセッションは
規約を読まず、台帳は誰も書かず、抜ける条件は守られない。ADR 0018 自身が Bad に「台帳の維持が人手に
依存する」と書いている。

決めるべきことは 3 つ。(1) SCC 内の機械ノード間の周回を誰が回すか、(2) 人間ノードと SCC 間の遷移を
誰が回すか、(3) 抜ける条件をどう強制するか。あわせて、② build と ③ review の実行主体（役割）を決める。

調査で確認した制約（出典は More Information）:

* Claude Code の Dynamic Workflow（保存ワークフロー）は、スクリプトがループ・分岐・集約を回し、
  `agent(..., {agentType})` で既存の役割定義を呼べ、`schema` で JSON を返させられる。ただし
  **実行中にユーザー入力を受けられない**（"No mid-run user input"）。
* hook の `UserPromptSubmit` は毎ターン `additionalContext` を注入でき、`PreToolUse` は
  `permissionDecision: deny` でツール呼び出しを止められる。
* `tests/test_user_config.py` は `user/agents/` の**全役割**に `Edit` / `Write` の禁止を要求する。
  したがって、ファイルを編集する役割（implementer）は役割ファイルとして書けない。
* ワークフローと hook は Claude Code 専用で、OpenCode に相当機構は無い。ユーザーは 2026-09-23 に
  「Claude Code を前提にしてよい。OpenCode は当面考えない」と決めた（[ADR 0001](0001-target-claude-code-and-opencode.md)
  の見直しは別の決定として残す）。

## Decision Drivers

* グラフを「読む規約」で終わらせず、遷移と抜ける条件を機械に持たせたい
* 人間ノード（decide / human-op / human-review）は必ず人間に返る構造にしたい（[ADR 0018](0018-workflow-graph-three-sccs.md)）
* メインセッションのコンテキストに調査・設計・検証の全文を載せない（[ADR 0013](0013-context-budget-monitoring.md)）
* 「委譲はユーザーが名前で指示したときだけ」というドッグフーディング制約を壊さない（[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)）
* 既存の役割定義とテスト制約を壊さない
* グラフを使わない作業には一切干渉しない（hook を常設できる条件）
* 個人用途なので運用の手数を増やさない

## Considered Options

1. skill だけ — 規約を skill に書き、メインセッションのモデルが全遷移を手で回す
2. 保存ワークフローだけ — SCC 内をスクリプトが回し、それ以外は skill でメインに任せる（hook 無し）
3. 3 層 — SCC 内は保存ワークフロー、人間ノードと SCC 間はメイン + skill、抜ける条件は hook で強制、現在地は hook で注入
    - 3.1. ② の implement をワークフロー内の通常エージェント（役割ファイル無し）にする
    - 3.2. ② の implement を別セッション（brief + セッション間メッセージ）にする
4. Agent Teams（実験的機能）でリード agent に回させる

1 と 2 / 3 は「**誰が次に何を回すかを決めるか**」（Claude がターンごとに / スクリプト）で分かれる。
2 と 3 は「**抜ける条件を守るのが誰か**」（モデル / hook）で分かれる。

## Decision Outcome

選択: **3. 3 層 + 3.1. implement はワークフロー内エージェント**（採用。ユーザー決定 2026-09-23）。

適用するルール:

- **SCC 内は保存ワークフロー**。SCC ごとに 1 本、`user/workflows/{deliberate,build,review}.js`。
  `install.sh` が `~/.claude/workflows/<name>.js` へファイル単位で symlink し、`/deliberate` `/build`
  `/review` として呼べる。役割は `agent(..., {agentType: '<役割>'})` で呼び、台帳の行は `schema` で
  JSON として返す。役割の報告全文は `args.ledgerDir` に書かせ、最終出力には要約とパスだけを返す。
- **1 周 = ワークフロー 1 回 → 人間の判断 → 次の周**。人間ノードはワークフローの外（メインセッション）に
  置く。ワークフローが「実行中にユーザー入力を受けられない」制約を、人間ノードを SCC の硬い境界にする
  仕組みとして使う。
- **周の中の離脱はスクリプトが判定**する。`/deliberate` は同じ致命的指摘が丸ごと残る周を空転として止め、
  `/build` は同一原因 2 回 / ベンチ未達 / 設計の前提の問題で `escape_deliberate` を返す。
  周を跨ぐ判定（① の「確定も新軸も増えない周が 2 回」）はメインが台帳の差分で行う。
- **人間ノードと SCC 間はメインセッション**。規約は `packages/workflow-graph/` の skill に置く
  （常時のコンテキストは増やさない）。戻り値を台帳に書くのもメインの仕事。
- **抜ける条件は hook で強制**。`user/bin/workflow-graph-guard.sh`（`PreToolUse`, Bash）が
  `gh pr create` を `verify.json` 全 pass まで、`gh pr merge` を `review.json` 未対応 0 まで拒否する。
- **現在地は hook で注入**。`user/bin/workflow-graph-state.sh`（`UserPromptSubmit`）が
  `[workflow-graph] task=… scc=… 未確定 n / 未pass n / 未対応 n` を毎ターン 1 行注入する。
- **規約も hook で注入し、起動条件も hook で守る**（2026-09-24 追記。ユーザー決定「skill を先に叩く前提は
  嫌だ」）。同 hook がプロンプトにコマンド名を見つけたターンに skill 本文を注入し（セッションにつき 1 回）、
  `workflow-graph-guard.sh` が `Workflow` ツールの起動を `args.models` の有無で拒否する。モデルは
  ワークフロー実行中には選べないので、起動前に `AskUserQuestion` で聞き、答え（既定なら `{}`）を
  `args.models` に渡すことを機械的に要求する。
- **hook は台帳ディレクトリが無い作業に干渉しない**。台帳は `<作業ツリー>/.claude/workflow-graph/<task>/`
  （タスク = worktree と寿命を揃える。`.claude/` は gitignore 済み）。
- **② ③ の実行主体**: `verifier`（新規役割。Bash で検証コマンドを実行できる。fail の原因を
  「実装 / 設計の前提」で分類し、離脱の材料を返す）、`reviewer`（新規役割。差分を決定との整合・正しさ・
  テストで読む）。`implement` は `/build` 内の通常エージェントで**役割ファイルを作らない**。
  `critic` は変更しない。
- hook の登録は `install.sh` が「無ければ足す」（[ADR 0013](0013-context-budget-monitoring.md) と同じ扱い。
  `UserPromptSubmit` / `PreToolUse` は他ツールも書き得る配列のため deep merge に載せない）。
- 起動は「ユーザーが `/deliberate` 等を指示したときだけ」。委譲の手動指示ルールと同じ。

### なぜ implement を別セッションにしないか（3.2 を採らない理由）

別セッションの利点は「自分の pane で権限プロンプトを捌ける」「人が横に座って会話できる」の 2 つ
（[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)）。ワークフロー内エージェントにすると
implement ⇄ verify のループがスクリプトに閉じ、役割ファイル不要でテスト制約を触らずに済む。会話が要る
のは `human-op` が濃い実装（インフラ系）に限られるので、それは必要になったときに別セッション協調
プロトコルを起こす（未確定の点として残す）。

### Consequences

* Good: SCC 内の周回と離脱条件がコードになり、ADR 0018 の「台帳の維持が人手依存」が hook と schema で埋まる。
* Good: 調査・設計・検証の全文がメインの文脈に入らない（`ledgerDir` に書かれ、要約だけ返る）。
* Good: 人間ノードが構造的に飛ばせない（ワークフローの制約そのもの）。
* Good: `/workflows` の進捗表示と `journal.jsonl` が、台帳の変遷の監査証跡になる。
* Bad: Claude Code 専用。[ADR 0001](0001-target-claude-code-and-opencode.md) の前提と衝突する
  （[ADR 0017](0017-session-end-retain-hook.md) と同じ扱い）。OpenCode 側は skill と役割の手動呼び出しだけ。
* Bad: ワークフローの実行はエージェント数分のトークンを使う。`/deliberate` 1 周で 2〜4 体、
  `/review` は指摘数に比例する。
* Bad: 台帳の JSON 書式（`decisions` / `verify` / `review`）を skill・スクリプト・hook の 3 箇所が共有する。
  1 箇所を変えたら 3 箇所を揃える必要がある。
* Bad: `~/.claude/workflows/` への symlink 読み込みは公式に記述が無い。実機では効いたが、Claude Code の
  更新で壊れ得る。
* Neutral: `/deliberate` の `maxRounds` 既定 2、`/build` の backstop 6 周は安全網であり、離脱条件ではない。

### Confirmation

* `tests/test_workflows.py`: SCC ごとに 1 本（`deliberate` / `build` / `review`）あること、`meta` が最初の文で
  `name` がファイル名と一致すること、`phase()` の題名が `meta.phases` と一致すること、
  `Date.now()` / `Math.random()` / `new Date()` / `import()` を使わないこと、`agentType` が
  `user/agents/` に実在する役割であること、`args.ledgerDir` を使うことを検証する。
* `tests/test_workflow_graph_hooks.py`: 台帳が無ければ両 hook の台帳部分が黙ること、`workflow-graph-state.sh` が
  SCC と件数を注入すること、コマンド名を含むプロンプトで skill 本文をセッションにつき 1 回注入すること、
  `workflow-graph-guard.sh` が `gh pr create` を `verify.json` 未実行・fail で拒否し全 pass で通すこと、
  `gh pr merge` を `review.json` 未実行・`open` 残で拒否し 0 で通すこと、`deferred` / `rejected` を未対応に
  数えないこと、複数タスクでは最近更新されたものを見ること、4 本のワークフローを `args.models` 無し
  （`name` / `scriptPath` どちらの経路でも）で起動したら拒否し `{}` でも通すこと、同梱 `deep-research` を
  拒否することを検証する。
* `tests/test_install.py`: `test_workflow_is_linked_per_file` / `test_removes_dangling_dotagents_workflow_links_only`
  がワークフローのファイル単位 symlink を、`test_workflow_graph_hooks_added_once_and_keep_existing` が
  hook の登録が 1 回だけで既存エントリを残すことを、一時 HOME で検証する。
* `tests/test_user_config.py` の `TestAgentDefinition` が `verifier` / `reviewer` の frontmatter と報告形式を、
  `test_delegation_table_lists_every_agent` が Delegation 表との整合を検証する。
* `tests/test_skills.py` が `packages/workflow-graph/` の SKILL.md を agentskills.io spec で検証する。
* 実機（Claude Code 2.1.280）: `~/.claude/workflows/` へ symlink した 3 本がセッション中に skill 一覧へ現れた。
  `/deliberate` を `scriptPath` 指定で 1 回実行し（designer + critic、`maxRounds: 1`）、`agentType` と
  `schema` の併用、`ledgerDir` への報告の書き出しを確認した（結果は
  [docs/design/workflow-graph.md](../design/workflow-graph.md) の追試に記録する）。

## Pros and Cons of the Options

### 1. skill だけ

* Good: 機構が最少で、両ツールで動く。
* Bad: 「誰が次に何を回すかを決めるか」が Claude のターンごとの判断のままで、ADR 0018 の Bad（台帳の
  維持が人手依存）が何も埋まらない。
* Bad: 調査・設計の全文がメインの文脈に入る。

### 2. 保存ワークフローだけ

* Good: SCC 内の周回と離脱はコードになる。
* Bad: 抜ける条件（PR を出す・merge する）はモデルが台帳を見て判断するしかなく、忘れれば素通りする。
* Bad: 現在地をモデルが覚え続ける必要があり、長いセッションで失われる。

### 3. 3 層（採用）

* Good: 遷移の種類ごとに最も強い機構を当てられる。公式の比較表（Subagents / Skills は Claude が決める、
  Workflows はスクリプトが決める）と同じ切り分け。
* Good: 「実行中にユーザー入力不可」が人間ノードを硬い境界にする。設計と機構の制約が一致する。
* Bad: 機構が 3 つ（スクリプト・skill・hook）に分かれ、台帳の書式を 3 箇所で揃える必要がある。
* Bad: Claude Code 専用。

#### 3.1. implement をワークフロー内エージェントにする（採用）

* Good: implement ⇄ verify のループが 1 本のスクリプトに閉じる。役割ファイル不要でテスト制約を触らない。
* Bad: 途中で implement エージェントと会話できない。特権操作は `needs_human_op` で止まって返すしかない。

#### 3.2. implement を別セッションにする

* Good: 自分の pane で権限プロンプトを捌け、会話できる。
* Bad: ループがスクリプト化されず、人かメインが「同一原因 2 回」を数える。
* Bad: brief・セッション間メッセージ・完了通知のプロトコルを先に整備する必要があり、役割ファイルに
  するならテストの Edit / Write 禁止を primary 専用で緩める必要がある。

### 4. Agent Teams

* Good: リード agent が複数のセッションを回せる。
* Bad: 実験的・既定 OFF で、有効化すると名前付きサブエージェントが勝手にチームメイト化する副作用がある
  （[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md) の調査）。
* Bad: リードもモデルなので「誰が次を決めるか」は 1 と同じ。

## More Information

* グラフの形: [ADR 0018](0018-workflow-graph-three-sccs.md)。機構: [docs/design/workflow-graph.md](../design/workflow-graph.md)。
  メインセッション向け規約: `packages/workflow-graph/.apm/skills/workflow-graph/SKILL.md`。
* 役割定義の形式・配布: [ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)。hook の登録方式:
  [ADR 0009](0009-settings-json-merge.md)、[ADR 0013](0013-context-budget-monitoring.md)。
* Claude Code 専用機構を採った前例: [ADR 0017](0017-session-end-retain-hook.md)。
  本 ADR は [ADR 0001](0001-target-claude-code-and-opencode.md) の見直し（Claude Code 専用化）を前提とする。
  見直しは別の ADR で行い、その際に `tests/test_user_config.py` の frontmatter ホワイトリスト・`permission`
  必須・AGENTS.md の Claude 固有識別子禁止、`user/install.sh` の OpenCode 配布、AGENTS.md / CLAUDE.md の
  2 段構成（[ADR 0005](0005-agents-md-canonical.md)）が畳む対象になる。
* 一次情報: [Orchestrate subagents at scale with dynamic workflows](https://code.claude.com/docs/en/workflows)
  （"When to use a workflow" の比較表、"Behavior and limits" の "No mid-run user input"、
  "Save the workflow for reuse"）、[Hooks reference](https://code.claude.com/docs/en/hooks)
  （`UserPromptSubmit` の `additionalContext`、`PreToolUse` の `permissionDecision`）、
  バンドルの `/workflow-authoring`（`agentType` が Agent ツールと同じ registry から解決される）。
* 未確定の点: 空転 2 周・`maxRounds` 2・backstop 6 の閾値、別セッション implementer の要否、
  `~/.claude/workflows/` の symlink 読み込みの公式サポート。
