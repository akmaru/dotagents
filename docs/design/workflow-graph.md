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
| 抜ける条件・起動条件の強制 | hook | `PreToolUse`（Bash）: `gh pr create` は `verify.json` 全 pass、`gh pr merge` は `review.json` 未対応 0 を要求。（Workflow）: 4 本を `args.models` 無しで起動したら拒否、同梱 `/deep-research` は `/web-research` に誘導 | `user/bin/workflow-graph-guard.sh` |
| 規約と現在地の注入 | hook | `UserPromptSubmit`: プロンプトにコマンド名があればセッションにつき 1 回 skill 本文を注入。台帳があれば件数を毎ターン 1 行注入 | `user/bin/workflow-graph-state.sh` |

skill をユーザーが先に叩く前提は置かない（忘れる）。規約は hook が注入し、起動条件は hook が守る。
`apm install workflow-graph` は「`/workflow-graph` と打って読み直せる」ためのもので、無くても回る。

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
| research（codebase） | `researcher`（`/deliberate` 内） | opus（`researcher.md` の `model:`） |
| research（web） | `/web-research` の 5 段階（`/deliberate` から 1 段ネスト） | 全段階 opus |
| web-research 結果の整形 | `/deliberate` 内の通常エージェント | haiku |
| design / critique | `designer` / `critic`（`/deliberate` 内） | セッション継承 |
| implement / fix | `/build` 内の通常エージェント（役割ファイル無し。この worktree で編集） | sonnet |
| verify-local、CI が落ちたときの原因切り分け | `verifier`（`/build` 内、または単発） | sonnet（`verifier.md` の `model:`） |
| 差分の提示 | `reviewer`（`/review` 内） | セッション継承 |
| 指摘の反証 | `/review` 内の通常エージェント（指摘 1 件につき 1 体） | sonnet |
| explainer | 常駐セッション（未実装。[ADR 0016](../adr/0016-explainer-pane-transcript-digest.md)） | — |

