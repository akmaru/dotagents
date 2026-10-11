---
status: accepted
date: 2026-10-11
decision-makers: akmaru
---

# 新規プロジェクトの標準構成を定め、ADR の置き場は指示ファイルの規約 → 既存 → docs/internal/adr/ の順で決める

## Context and Problem Statement

dotagents のスキルは、それぞれが前提にするファイルを別々に書いていた。madr-writer・grill-with-docs・refine-design と
役割 designer・critic は ADR の置き場を `docs/adr/` に決め打ちし、外部の adr-skill は `docs/decisions/` を既定にし、
grill-spec の仕様書（feature/grill-spec ブランチ）は `docs/internal/{specs,adr}/` を提案していた。新規プロジェクトを
作るときに「あるべきファイル / ディレクトリ」を 1 つに定め、存在を確かめて無ければ作るスキルを用意したい。決めることは
3 つある。(1) 標準のツリー。(2) その規定をどこに持たせ、既存スキルがどう従うか。(3) 公開リポジトリ向けなど、
プロジェクトによって要否が分かれるファイルをどう選ぶか。

## Decision Drivers

* スキルは任意のリポジトリに `apm install` して使う。すでに `docs/adr/` などを持つリポジトリでも ADR が 2 か所に割れない
* grill-with-docs の「ファイルは書くものができたときだけ作る」（遅延作成）と矛盾しない。空の `CONTEXT.md` を置かない
* 構成の規定を 1 か所に置き、スキルごとに食い違わせない
* docs は外部に公開するドキュメントのソース（`public/`）と内部の文書（`internal/`）を分ける。ジェネレータは
  リポジトリごとに違うので前提にしない
* GitHub のコミュニティヘルスファイルは `.github/` → ルート → `docs/` の順にしか探されない
  （[GitHub Docs](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file)）
* beads は採用を続けるか検討中なので、標準構成に含めない
* リポジトリは GitHub で管理する場合と GitLab で管理する場合があり、テンプレートなどの置き場がホスティングごとに違う

## Considered Options

1. 現状維持: 標準構成を定めず、各スキルが置き場を決め打ちする
2. 標準構成を雛形スキルにだけ書き、空のファイルも含めて一式を作る
3. 標準構成のうち置き場の規約を指示ファイル（`AGENTS.md`）に書き、雛形スキルは中身のあるファイルと規約だけを置く。
   既存スキルは指示ファイルの規約 → 既存のディレクトリ → 既定の順で置き場を決める
    - 3.1. 要否が分かれるファイルを「チーム外の人が使う・貢献するか」の 1 問でまとめて決める
    - 3.2. 「コードを誰でも読めるか」「チーム外から issue / PR を受けるか」「リリースするか」の 3 軸で決める
    - 3.3. ファイルごとにチェックボックスで聞く

3.1〜3.3 は、要否が分かれるファイルを選ぶ粒度で分かれる。

## Decision Outcome

選択: **3.3**（置き場の規約を指示ファイルに置けば、既存スキルも今後のスキルも同じ場所を読める。要否の選択は
ファイルごとに聞くのが、軸の数え方を誤る余地がなく、外れたファイルを後で消す手間も無い）。

標準のツリー:

```
<repo>/
├── README.md
├── LICENSE                 # 既定は MIT
├── CONTRIBUTING.md         # 人間向けの手順。AGENTS.md は重複させず参照する
├── AGENTS.md               # エージェント向け指示。「置き場の規約」節を含む
├── CLAUDE.md               # `@AGENTS.md` の 1 行だけ
├── .gitignore
├── .gitattributes
├── .editorconfig
├── docs/
│   ├── public/             # 外部に公開するドキュメントのソース。.gitkeep だけを置く
│   └── internal/
│       └── adr/
│           └── 0001-record-architecture-decisions.md
└── .claude/
    └── .gitignore          # `*` / `!.gitignore`。台帳など作業用の置き場
```

- 作らず、置き場だけを `AGENTS.md` に書くもの: ルートの `CONTEXT.md`（用語集）、`CONTEXT-MAP.md`、
  `docs/internal/specs/`（仕様書）。それぞれ最初に書く内容ができたときに、書くスキルが作る。
- 最初に、リポジトリを GitHub と GitLab のどちらで管理するかを聞く。ホスティング固有のファイルの置き場は次のとおり。

  | ファイル | GitHub | GitLab |
  |---|---|---|
  | issue テンプレート | `.github/ISSUE_TEMPLATE/` | `.gitlab/issue_templates/` |
  | PR / MR テンプレート | `.github/pull_request_template.md` | `.gitlab/merge_request_templates/` |
  | `CODEOWNERS` | `.github/CODEOWNERS` | ルートの `CODEOWNERS` |

- チェックボックスで要否を聞くもの: `SECURITY.md`、`CODE_OF_CONDUCT.md`、`SUPPORT.md`、`CHANGELOG.md`、
  issue テンプレート、PR / MR テンプレート、`CODEOWNERS`。`SECURITY.md` などの Markdown はどちらのホスティングでも
  ルートに置く。GitHub が探す範囲（`.github/` → ルート → `docs/`）に入れるためで、`docs/public/` には置かない。
- 雛形に含めないもの: 言語別のファイル（`Cargo.toml` など。`cargo init` などに任せる）、CI と dependabot の設定
  （言語に依存する）、beads。
