# ワークフローグラフ（3 つの強連結成分）

普段の作業を、ノード（仕事）・エッジ（遷移条件）・エッジ上を流れる共有状態として明示したもの。
グラフの形は [ADR 0018](../adr/0018-workflow-graph-three-sccs.md)、制御の分担（誰が遷移を回すか）は
[ADR 0020](../adr/0020-workflow-graph-control-flow.md)、図は
[workflow-graph.drawio](workflow-graph.drawio)（draw.io で開く）。役割定義の形式と配布は
[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)。
本書は機構の説明で、メインセッション向けの運用規約は `packages/workflow-graph/` の SKILL.md にある
（2026-09-23 時点）。

**グラフエンジニアリング**（graph engineering）= 複数のエージェント・ループ・検証器・人間を明示的な
グラフとして設計する層。プロンプトエンジニアリング（1 回の入力）やコンテキストエンジニアリング
（1 モデルが何を見るか）を置き換えるものではなく、それらを束ねる上位の層を指す。
出典: [Graph Engineering in the Era of LLM Agents (arXiv:2608.21156)](https://arxiv.org/abs/2608.21156)、
[DEEP-JLU/Awesome-Graph-Engineering](https://github.com/DEEP-JLU/Awesome-Graph-Engineering)。

## 根拠（実測）

`~/.claude/projects/` の全 72 セッション（12 プロジェクト、51MB）を集計した結果に基づく。
再現手順は末尾の「測り直し方」。

| 観測 | 値 | グラフ上の意味 |
|---|---|---|
| ツール実測 | Bash 1733 / WebFetch 126 / WebSearch 29 / Read 42 / Write 14 / Edit 10 | 「調べる・決める・設定する・記録する」が主。コードを書く量は少ない |
| 委譲 | Agent 15 回（researcher 4 / designer 2 / critic 2 / その他 7） | 実質ほぼ単一ノードで全部を回していた |
| 人間ターンに占める問い | 33〜43%、決定 1 件あたり 1〜8 往復 | ① は一点でなく**滞在する領域** |
| Monitor 13 回 | CI 監視 7 / ローカル検証 6 | 検証が 2 種類・2 箇所にある |
| CI 結果イベント | `test (ubuntu26.04)` fail 8 / pass 4 | ② も回る。しかも**同じ項目が繰り返し落ちる** |
| 差分提示系 | `git diff --stat` 23 / `git diff main` 11 / `git show` 8 | ③ は既に独立フェーズとして存在する |
| PR 系 | `gh pr create` 21 / `gh pr checks` 19 / `gh pr merge` 16 | ②→③ の境界は PR |
| beads | `br list --status=open` が空 | タスクグラフの実体が無い |

① を実際に 1 周半回した記録が
[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md) の検討時にある:
`researcher ×3 → designer v1 → critic v1 → designer v2（+追補）→ critic v2 → decide → 実装`。

## 用語

| 語 | 意味 |
|---|---|
| **強連結成分**（SCC: strongly connected component） | 互いに行き来できるノードの集合。本グラフでは ①②③ の 3 つ |
| **台帳** | SCC ごとに 1 枚だけ持つ共有状態ファイル。エッジに載るのは要約ではなくこのファイルのパス |
| **戻りエッジ** | SCC 内でノード間を戻る遷移。**回るのが正常**なので回数上限を置かない |
| **離脱エッジ** | SCC から出る遷移。回数ではなく「**同じものの再発**」で判定する |

## 全体像

```
要望 ─▶ intake ─┬─(調査・設計が要る)─▶ ① deliberate ─(未確定 0)─▶ record/ADR ─┐
                └─(自明・定型)──────────────────────────────────────────────┐ │
                                                                           ▼ ▼
他人の MR/PR ───────────────────────────┐                            ② build
                                        │                                 │
                        ③ review ◀──────┴── commit/push/PR ◀──(全項目 pass)┘
                           │
              (未対応 0)───┴──▶ merge ─▶ 完了
```

離脱エッジ（赤点線、図を参照）: `② ─▶ ①`（同一原因で 2 回 fail / ベンチ未達）、
`③ ─▶ ①`（指摘が設計に及ぶ）、`③ ─▶ beads`（棚上げ）→ `beads ─▶ intake`（新しいタスク）。
**グラフが閉じていないのはこの beads 経由の 1 本だけで、ここだけがノードを自己増殖させる。**

## 3 つの SCC は同じ形をしている

どれも「機械が回る複数ノード + **人間が判断する 1 ノード** + 台帳 1 枚 + 離脱条件」。

| | ① deliberate | ② build | ③ review |
|---|---|---|---|
| 人間ノード | `decide` | `human-op` | `human-review` |
| 機械ノード | `research` / `design` / `critique` | `implement` / `verify-local` | `verify-CI` / `差分の提示` / `fix` |
| 台帳 | `decisions.json` | `verify.json` | `review.json` |
| 台帳の行 | `confirmed` / `open`（軸 / 質問 / 選択肢） | `items`（項目 / 種別 / pass・fail / 原因 / 層） | `items`（指摘 / file:line / open・fixed・deferred・rejected） |
| 回すもの | `/deliberate` | `/build` | `/review` |
| 抜ける条件 | `open` が 0 | 全項目 pass（`gh pr create` を hook が守る） | `open` が 0（`gh pr merge` を hook が守る） |
| 離脱の判定 | **同じ軸の再訪**: 確定も新軸も増えない周が 2 回続いたら人間に確認 | **同一原因の再発**: 同じ項目が同じ原因で 2 回 fail → ① へ。ベンチ未達は 1 回目で ① へ | **層の不一致**: 指摘が実装でなく設計に及ぶ → ① へ |

### ① deliberate

`research → design → critique → decide` と、`decide` からの 2 本の戻り。

| 戻りエッジ | 引き金の例 | 委譲の扱い |
|---|---|---|
| `decide → research` | 「案 2 のヘルプはどういう意味なの？」「daemon はログオフでは止まらないよね？」 | 同じ researcher を `SendMessage` で**再開**（追補） |
| `decide → design` | 「AWS 常にホストする案はどうだろう？」「ID 連携を使えば API キー不要と言われた」 | designer を**呼び直す**（改訂。軸が増えた = 別版） |
| `decide → decide` | 「まず永続化は API のみは決定。永続化については少し掘り下げたい」 | 委譲なし。台帳を部分確定に更新するだけ |

役割の報告は**末尾が必ず「未決事項（質問 + 選択肢 2〜4 個）」**で終わる（[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)）。
これが `decisions.json` の `open` 行にそのまま対応するので、台帳の書式を別に定義する必要はない。
`/deliberate` は designer / critic の未決事項を `schema` で JSON として受け取り、`open` に併合して返す。

**research ノードの実装は小問の種別で分かれる。**

| 種別 | 実装 | 向く問い |
|---|---|---|
| `codebase` | `researcher` 1 体（`agentType`） | このリポジトリ・ローカルの事実。ADR・テスト・特定ツールの仕様をバージョン固定で |
| `web` | `/web-research`（同梱 `/deep-research` の写し。段階ごとにモデル固定）を `workflow()` で 1 段ネスト呼び出し → 結果を軽いエージェントが researcher の報告形式に整形 | 外部ツール・技術の仕様や比較。出典同士が食い違う問い |

web-research は Scope → Search（5 角度並列）→ Fetch（最大 15 出典）→ Verify（主張ごと 3 票の反証）→
Synthesize の 5 段で、1 回に最大 100 体近くを回す。同梱の `/deep-research` は `agent()` に `model` を
渡さないためセッションのモデルで全段階が動く。それだけを変えるために `user/workflows/web-research.js` に
写しを置き、既定を全段階 opus にした（他は同梱版と同一に保ち、Claude Code 更新時に差分を追えるようにする）。
`maxDeepResearch`（既定 0）で本数を抑え、超過分は researcher で代替する。

小問は 2 経路で入る。(1) main が `args.researchQuestions` で事前に渡す、(2) designer が 1 周目に
「案を比べるのに足りない事実」を `researchNeeded`（案 / 小問 / 種別）で返し、同じ周で並列に調べて
designer が改訂する。(2) は `decide → research` の戻りのうち人間を介さず済む分を先回りするもので、
decide に届く `open` を減らすのが狙い（効果は未測定）。

確定済みの軸は再オープンしない。次のノードへ渡すときは「確定済み」と明記する
（`user/AGENTS.md` の Delegation 節の規約そのもの）。

### ② build

`implement ⇄ verify-local` と `implement ⇄ human-op`。

`verify-local` の項目には**種別**（テスト / ベンチ / 起動確認）を持たせる。性能は設計の帰結なので、
**ベンチ未達だけは 1 回目で ① へ戻す**。テストは同一原因 2 回で戻す。

`human-op` は人間が手で実行する特権・対話操作（`aws sso login`、`terraform apply`、keychain 登録、
daemon 起動、ブラウザ確認）。結果を貼り戻して `implement` に戻る。

ローカルで再現できない検証項目（例: CI 固有の OS マトリクス）は `/build` の `checks` に入れず、
③ の `verify-CI` に委ねる。

`implement` は `/build` の中の通常のワークフローエージェント（役割ファイル無し。`tests/test_user_config.py`
が全役割に Edit / Write の禁止を要求するため、編集する役割は役割ファイルにできない）。この作業ツリーで
直接編集し、commit はしない。`human-op` が要ると分かった時点で `needs_human_op` を返して止まる。

### ③ review

`verify-CI → 差分の提示 → human-review` と、`human-review` からの 2 本の戻り。

`human-review` の指摘は 3 分岐する。

| 分岐 | 行き先 | 実例 |
|---|---|---|
| 今直す | `fix` → `verify-CI` | 「`import re` の件は直して」 |
| 人間が自分で直す | `human-op` → `verify-CI` | 「5 は確認して変更しておいた」 |
| 棚上げ | beads issue（新しいタスクノード） | 「2 は承認した気がするけど、状況確認してほしい」 |
| 却下 | 台帳に理由付きで記録して閉じる | — |

**③ は単独の入口も持つ**。他人の MR / PR のレビュー依頼は `intake` から ③ に直接入り、
`merge` へは行かず指摘を出して終わる。`差分の提示` は `/review` の中の `reviewer` 役割が担い、
「止める / 直す」の指摘は 1 件ずつ反証エージェントにかけて誤検知を落としてから人間に渡す。

## side-car: explainer

`explainer` は常駐 pane の別セッションで、どの SCC からも参照できるが**グラフの状態を変えない**
（観測のみ）。実測で問いの 3〜4 割が「用語・意味の確認」なので、ここを逃がすと ① の
`decide → research` 往復が減るはずだが、効果は未測定。機構は
[docs/design/explainer-pane.md](explainer-pane.md)、決定は
[ADR 0016](../adr/0016-explainer-pane-transcript-digest.md)（proposed、段階 1b は未着手）。

## 状態の置き場所

| 層 | 置き場所 | 寿命 |
|---|---|---|
| 台帳と報告 | `<作業ツリー>/.claude/workflow-graph/<task>/`（`*.json` と `research-N.md` / `design-vN.md` / `critique-vN.md` / `implement-rN.md` / `verify-rN.md` / `review-v1.md`） | タスク = worktree。セッションを跨いで残り、worktree と一緒に消える。`.claude/` は gitignore 済み |
| 決定 | `docs/adr/NNNN-*.md` | 永続。`record` ノードの出力 |
| タスク | beads（`.beads/`） | 永続。棚上げで増える |
| 学び | Hindsight | 永続。`SessionEnd` hook が自動投入（[ADR 0017](../adr/0017-session-end-retain-hook.md)） |

台帳は worktree と寿命を共にするので、長期に要るものは `docs/` か beads に移してから worktree を消す。
学びの投入はグラフ上のノードではなく、**グラフ全体の終了時副作用**として扱う。

## 制御の分担（ADR 0020）

グラフの遷移は 2 種類あり、それぞれ最も強い機構に持たせる。

| 遷移 | 制御の主体 | 機構 | 置き場 |
|---|---|---|---|
| SCC 内（機械ノード間の周回） | スクリプト | 保存ワークフロー `/deliberate` `/build` `/review`。役割は `agent(..., {agentType})` で呼び、台帳の行は `schema` で JSON として返す | `user/workflows/*.js` → `~/.claude/workflows/`（ファイル単位 symlink） |
| 人間ノードと SCC 間 | メインセッション | `workflow-graph` skill の規約に従い、`AskUserQuestion` で人間に聞き、戻り値を台帳に書く | `packages/workflow-graph/.apm/skills/workflow-graph/SKILL.md` |
| 抜ける条件の強制 | hook | `PreToolUse`（Bash）: `gh pr create` は `verify.json` 全 pass、`gh pr merge` は `review.json` 未対応 0 を要求 | `user/bin/workflow-graph-guard.sh` |
| 現在地の把握 | hook | `UserPromptSubmit`: 台帳の件数を毎ターン 1 行注入 | `user/bin/workflow-graph-state.sh` |

ワークフローは**実行中にユーザー入力を受けられない**（[公式](https://code.claude.com/docs/en/workflows#behavior-and-limits)）。
この制約が人間ノードを SCC の硬い境界にする。1 周 = ワークフロー 1 回 → 人間の判断 → 次の周。
`/deliberate` は「同じ致命的指摘が丸ごと残る周」を空転として自分で止め、`/build` は「同一原因 2 回 /
ベンチ未達 / 設計の前提の問題」で離脱を返す。周を跨ぐ判定（① の「確定も新軸も増えない周が 2 回」）は
main が台帳の差分で行う。hook は台帳ディレクトリが無い作業には一切干渉しない。

## 委譲の規約との対応

SCC の内側では保存ワークフローが `agent(..., {agentType: '<役割>'})` で役割を呼ぶ。渡すものは
`user/AGENTS.md` の Delegation 節のとおり（目的・制約・関連ファイルの絶対パス・先行報告のパス・
確定済み事項の明示）で、スクリプトがプロンプトに組み立てる。役割の報告全文は `ledgerDir` に書かせ、
最終出力には要約とパスだけを返させる（main の文脈に全文を載せない）。
**追補は同じエージェントを再開、改訂は呼び直し**という既存の区別は、`/deliberate` では
「designer の改訂は新しい `agent()` 呼び出し」として現れる。

SCC の外で役割を単発で呼ぶときは従来どおり `Agent` ツールの `subagent_type`。
委譲もワークフローの起動も「ユーザーが名前で指示したときだけ」（閾値計測のためのドッグフーディング中）。
本グラフはその制約を変えない。

## 役割と実行主体の対応

| ノード | 実行主体 | モデル（既定） |
|---|---|---|
| intake / decide / record / human-op / human-review / merge / beads | メインセッション（skill の規約） | セッション |
| research（codebase） | `researcher`（`/deliberate` 内） | opus |
| research（web） | `/web-research` の 5 段階（`/deliberate` から 1 段ネスト） | 全段階 opus |
| web-research 結果の整形 | `/deliberate` 内の通常エージェント | haiku |
| design / critique | `designer` / `critic`（`/deliberate` 内） | セッション継承 |
| implement / fix | `/build` 内の通常エージェント（役割ファイル無し。この worktree で編集） | sonnet |
| verify-local、CI が落ちたときの原因切り分け | `verifier`（`/build` 内、または単発） | sonnet |
| 差分の提示 | `reviewer`（`/review` 内） | セッション継承 |
| 指摘の反証 | `/review` 内の通常エージェント（指摘 1 件につき 1 体） | sonnet |
| explainer | 常駐セッション（未実装。[ADR 0016](../adr/0016-explainer-pane-transcript-digest.md)） | — |

モデルは**呼び出しごと**に `agent(..., {model})` で指定する（優先度 1 位。
[Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model)）。役割ファイルの `model:` は
`tests/test_user_config.py` が禁止しているため使えない（[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)。
ADR 0001 の見直しで外れる制約の 1 つ）。既定は各スクリプトの `MODELS` にあり、`args.models` で部分上書きできる。
判断が結果を左右するノード（design / critique / reviewer）はセッション継承、決定どおりに書く・実行する・
1 件を判定するノードは sonnet、機械的な整形は haiku。同梱の `/deep-research` は `model` を渡していないため
セッションのモデルで 100 体前後が回る（2026-09-23 の追試で全 206 体が Fable 5.1 だった）。これが
`/web-research` を写しとして持つ理由。

`verifier` の Bash は検証コマンドの実行を許す（他の役割は読み取り専用）。役割の `disallowedTools` は
Bash 経由の書き込みを防げないので、起動前後の `git status --short` の一致を報告させて検知する。

## 未確定の点

- **空転 2 周という閾値**、`/deliberate` の `maxRounds` 既定 2、`/build` の backstop 6 周は実測に基づかない
  初期値。数タスク回してから見直す。
- **別セッションの implementer**（人が横に座って会話する形）は作っていない。`human-op` が濃い実装
  （インフラ系）で必要になったら、[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md) の
  別セッション協調プロトコルを起こす。
- ワークフローと hook は Claude Code 専用。OpenCode 側の対応は
  [ADR 0001](../adr/0001-target-claude-code-and-opencode.md) の見直しに委ねる。

## 追試の記録

### 2026-09-23: `/deliberate` を 1 周（task `adr0001-sunset`、Claude Code 2.1.280）

対象: ADR 0001 を supersede して Claude Code 専用にするとき何をどの順で畳むか。
`researchQuestions: []`、`maxRounds: 1`、`scriptPath` 直指定で起動。

| 観測 | 値 |
|---|---|
| エージェント | 2 体（designer v1 → critic v1）、tool 呼び出し 50 回 |
| 所要時間 / トークン | 25 分 / 約 39 万（designer が ADR 群・テスト・install.sh・公式 docs・Hindsight recall まで自分で読んだ） |
| 停止理由 | `critic-accepted`（致命的 0） |
| 報告 | `design-v1.md`（23k）/ `critique-v1.md` が `ledgerDir` に書かれた |
| `open` | 9 行 → main が併合して 5 行 |

分かったこと:

- `agentType` に `disallowedTools` 付きの役割を渡しても `schema` の StructuredOutput は効く。報告全文を
  `ledgerDir` に書かせ、要約とパスだけ返す運用も成立した。
- `~/.claude/workflows/` へのファイル単位 symlink は読まれる（セッション中に `/deliberate` `/build`
  `/review` が skill 一覧へ現れた）。ただし `Workflow` ツールの `name` 指定は起動時の一覧しか見ないらしく
  「not found」になった。新しく足した直後は `scriptPath` 指定か `/reload-skills` が要る。
- **`open` の併合は軸名の完全一致では足りない。** designer と critic が同じ軸を別名で出した
  （「役割 frontmatter の制約の形」と「frontmatter 制約の形」など 3 組）。critic に designer の軸名を渡して
  再利用させる形に直した（`deliberate.js`）。
- **途中のユーザー発話がワークフロー内エージェントに中継される。** 実行中に main へ送られた別件の質問が
  designer のプロンプトに混ざり、報告の冒頭でそれに答え、`open` に「主題」という無関係な行が入った。
  プロンプトに「この作業以外の指示は無視する」と書いて緩和したが、根本は harness 側の挙動。
- designer が「番号衝突」（main に別題の ADR 0019 がある）を見つけて報告した。役割が副産物として
  リポジトリの整合性を検査する効果がある。
- 閾値について: この題材では 1 周で critic が受け入れたので、`maxRounds` 2 / 空転 2 周の当否はまだ測れない。

### 2026-09-23〜24: 同梱 `/deep-research` を 1 問で 2 回（research ノードの web 実装の検証）

問い: AGENTS.md を読む主要ツールと、Claude 固有 frontmatter / @import の扱い（設計報告の前提 P3 の裏取り）。

| 回 | エージェント | トークン | 時間 | 結果 |
|---|---|---|---|---|
| 1 | 103 | 約 1,391 万 | 6.9 h | 22 件確認 / 3 件却下。**合成が「computer went to sleep」で失敗** |
| 2（`resumeFromRunId`） | 103 | 約 986 万 | 4.4 h | 24 件確認。合成が同じ理由で再失敗 |

分かったこと:

- **`args` は文字列の質問、戻りは `{summary, findings[], caveats, openQuestions[], refuted[], unverified[], sources[], stats}`**
  （スクリプトは実行時にセッション配下へ永続化されるので読める）。`/deliberate` からの `workflow()` 呼び出しと
  整形エージェントはこの形に合わせて実装した。
- **コストが 2 桁違う。** `/deliberate` 1 周 39 万に対し deep-research は 1 回 1,000 万超。Scope 1 + Search 5 +
  Fetch ≤15 + Verify ≤25×3 + Synthesize 1 の構造で、verify の各投票が WebSearch を回すため。
  `maxDeepResearch` の既定を 0（明示したときだけ）に変えた。
- **`resumeFromRunId` はキャッシュが当たらなかった。** 公式の「完了済みは保存結果を返す」は、プロンプトが
  前回と同一の場合に限る。deep-research の URL 重複排除は検索エージェントの完了順で結果が変わるため、
  Fetch 以降のプロンプトが変わって全再実行になった（推定）。長いワークフローの再開は前提にしない。
- **PC のスリープで末尾の合成が落ちる。** 数時間かかるワークフローはスリープ抑止（`caffeinate`）が要る。
  検証済みの主張は `journal.jsonl` と task output に残るので、合成だけ main が手で行い
  `research-1.md` にまとめた。
- 内容としては、agents.md の互換一覧に Claude Code が無いこと（3 票一致）、AGENTS.md 仕様に frontmatter /
  @import が無いこと、Codex / Gemini CLI / Cursor / Copilot CLI の読み込み位置が一次情報で確認できた。
  ADR 0001 見直しの decide に使える。

## 測り直し方

本書の「根拠」節の数字は次で再現できる（`jq` が要る）。

```sh
cd ~/.claude/projects

# ツール別の呼び出し回数
find . -name '*.jsonl' -exec cat {} + \
  | jq -r 'select(.message.content!=null) | .message.content
           | if type=="array" then .[] | select(.type=="tool_use") | .name else empty end' \
  | sort | uniq -c | sort -rn

# Monitor で何を監視しているか（CI かローカルか）
find . -name '*.jsonl' -exec cat {} + \
  | jq -r 'select(.message.content!=null) | .message.content
           | if type=="array" then .[] | select(.type=="tool_use" and .name=="Monitor") | .input.description else empty end' \
  | sort | uniq -c | sort -rn

# CI の pass/fail イベント
find . -name '*.jsonl' -exec cat {} + \
  | grep -oE '(test|build|check|lint)[^"]{0,30}: (pass|fail)' | sort | uniq -c | sort -rn

# git / gh サブコマンドの内訳
find . -name '*.jsonl' -exec cat {} + \
  | jq -r 'select(.message.content!=null) | .message.content
           | if type=="array" then .[] | select(.type=="tool_use" and .name=="Bash") | .input.command else empty end' \
  | grep -oE '\b(git|gh) [a-z-]+( [a-z-]+)?' | sort | uniq -c | sort -rn
```

人間のターンだけを数えるときは `type=="user"` かつ `isSidechain != true` かつ `isMeta != true` に絞り、
`bash-stdout` / `<local-command` / `<command-message` / `<system-reminder` を含む行を除く
（貼り戻された端末出力とメタ行がユーザーターンとして記録されるため）。
