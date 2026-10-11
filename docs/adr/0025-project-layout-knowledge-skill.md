---
status: accepted
date: 2026-10-11
decision-makers: akmaru
---

# 標準構成の知識を project-layout スキルに切り出し、参照するパッケージは相対パスで依存する

## Context and Problem Statement

[ADR 0024](0024-new-project-standard-layout.md) で新規プロジェクトの標準構成と、ADR などの置き場の決め方を定めた。
この知識は、構成を作る `init-project` だけでなく、ADR を書く・読む `madr-writer`・`grill-with-docs`・`refine-design`
と、役割 designer・critic も使う。知識をどこに 1 つだけ置き、それを使うパッケージがどう確実に手に入れるかを決める。

## Decision Drivers

* 構成の定義を 1 か所に置き、スキルごとに食い違わせない
* 構成を知りたいだけの場面で、作成の手順まで読み込ませない
* 毎セッション常に読み込まれる指示（`user/AGENTS.md`）を増やさない（context-budget の方針）
* marketplace 経由で入れたとき、定義（`layout.json`）と、それを使うテンプレートの版が食い違わない
* 利用者は marketplace 経由で入れる。ディレクトリ指定で入れる予定は無い

## Considered Options

知識の置き場:

1. `init-project` の SKILL.md を他のスキルから参照させる
2. `user/AGENTS.md`（グローバル指示）に書く
3. 各スキルに置き場の決め方を埋め込む（ADR 0024 を決めた時点の状態）
4. 参照専用のスキル `project-layout` に切り出す
    - 4.1. 依存を `../project-layout`（相対パス）で張る
    - 4.2. 依存を `akmaru/dotagents/packages/project-layout`（GitHub の形）で張る
    - 4.3. 依存を marketplace の形（`name: project-layout` / `marketplace: dotagents`）で張る
    - 4.4. 依存を張らず、README で一緒に入れるよう案内する

4.1〜4.4 は、`project-layout` をどこから取ってくるかで分かれる。

## Decision Outcome

選択: **4.1**（定義が 1 か所になり、相対パスの依存は `init-project` を取ってきたのと同じ ref の `project-layout` を
取るので、`layout.json` とテンプレートの版がそろう）。

- `packages/project-layout/` は、SKILL.md（置き場の決め方と標準のツリー）と機械可読の `layout.json` を持つ。
  ファイルは作らない。
- `init-project` のスクリプトは、インストール後に同じ `skills/` の隣に入る `project-layout/layout.json` を読む。
  テンプレートは `templates/<layout.json の id>` に置く。dotagents のテストは `--layout` で checkout のパスを渡す。
- `init-project`・`madr-writer`・`grill-with-docs`・`refine-design` の `apm.yml` に `../project-layout` を依存として
  書く。これらと役割 designer / critic は、置き場の決め方を自前で書かず `project-layout` を参照する。
- 構成を変えるときは `project-layout` の version を上げ、`apm pack` で `marketplace.json` を作り直してからコミットする。

### Consequences

* Good: 置き場の決め方と標準のツリーが `project-layout` の 1 か所だけになる
* Good: 構成を知りたいだけの場面では、description の短い `project-layout` だけが読まれる
* Good: `layout.json` の各項目にテンプレートがあることを、テストで機械的に確かめられる
* Bad: APM 0.31.0 では、パッケージを作業ツリーから入れる経路（ディレクトリ指定と、ローカルのリポジトリを
  marketplace として登録した場合）の `-g` で、相対パスの依存が配置されない（エラーは
  `its install path is not a directory`）。GitHub から入れる経路では `-g` でも配置される。push 前の変更を `-g` で
  試すときは、2 つのパッケージを明示して入れる（`packages/init-project/README.md` に記載）
* Bad: APM の仕様は、ローカルパスの依存を "development only" と位置づけている。将来の版で扱いが変わったら 4.2 に
  切り替える（`apm.yml` の依存の行を書き換えるだけで済む）
* Neutral: `project-layout` だけを別の版に固定することはできない。常に依存元と同じ ref のものが入る
* Neutral: 役割 designer / critic は APM のパッケージではないので依存を宣言できない。`project-layout` は、上の
  スキルのどれかを入れれば一緒に入る

### Confirmation

* `tests/test_init_project.py::test_init_project_depends_on_project_layout_by_relative_path` が、4 つのパッケージの
  `apm.yml` に `../project-layout` が書かれていることを確かめる。
