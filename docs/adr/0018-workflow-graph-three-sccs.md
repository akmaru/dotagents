---
status: accepted
date: 2026-09-23
decision-makers: akmaru
---

# ワークフローを 3 つの強連結成分としてモデル化し、SCC からの離脱は回数でなく再発で判定する

## Context and Problem Statement

普段の作業は「調査 → 案出し → ユーザーが選択 → 実装 → CI → 記録」という並びで回っているが、どこにも
明示されておらず、メインセッションが単一ノードとして全部を抱えている。`~/.claude/projects/` の全 72
セッションを集計すると、委譲は Agent 15 回（うち役割は 8 回）しか使われていない。

ここに明示的なグラフ（ノード・エッジ・共有状態）を敷きたい。決めるべきことは 2 つある。
(1) ワークフローをどの形でモデル化するか、(2) ループをどこで止めるか。

実測は「ループは正常に回っている」ことを示す。人間のターンに占める問いの比率は 33〜43%、決定 1 件あたり
1〜8 往復。CI では `test (ubuntu26.04)` が 8 回 fail し 4 回 pass している。レビューも独立に存在し、
`git diff --stat` 23 回・`gh pr create` 21 回・`gh pr checks` 19 回が記録されている。
つまり止めるべきなのは「回ること」ではない。

## Decision Drivers

* 往復は正常なので、回数上限で切ると作業そのものが止まる（実測 1〜8 往復、CI は同一ジョブを 8 回）
* 同じ議論を繰り返さない。却下した案と判断軸を残す（[ADR 0015](0015-memory-ingestion-path.md) と同じ動機）
* メインセッションのコンテキストを無駄に消費しない（[ADR 0013](0013-context-budget-monitoring.md)）
* Claude Code と OpenCode の両方で成立すること（[ADR 0001](0001-target-claude-code-and-opencode.md)）
* 委譲は「ユーザーが役割名で指示したときだけ」という現行のドッグフーディング制約を壊さない
  （[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)）
* 実験的機能や外部ランタイムに基盤を依存させない
* 個人用途なので運用の手数を増やさない

## Considered Options

1. グラフを明示しない（現状維持）
2. 直線パイプライン + 差し戻しエッジに回数の上限を置く
3. 3 つの強連結成分（SCC）+ 台帳 + 「再発」による離脱
    - 3.1. 台帳を SCC ごとに 1 枚ずつ持つ
    - 3.2. 台帳をタスクにつき 1 枚へ統合する
4. 外部のグラフランタイム（LangGraph 等）に載せて自動実行する

2 と 3 は「**ループを異常とみなすか正常とみなすか**」で分かれる。3 と 4 は「**グラフを人間とモデルが読む
規約とするか、機械が実行する構造とするか**」で分かれる。

## Decision Outcome

選択: **3.1. 3 つの SCC + SCC ごとの台帳 + 再発による離脱**（採用）。

適用するルール:

- ワークフローを 3 つの SCC に分ける。**① deliberate**（`research` / `design` / `critique` / `decide`）、
  **② build**（`implement` / `verify-local` / `human-op`）、**③ review**（`verify-CI` / `差分の提示` /
  `human-review` / `fix`）。
- 3 つとも同じ形にする: **機械が回る複数ノード + 人間が判断する 1 ノード + 台帳 1 枚 + 離脱条件**。
  人間ノードは順に `decide` / `human-op` / `human-review`。
- SCC 内の戻りエッジに**回数上限を置かない**。回るのが正常。
- 離脱は「**同じものの再発**」で判定する。① は同じ軸の再訪（確定も新軸も増えない周が 2 回続いたら人間に
  確認）、② は同一原因で 2 回 fail（ベンチ未達だけは 1 回目）、③ は指摘が実装でなく設計に及んだとき。
  ② と ③ の離脱先はどちらも ①。