モデルの決まり方は 2 段（[Choose a model](https://code.claude.com/docs/en/sub-agents#choose-a-model)）。
**役割で動くノード**は役割ファイルの `model:` が既定（`researcher.md` = opus、`verifier.md` = sonnet、他は
未指定 = セッション継承）。この frontmatter は以前 `tests/test_user_config.py` が禁止していた
（[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)）が、[ADR 0021](../adr/0021-target-claude-code-only.md)
で外れたので役割側へ移した。**役割ファイルの無いノード**（implement / integrate / refute / web-research の
各段階）は各スクリプトの `MODELS` が既定を持つ。どちらも `args.models` で渡した値が呼び出しごとの指定
（優先度 1 位）として勝つ。`tests/test_workflows.py` が「役割で動くノードのスクリプト既定は `undefined`」を、
`tests/test_user_config.py` が「`model:` の値は alias / inherit / フル ID」を検査する。
判断が結果を左右するノード（design / critique / reviewer）はセッション継承、決定どおりに書く・実行する・
1 件を判定するノードは sonnet、機械的な整形は haiku。ワークフローは実行中に人間に聞けないので、
メインセッションは**起動の直前に毎回** `AskUserQuestion` でノードごとのモデルを確認し、既定から変えた
分だけを `args.models` に渡す（規約は skill の「起動前にモデルを聞く」）。同梱の `/deep-research` は `model` を渡していないため
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
- ワークフローと hook は Claude Code 専用（[ADR 0021](../adr/0021-target-claude-code-only.md) で
  Claude Code のみをターゲットにした）。

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

### 2026-09-25: グラフを ① → record → ② → PR → ③ → merge まで通した（task `adr0001-sunset`、PR #40）

対象: ADR 0001（Claude Code と OpenCode の両対応）を supersede して Claude Code 専用にする。
hook 導入後の初回で、①〜③ のすべてのノードと 3 つの人間ノードを 1 度ずつ踏んだ。

| ノード | 実行 | 結果 |
|---|---|---|
| ① `/deliberate` | designer + critic（前日）、`/web-research`（前日） | 未確定 5 行。critic-accepted |
| decide | `AskUserQuestion` 4 問（ブランチの 1 問は状況で解消） | 確定 6 行、未確定 0 |
| record | main が ADR 0021 を書き、0001 を superseded、0004 を amended に | — |
| ② `/build` r1 | implement（sonnet）+ verifier（sonnet）、16 分、34 万トークン | `needs_human_op`。pytest pass、**検証コマンド 2 本が fail** |
| ② `/build` r2 | 検証コマンドを直して `resumeFromRunId`、3 分、20 万トークン | 全 pass |
| commit / PR | main が 3 コミットに分けて積み、`gh pr create` | guard hook が `verify.json` 全 pass を確認して通した |
| ③ `/review` | reviewer（opus）+ 反証 2 体（sonnet）、4 分、31 万トークン | 指摘 5（直す 2 / 任意 3）、反証で落ちたもの 0、「指摘対応後に可」 |
| human-review | `AskUserQuestion` 5 問（2 問は「それは何？」の聞き返しを挟んで再質問） | fixed 3 / rejected 2 |
| merge | main が直して push、CI pass、`gh pr merge` | guard hook が `review.json` 未対応 0 を確認して通した |

分かったこと:

- **hook は設計どおりに効いた。** 毎ターン `[workflow-graph] task=… scc=…` の 1 行が入り、現在地を忘れずに済んだ。
  `gh pr create` / `gh pr merge` の前に台帳が確認され、`Workflow` の起動は `args.models` 無しでは拒否される
  （今回は毎回 `AskUserQuestion` で聞いてから `{}` を渡した）。
- **② の r1 の fail は 2 件とも検証コマンド側の欠陥だった。** (1) harness の `grep` は ugrep で `./` を前置しない
  ため除外パターンが効かず、(2) `apm pack --check-clean` は外部 API の 404 で失敗した。verifier が両方を
  「設計の前提」と分類して `needs_human_op` で返し、main が原因を確かめてコマンドを直した。
  「実装の問題 / 設計の前提の問題」の分類は、この場面で正しく効いた。**検証コマンドは `git grep`
  （追跡ファイルのみ、gitignore 尊重）で書く**のが教訓。
- **`resumeFromRunId` はここでは効いた。** `checks` を変えると implement のプロンプトも変わるので implement も
  再実行されたが、「実装済みなら差分を確認するだけ」と指示したので 3 分で済んだ。
- **③ の反証で落ちた指摘は 0 件。** reviewer（opus）の 5 件はすべて実在した。うち 2 件は「ADR 0021 で外れた
  制約を、設計書と SKILL.md がまだ『禁止』と書いている」で、ADR の Confirmation の grep が `opencode` しか
  探さないため漏れたもの。決定の帰結（何が可能になったか）は語で grep できないので、reviewer の
  「決定との整合」観点が要る。
- **human-review で「それは何？」が 2 回出た。** `review.json` の `what` は reviewer の言葉のままで、
  人間には前提（「役割ファイル」= `user/agents/*.md`）が抜けていた。指摘を人間に見せるときは
  main が用語と背景を補ってから聞く。
- **棚上げ先が無かった。** `br`（beads_rust）がこのマシンに無く、`bd`（別実装）は別形式の DB を作るので
  使えない。apm の 404 は `review.json` の `deferred` に留めた。beads を使うなら `br` を入れる。
- `bd` を試したときに `.beads/` 配下に別実装の成果物（`embeddeddolt/` 等）ができた。消して戻した。

### 2026-09-25: 2 本目（task `explainer-pane`、PR #43）。① を飛ばして ② から

対象: ADR 0016 の段階 1b。① は 9/22 に別セッションで完了済み（ADR + 設計書）なので、台帳 `decisions.json` に
確定 6 行・未確定 0 を書いて ② から入った。

| ノード | 実行 | 結果 |
|---|---|---|
| ② `/build` | implement（sonnet）+ verifier（sonnet）、19 分、35 万トークン | 1 周で全 pass（成果物 5 点 + テスト + 文書） |
| ③ `/review` | reviewer（opus）+ 反証 3 体、9 分、45 万トークン | 指摘 7（直す 3 / 任意 4）、落ちたもの 0。**`--since` で新規 0 件のとき cursor が空になる不具合を fixture と実トランスクリプトで再現**していた |
| human-review | 用語と背景を補って 4 問 | fix 5 / deferred 1 / rejected 1 |
| fix | `/build` を指摘付きで再実行、11 分、26 万トークン | 1 周で全 pass。偽 herdr でメイン pane の解決順と exit 2/3 を検証するテストが増えた |

分かったこと:

- reviewer（opus）が「実行して再現した」不具合を返してきた。差分を読むだけでなく fixture で動かしている。
  実機（herdr）で試せない部分は「推測、実機未確認」と明記して返しており、human-review で区別できた。
- `fix` を `/build` で回す形は成立した。指摘の `fix` 欄がそのまま implement の指示になる。
- 用語を補ってから聞いた結果、聞き返しは 0 回（前回は 2 回）。
- 実機の herdr での手動確認（設計書の「手動」節）は、ワークフローの外で人間がやる。

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