* `tests/test_init_project.py::test_script_finds_layout_next_to_its_own_skill_dir` が、2 つのスキルを隣どうしに
  置いた状態で、`--layout` なしにスクリプトが `layout.json` を読めることを確かめる。
* `tests/test_init_project.py::test_every_layout_entry_has_a_template` が、`layout.json` の各 id にテンプレートが
  あり、余分なテンプレートが無いことを確かめる。
* `tests/test_skills.py::test_layout_consumers_refer_to_project_layout` が、参照する側の 5 ファイルが
  `project-layout` を参照し、`docs/adr/` を自前で書いていないことを確かめる。
* `tests/test_e2e_marketplace.py::test_init_project_from_github_marketplace_pins_both_packages_to_one_commit` が、
  CI で PR の先端のコミットを GitHub から marketplace として登録し、プロジェクトと `-g` の両方で、`project-layout` が
  隣に入ること、`apm.lock.yaml` の `resolved_commit` が 2 つともそのコミットであること、入ったスクリプトが
  `--layout` なしで動くことを確かめる。CI が `DOTAGENTS_E2E_REMOTE` を渡さないローカルではスキップする。
* `tests/test_e2e_marketplace.py::test_init_project_from_local_marketplace_deploys_project_layout_alongside` が、
  ローカルの marketplace（作業ツリー）からプロジェクトスコープで入れたときに同じことを確かめる。

## Pros and Cons of the Options

### 1. init-project の SKILL.md を参照させる

* Good: パッケージが増えない
* Bad: description が「作る」場面に合わせてあるので、知りたいだけの場面で起動されにくい
* Bad: 読むと作成の手順まで読み込まれる

### 2. user/AGENTS.md に書く

* Good: どのセッションでも確実に読まれる
* Bad: 毎セッション常に読み込まれる量が増える
* Bad: marketplace 経由の利用者には届かない

### 3. 各スキルに埋め込む

* Good: どのスキルも単体で動く
* Bad: 置き場の決め方を 5 か所に書くことになり、変えるときに揃えて直す必要がある

### 4. project-layout に切り出す

* Good: 定義が 1 か所になる
* Bad: 使う側が `project-layout` を確実に手に入れる仕組みが要る（4.1〜4.4）

#### 4.1. 相対パスで依存する（採用）

* Good: 仕様上、リモートのパッケージ内の相対パスは "APM expands it to the same remote host/repo/ref" なので、
  依存元と同じ ref の `project-layout` が入る（[Manifest schema](https://microsoft.github.io/apm/reference/manifest-schema/)）
* Good: ディレクトリ指定でプロジェクトに入れたときも手元の `project-layout` が入る（scratchpad で確認）
* Bad: Consequences の 2 つ（`-g` のディレクトリ指定で配置されない、"development only"）

#### 4.2. GitHub の形で依存する

* Good: リモートの依存として通常の経路で解決される
* Bad: `#ref` を付けなければ main を追いかけるので、古い `init-project` と新しい `project-layout` が組み合わさりうる
* Bad: `#ref` を付けると、`layout.json` を変えるたびに「変更のコミット」と「ref を更新するコミット」の 2 段になる

#### 4.3. marketplace の形で依存する

* Good: version の範囲で依存を指定できる
* Bad: 利用者が marketplace を `dotagents` という名前で登録していることが前提になる
* Bad: 範囲で指定するには、タグを打つ運用が要る（dotagents には今タグが無い）

#### 4.4. 依存を張らない

* Good: APM の依存解決に頼らない
* Bad: 入れ忘れても、スクリプトを実行するまで気づかない
* Bad: 参照する側のスキルに既定値を残すことになり、3 と同じ食い違いの危険が戻る

## More Information

* [ADR 0024](0024-new-project-standard-layout.md): 標準構成と置き場の決め方
* [ADR 0023](0023-agents-md-dependent-skills-from-checkout.md): AGENTS.md が参照するスキルをディレクトリ指定で入れる仕組み。
  `project-layout` と `init-project` は AGENTS.md から参照しないので対象外
* 先例: `packages/rust/apm.yml` が他のパッケージに依存している
* 確認の記録: 2026-10-11 に push 済みのコミット `05e414b` を GitHub から登録し、プロジェクトと `-g` の両方で
  2 つが同じコミットから入ることを手で確かめた。以後は上の e2e テストが CI で確かめる