- 台帳は SCC ごとに 1 枚: `decisions.json`（軸 / 選択肢 / 確定・未確定 / 根拠）、
  `verify.json`（検証項目 / 種別 / pass・fail・未実行 / 直近の原因）、`review.json`（指摘 / 対応・棚上げ・却下）。
  抜ける条件はそれぞれ未確定 0 / 全項目 pass / 未対応 0。置き場は作業ツリー直下の
  `.claude/workflow-graph/<task>/`（タスク = worktree と寿命を揃える。[ADR 0020](0020-workflow-graph-control-flow.md)）。
- ① の台帳は**役割の報告末尾にある「未決事項」をそのまま使う**。書式を別に定義しない
  （[ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)）。
- エッジに載せるのは要約ではなくファイルのパス。`user/AGENTS.md` の Delegation 節の規約に従う。
  同節の「**追補は同じエージェントを再開、改訂は呼び直し**」を ① の戻りエッジのラベルとして使う。
- 永続化の行き先を分ける: 決定は `docs/adr/`、棚上げは beads、学びは Hindsight
  （`SessionEnd` hook の自動投入。[ADR 0017](0017-session-end-retain-hook.md)）。学びの投入はノードではなく
  グラフ全体の終了時副作用として扱う。
- `explainer` はどの SCC からも参照できるが状態を変えない side-car とする
  （[ADR 0016](0016-explainer-pane-transcript-digest.md)）。
- 誰がどの遷移を回すか（ワークフロー / メインセッション / hook の分担）と、② ③ の実行主体
  （`verifier` / `reviewer` 役割、`implement` は役割ファイル無し）は
  [ADR 0020](0020-workflow-graph-control-flow.md) で決める。本 ADR はグラフの形だけを決める。
- 機構と運用の詳細は [docs/design/workflow-graph.md](../design/workflow-graph.md)、図は
  [docs/design/workflow-graph.drawio](../design/workflow-graph.drawio)。

### Consequences

* Good: ノード境界が文脈境界になるので、調査・設計・批評の文脈をメインから隔離できる。
* Good: 3 つの SCC が同じ形なので、覚える規則が 1 つで済む。
* Good: 「グラフが閉じていない」のが ③ → beads → `intake` の 1 本だけになり、タスクがどこで増えるかが
  1 箇所に固定される。現在空の beads に役割が生まれる。
* Bad: 台帳 3 枚の維持コストが新たに発生する。台帳は worktree と一緒に消えるので、長期に要るものは
  `docs/` か beads へ移す手間も要る。
* Bad: 「空転 2 周」「ベンチは 1 回目で離脱」の閾値は実測に基づかない初期値である。
* Neutral: 委譲が手動指示のみという制約は変えないので、グラフは当面「人間とモデルが読む規約」として
  機能し、自動実行はされない。

### Confirmation

グラフの**形**（3 つの SCC、台帳、離脱の判定）そのものを検査するテストは無い。これは規約であり、
強制点は制御の分担を決めた [ADR 0020](0020-workflow-graph-control-flow.md) 側にある。そちらの
`tests/test_workflow_graph_hooks.py` が「抜ける条件」（`verify.json` 全 pass で PR、`review.json`
未対応 0 で merge）を hook が守ることを、`tests/test_workflows.py` が SCC ごとに 1 本のワークフローが
あることを検証する。

役割については `tests/test_user_config.py` の `TestAgentDefinition` が `user/agents/*.md` の frontmatter と
報告形式（末尾の「未決事項」）を、`test_delegation_table_lists_every_agent` が Delegation 表との整合を
検証する。

追試の予定: 次の設計タスク 1 本で台帳 3 枚を実際に作り、① の周回数・離脱が起きた回数・閾値が妥当だったかを
[docs/design/workflow-graph.md](../design/workflow-graph.md) に追記する。閾値が外れていれば本 ADR を改訂する。

## Pros and Cons of the Options

### 1. グラフを明示しない（現状維持）