- ADR の置き場は、(1) 指示ファイル（`AGENTS.md` / `CLAUDE.md`）の規約、(2) 既存の `docs/internal/adr/`、
  `docs/adr/` の順、(3) どちらも無ければ `docs/internal/adr/`、で決める。この順と標準のツリーは
  `project-layout` スキルが定義し、他のスキルと役割はそれを参照する（[ADR 0025](0025-project-layout-knowledge-skill.md)）。
  dotagents 自身は (2) により `docs/adr/` を使い続ける。

### Consequences

* Good: 既定が `docs/internal/adr/` に変わっても、`docs/adr/` を持つ既存リポジトリでは ADR が割れない
* Good: 構成を変えたいリポジトリは `AGENTS.md` の置き場の規約を書き換えるだけでよく、スキルを直さなくてよい
* Good: 空の `CONTEXT.md` や空の仕様書ディレクトリを作らないので、grill-with-docs の遅延作成と矛盾しない
* Bad: 構成の知識を参照するスキルが複数あるので、知識の置き場と依存の管理が要る。どう持つかは
  [ADR 0025](0025-project-layout-knowledge-skill.md) で決める
* Bad: 要否が分かれるファイルが 7 つあるので、雛形を作るたびに 7 項目のチェックボックスに答える。Claude Code の
  質問ツールは 1 問あたり選択肢 4 つまでなので、ホスティングの質問と合わせて 3 問になる
* Neutral: grill-spec の仕様書が提案した `packages/<name>/docs/internal/{specs,adr}/`（パッケージ固有の置き場）は
  この ADR では決めない。grill-spec を main に入れるときに、この ADR と整合させる

### Confirmation

* `tests/test_init_project.py::test_layout_matches_adr_0024` が、`project-layout` の `layout.json` に載る
  すべてのパス（標準のツリー・作らないもの・選択式のファイル）が、この ADR に書かれていることを確かめる。
  ADR のツリーの図と `layout.json` の構造までは突き合わせない。
* `tests/test_init_project.py` の他のテストが、空のディレクトリに作られるファイルが標準のツリーとちょうど一致すること、
  選択式のファイルがホスティングごとの置き場に作られること、既存のファイルを上書きしないこと、`CONTEXT.md` と
  `docs/internal/specs/` を作らないことを、`init-project` のスクリプトを実行して確かめる。
* `tests/test_skills.py::test_project_layout_defines_the_adr_location_order` は、`project-layout` の SKILL.md に
  `AGENTS.md`・`CLAUDE.md`・`docs/internal/adr/`・`docs/adr/` が書かれていることだけを見る。3 段の順の正しさは
  レビューで確かめる。

## Pros and Cons of the Options

### 1. 現状維持

* Good: 何も変えなくてよい
* Bad: スキルごとに置き場が違い（`docs/adr/` と `docs/decisions/`）、`docs/public/` と `docs/internal/` を分ける
  構成に従えない
* Bad: 新規プロジェクトであるべきファイルが、どこにも定義されていない

### 2. 雛形スキルにだけ書き、一式を作る

* Good: 雛形スキルを読めば構成が分かる
* Bad: 空の `CONTEXT.md` を作ると grill-with-docs の遅延作成と矛盾し、grill-with-docs を直す必要がある
* Bad: 既存スキルは雛形スキルを読まないので、構成の規定と各スキルの置き場が別々に書かれ、食い違いがもう 1 つ増える

### 3. 置き場の規約を指示ファイルに置き、雛形は中身のあるものだけを作る

* Good: 既存スキルも今後のスキルも、指示ファイルという 1 か所を読めばよい
* Good: 既存の置き場を優先するので、既存リポジトリでの互換が保たれる
* Bad: 指示ファイルに規約が無いリポジトリでは、既定値が各スキルに書かれていることになる

#### 3.1. 1 問でまとめて決める

* Good: 質問が 1 回で済む
* Bad: 「公開だがリリースしない」のように軸が連動しないリポジトリでは、不要なファイルが作られ、後で消すことになる
* Bad: 「公開」という語が、リポジトリの可視性と `docs/public/` の公開の 2 つの意味で紛らわしい

#### 3.2. 3 軸で決める

* Good: ファイルの要否を、理由（読めるか・受け付けるか・リリースするか）と結びつけて決められる
* Bad: 軸とファイルの対応を利用者が覚えておく必要があり、どの軸にも当てはまらない `SUPPORT.md` や `CODEOWNERS` の
  扱いがあいまいになる

#### 3.3. ファイルごとのチェックボックス（採用）

* Good: 何が作られるかを、作る前にファイル名で確かめられる
* Good: 軸の解釈を挟まないので、選択と結果が食い違わない
* Bad: 毎回 7 項目に答える（ホスティングの質問と合わせて 3 問）

## More Information

* [ADR 0021](0021-target-claude-code-only.md): Claude Code のみをターゲットにする。チェックボックスは Claude Code の
  質問ツール（multiSelect）を前提にする
* [ADR 0023](0023-agents-md-dependent-skills-from-checkout.md): AGENTS.md が参照する skill の配り方
* GitLab の置き場の出典: [Description templates](https://docs.gitlab.com/user/project/description_templates/)、
  [Code Owners](https://docs.gitlab.com/user/project/codeowners/)（ルート → `docs/` → `.gitlab/` の順に探す）
* 標準のツリーを作るのは `init-project` スキル、定義を持つのは `project-layout` スキル（[ADR 0025](0025-project-layout-knowledge-skill.md)）
