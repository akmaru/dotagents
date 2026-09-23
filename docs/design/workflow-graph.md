# ワークフローグラフ（3 つの強連結成分）

普段の作業を、ノード（仕事）・エッジ（遷移条件）・エッジ上を流れる共有状態として明示したもの。
決定は [ADR 0018](../adr/0018-workflow-graph-three-sccs.md)、図は
[workflow-graph.drawio](workflow-graph.drawio)（draw.io で開く）。役割定義の形式と配布は
[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)。
本書は機構の説明で、運用規約を兼ねる（2026-09-23 時点）。

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
| 台帳 | `decisions.md` | `verify.md` | `review.md` |
| 台帳の行 | 軸 / 選択肢 / 確定・未確定 / 根拠 | 検証項目 / 種別 / pass・fail・未実行 / 直近の原因 | 指摘 / 対応・棚上げ・却下 |
| 抜ける条件 | 未確定 0 | 全項目 pass | 未対応 0 |
| 離脱の判定 | **同じ軸の再訪**: 確定も新軸も増えない周が 2 回続いたら人間に確認 | **同一原因の再発**: 同じ項目が同じ原因で 2 回 fail → ① へ。ベンチ未達は 1 回目で ① へ | **層の不一致**: 指摘が実装でなく設計に及ぶ → ① へ |

### ① deliberate

`research → design → critique → decide` と、`decide` からの 2 本の戻り。

| 戻りエッジ | 引き金の例 | 委譲の扱い |
|---|---|---|
| `decide → research` | 「案 2 のヘルプはどういう意味なの？」「daemon はログオフでは止まらないよね？」 | 同じ researcher を `SendMessage` で**再開**（追補） |
| `decide → design` | 「AWS 常にホストする案はどうだろう？」「ID 連携を使えば API キー不要と言われた」 | designer を**呼び直す**（改訂。軸が増えた = 別版） |
| `decide → decide` | 「まず永続化は API のみは決定。永続化については少し掘り下げたい」 | 委譲なし。台帳を部分確定に更新するだけ |

役割の報告は**末尾が必ず「未決事項（質問 + 選択肢 2〜4 個）」**で終わる（[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)）。
これが `decisions.md` の未確定行にそのまま対応するので、台帳の書式を別に定義する必要はない。

確定済みの軸は再オープンしない。次のノードへ渡すときは「確定済み」と明記する
（`user/AGENTS.md` の Delegation 節の規約そのもの）。

### ② build

`implement ⇄ verify-local` と `implement ⇄ human-op`。

`verify-local` の項目には**種別**（テスト / ベンチ / 起動確認）を持たせる。性能は設計の帰結なので、
**ベンチ未達だけは 1 回目で ① へ戻す**。テストは同一原因 2 回で戻す。

`human-op` は人間が手で実行する特権・対話操作（`aws sso login`、`terraform apply`、keychain 登録、
daemon 起動、ブラウザ確認）。結果を貼り戻して `implement` に戻る。

ローカルで再現できない検証項目（例: CI 固有の OS マトリクス）は `verify.md` に印を付けて持ち、
② の抜ける条件からは除外して ③ の `verify-CI` に委ねる。

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
`merge` へは行かず指摘を出して終わる。組み込みの `/code-review` skill がこのノードの実装候補。

## side-car: explainer

`explainer` は常駐 pane の別セッションで、どの SCC からも参照できるが**グラフの状態を変えない**
（観測のみ）。実測で問いの 3〜4 割が「用語・意味の確認」なので、ここを逃がすと ① の
`decide → research` 往復が減るはずだが、効果は未測定。機構は
[docs/design/explainer-pane.md](explainer-pane.md)、決定は
[ADR 0016](../adr/0016-explainer-pane-transcript-digest.md)（proposed、段階 1b は未着手）。

## 状態の置き場所

| 層 | 置き場所 | 寿命 |
|---|---|---|
| 台帳（揮発） | scratchpad の `decisions.md` / `verify.md` / `review.md` | タスク単位。セッション固有の一時領域 |
| 決定 | `docs/adr/NNNN-*.md` | 永続。`record` ノードの出力 |
| タスク | beads（`.beads/`） | 永続。棚上げで増える |
| 学び | Hindsight | 永続。`SessionEnd` hook が自動投入（[ADR 0017](../adr/0017-session-end-retain-hook.md)） |

台帳は scratchpad に置くので、長期に要るものは `docs/` か beads に移してから捨てる。
学びの投入はグラフ上のノードではなく、**グラフ全体の終了時副作用**として扱う。

## 委譲の規約との対応

ノードから役割を呼ぶときは `Agent` ツールの `subagent_type` に役割名を渡す。渡すものは
`user/AGENTS.md` の Delegation 節のとおり（目的・制約・関連ファイルの絶対パス・先行報告のパス・
確定済み事項の明示）。**追補は同じエージェントを再開、改訂は呼び直し**という既存の区別が、
そのまま ① の戻りエッジのラベルになっている。

委譲は現在「ユーザーが役割名で指示したときだけ」（閾値計測のためのドッグフーディング中）。
本グラフはその制約を変えない。

## 未定義の拡張点

- **② と ③ に対応する役割が無い**。[ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md) は
  implementer / verifier を「拡張点（定義なし）」とし、reviewer は役割自体が存在しない。
  足すときは `user/agents/<name>.md` を同じ形式で作り、`user/AGENTS.md` の Delegation 表に行を追加する
  （`tests/test_user_config.py` が整合を強制する）。
- **verifier の権限**。役割の読み取り専用制約（`disallowedTools`）は Bash 経由の書き込みを防げない。
  verifier は本質的にコマンドを実行するので、ここは制約文と作業ディレクトリの限定で補う必要がある。
- **`intake` のルーティング**。現在はメインのモデルの判断に委ねる。skill として明文化して機械的に
  踏ませるかは未決（[ADR 0015](../adr/0015-memory-ingestion-path.md) の「モデル判断 vs 機械的保証」と同じ軸）。
- **空転 2 周という閾値**は実測に基づかない初期値。数タスク回してから見直す。

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