* Good: 手数がゼロ。実際に 72 セッションこれで回っている。
* Bad: 単一ノードに全フェーズが載るため、調査の数千行がメインの文脈に残る。
* Bad: 同じ軸の議論が再燃しても気づけない。[ADR 0015](0015-memory-ingestion-path.md) が
  「同じ議論を繰り返さないために軸を残す」と書いたのは、この問題を一度踏んだため。

### 2. 直線パイプライン + 差し戻し回数の上限

* Good: 停止性が自明で、説明も簡単。
* Bad: **実測と矛盾する**。決定 1 件あたり 1〜8 往復、CI は同一ジョブが 8 回 fail している。
  上限 3 回で切ると通常の作業が止まる。
* Bad: 回数を数えても「同じ理由で足踏みしている」のか「毎回前進している」のかを区別できない。

### 3. 3 つの SCC + 台帳 + 再発による離脱（採用）

* Good: ループを正常とみなすので実測と整合する。
* Good: 離脱条件が「同じ軸の再訪」「同一原因の再発」「層の不一致」と、3 つとも同じ発想で揃う。
* Good: 既存資産にそのまま乗る（役割の「未決事項」= ① の台帳、Delegation の追補/改訂 = 戻りエッジ、
  beads = 棚上げ先、`docs/adr/` = 決定の永続化）。
* Bad: 台帳の維持が人手に依存する。誰も書かなければ離脱条件が判定できない。

#### 3.1. 台帳を SCC ごとに 1 枚ずつ持つ（採用）

* Good: 抜ける条件が台帳 1 枚を見るだけで判定でき、SCC の独立性が保たれる。
* Good: ① の台帳は役割の報告形式をそのまま使えるので、新たに書式を決める必要がない。
* Bad: ファイルが 3 枚になり、SCC をまたぐ往復（②→①）で 2 枚を同時に見る場面が出る。

#### 3.2. 台帳をタスクにつき 1 枚へ統合する

* Good: ファイルが 1 枚で済み、SCC をまたいでも文脈が途切れない。
* Bad: 行の意味が 3 種類混在し、「抜ける条件」を機械的に判定できなくなる。
* Bad: ① の台帳を役割の報告形式に一致させられなくなり、変換が要る。

### 4. 外部のグラフランタイムに載せて自動実行する

* Good: 遷移条件と停止性がコードとして強制され、実行ログも構造化される。
* Bad: 人間ノードが 3 つあり、そのうち 2 つ（`human-op` / `human-review`）は非同期の外部操作。
  ランタイムに載せると待ち合わせの実装が主な仕事になる。
* Bad: Claude Code / OpenCode の外に実行基盤を持つことになり、
  [ADR 0001](0001-target-claude-code-and-opencode.md) の前提と衝突する。
* Bad: 「委譲は手動指示のみ」という現在のドッグフーディング制約と真っ向から矛盾する。

## More Information

* 機構と運用: [docs/design/workflow-graph.md](../design/workflow-graph.md)、
  図: [docs/design/workflow-graph.drawio](../design/workflow-graph.drawio)
* 役割定義の形式・配布・実行形態: [ADR 0014](0014-agent-roles-dual-key-per-file-symlink.md)
* side-car の explainer: [ADR 0016](0016-explainer-pane-transcript-digest.md)、
  [docs/design/explainer-pane.md](../design/explainer-pane.md)
* 学びの永続化: [ADR 0017](0017-session-end-retain-hook.md)
* グラフエンジニアリングの出典:
  [Graph Engineering in the Era of LLM Agents (arXiv:2608.21156)](https://arxiv.org/abs/2608.21156)、
  [DEEP-JLU/Awesome-Graph-Engineering](https://github.com/DEEP-JLU/Awesome-Graph-Engineering)
* 制御の分担と ② ③ の実行主体: [ADR 0020](0020-workflow-graph-control-flow.md)
