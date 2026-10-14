---
status: proposed
date: 2026-10-14
decision-makers: akmaru
---

# エージェント利用体験の改善要望を GitHub Issue に起票し、GitHub Actions のエージェントが PR まで自律で進める

## Context and Problem Statement

普段エージェントを使っていると、利用体験の課題（引っかかり・やり直し）や、実現したいことが出てくる。いまはその場で
忘れるか、手が空いたときに自分で dotagents を直すしかなく、改善が使った量に比例して進まない。

起票さえしておけば、エージェントがトリアージ・設計・実装・PR 作成までを自律で進め、人間は「試して approve するか」
だけを判断する、というループを作りたい。決めることは、起票の置き場、エージェントを動かす基盤と課金経路、
自律の範囲、変更を人間が試す方法の 4 つである。

制約: `user/` 配下は `~/.claude` へ symlink で配布される（[ADR 0004](0004-user-config-distribution-symlink-import.md)）
ので、dotagents の main への merge はそのまま全セッションの設定変更（= 配布）になる。また dotagents は公開リポジトリで、
誰でも Issue を書ける。

## Decision Drivers

* 起票の手間を最小にする（違和感を覚えたその場で、どのリポジトリで作業中でも起票できる）
* エージェントが自分の設定（hook・settings・AGENTS.md）を書き換えるので、配布の手前に人間の関門を残す
* 人間は「変更を実際に試したうえで」採否を決められる。試すことで普段の環境を壊さない
* 公開リポジトリでも、第三者の Issue をエージェントの指示として実行しない
* 個人リポジトリの改善には個人アカウント（Max プラン）を使い、会社の Team アカウントを使わない
* 手元のマシンが起きているかに依存しない

## Considered Options

起票の置き場:

1. beads（`.beads/`）を正本にし、beads-sync で GitHub に見せる
2. GitHub Issues を正本にする

エージェントを動かす基盤:

3. ローカルの定期実行（launchd + `claude -p`）
4. claude.ai の routine（クラウド）
5. GitHub Actions（`anthropics/claude-code-action`）
    - 5.1. API キー（`ANTHROPIC_API_KEY`）で認証する
    - 5.2. 個人 Max の OAuth トークン（`CLAUDE_CODE_OAUTH_TOKEN`）で認証する

自律の範囲:

6. 提案（トリアージと ADR 草稿）まで
7. PR 作成まで。人間が試して approve したら merge する
8. 低リスクの変更は CI が通れば自動で merge する

## Decision Outcome

選択: **2 + 5.2 + 7**。起票は GitHub Issues、実行は GitHub Actions を個人 Max の OAuth トークンで動かし、エージェントは
PR 作成までを自律で進める。人間は PR ごとに隔離した環境で変更を試し、approve すると merge される。

- **起票**: 作業中にスキル（名前は未決。下記 More Information）を打つと、一言の説明に今のセッションの文脈
  （作業中のリポジトリ、直前のやり取りの要約）を添えて、dotagents に専用ラベル付きの Issue を `gh issue create` で作る。
  捕捉は手動だけで始め、transcript からの自動検出は入れない。
- **起動**: 専用ラベルが付いた Issue をきっかけに、GitHub Actions のワークフローが起動する。claude-code-action は
  Issue / PR のイベントで起動したユーザーにリポジトリの write 権限を要求するので、第三者の Issue では動かない。
- **進め方**: エージェントは Issue を「そのまま実装できる」と「設計が要る」に分ける。設計が要る場合は、未決事項を
  質問と選択肢として Issue にコメントして止まる。人間が Issue 上で `@claude` を付けて答えると、続きから再開する。
  実装は `claude/` プレフィックスのブランチで行い、既存の CI（`.github/workflows/test.yml`）を通して PR を出す。
- **試し方**: PR 本文の末尾に、隔離環境で試す手順を必ず付ける。`user/install.sh` は配布先を `${HOME}/.claude` と
  直接書いているので、`HOME` ごと差し替えて隔離する。試用専用の HOME は 1 つに固定して PR をまたいで使い回し、
  起動時に `CLAUDE_CONFIG_DIR` も明示する（2026-10-14 追記。PR ごとに HOME を作ると毎回ログインしていない状態になり、
  `/login` が要った。`CLAUDE_CONFIG_DIR` を明示すると Keychain のエントリがそのディレクトリごとに分かれるので、
  試用環境での `/login` が普段のログインを上書きしない）:

  ```bash
  TRY_HOME=~/.claude-trial-home
  git worktree add /tmp/try-pr-N <branch>
  HOME="$TRY_HOME" /tmp/try-pr-N/user/install.sh
  HOME="$TRY_HOME" CLAUDE_CONFIG_DIR="$TRY_HOME/.claude" claude
  ```

- **merge**: 人間が PR を approve すると merge される。approve 以外の経路では merge しない。merge 後に手元の checkout
  を `git pull` した時点で配布が完了する。

### Consequences

* Good: 起票は Issue を 1 つ作るだけで済み、スマホや別マシンからも起票できる
* Good: 課金は個人 Max の使用量から引かれ、API 課金も会社アカウントの使用も発生しない
* Good: 配布の手前に「人間が試して approve する」関門が 1 つ必ず残る
* Bad: beads で管理しているタスク（`.beads/`）と、この改善ループの Issue の 2 か所に分かれる
* Bad: GitHub の runner には手元の環境（herdr・Hindsight・`~/.claude` の状態）が無いので、エージェントは利用体験を
  再現して確かめられない。体験の確認は人間の試用に頼る
* Bad: OAuth トークンは `claude setup-token` を実行した個人のサブスクリプションに紐づくので、トークンの期限切れや
  再発行を人間が管理する
* Neutral: 起票が増えると Max の使用量を消費する。`--max-turns` とワークフローの timeout で 1 回あたりの上限を置く

### Confirmation

`tests/test_agent_kaizen.py` が次を確かめる（CI の `.github/workflows/test.yml` で走る）:

* `.github/workflows/agent-kaizen.yml` が、ラベルを付けた人とコメントした人の両方をリポジトリのオーナーに限っていること、
  `CLAUDE_CODE_OAUTH_TOKEN` で認証し API キーを使わないこと、エージェントに `.github/agent-kaizen/INSTRUCTIONS.md` を読ませること
* `.github/workflows/agent-kaizen-merge.yml` が、オーナーの approve かつ `claude/` ブランチのときだけ走り、`test` の結果を
  見てから merge すること
* `INSTRUCTIONS.md` が merge と `.github/` の変更を禁じ、PR 本文に隔離環境での試し方を求めていること
* 起票スキルが `akmaru/dotagents` に `agent-kaizen` ラベルで起票し、起票前に確認を取ること

エージェントが実際に指示どおり振る舞うか（PR で止まるか、試し方を埋めるか）は、テストでは確かめられない。PR のレビューで確かめる。

## Pros and Cons of the Options

### 1. beads を正本にする

* Good: 既存のタスク管理（`.beads/`、beads-sync）と同じ場所に集まる
* Bad: 他のリポジトリから起票するとき、dotagents の checkout へ書き込む必要があり、そのリポジトリで作業中の
  セッションと競合しうる
* Bad: スマホや別マシンから起票できない

### 2. GitHub Issues を正本にする（採用）

* Good: どこからでも起票でき、`gh` だけで完結する
* Good: GitHub Actions のイベントで直接起動できる
* Bad: beads との 2 か所管理になる（ユーザー決定により、この改善ループでは beads を使わない）

### 3. ローカルの定期実行

* Good: 手元の hook・skill・Hindsight がそのまま使え、利用体験を再現しやすい
* Bad: 手元のログインは会社の Team アカウントなので、個人リポジトリの改善に会社アカウントの使用量を使う
* Bad: Mac が起きている間しか動かない

### 4. claude.ai の routine

* Good: Max プランで使え、マシンに依存しない
* Bad: GitHub トリガーで反応できるのは Pull request と Release のイベントだけで、Issue のイベントでは起動できない。
  Issue を定期的に見に行くポーリングになり、起票してから着手までに遅れが出る

### 5. GitHub Actions（採用）

* Good: Issue のラベル付与やコメントをきっかけに、イベント駆動で起動できる
* Good: Issue / PR のイベントでは起動したユーザーに write 権限を要求するので、公開リポジトリでも第三者の Issue を
  実行しない
* Bad: runner には手元の環境が無い

#### 5.1. API キーで認証する

* Good: トークンの持ち主に依存しない
* Bad: サブスクリプションとは別に API 課金が発生する

#### 5.2. 個人 Max の OAuth トークンで認証する（採用）

* Good: 実行はサブスクリプションの使用量から引かれ、API 課金が発生しない
* Bad: トークンは発行した個人に紐づき、期限切れや再発行の管理が要る

### 6. 提案まで

* Good: 自己改変のリスクが最も小さい
* Bad: 実装は結局人間が指示する必要があり、「自律的に改善する」という目的を満たさない

### 7. PR 作成まで + 人間が試して approve したら merge（採用）

* Good: 実装まで自律で進み、人間の作業は試用と approve だけになる
* Good: merge = 配布の手前に人間の関門が残る
* Bad: 人間が試すまで改善は配布されない

### 8. 低リスクの変更は自動 merge

* Good: 最も速く改善が回る
* Bad: 「低リスク」の判定をエージェント自身が行うことになり、自己改変の関門が 1 つ減る
* Bad: 文言の変更でも、AGENTS.md やスキルの記述はエージェントの振る舞いを変えるので、低リスクの線を引きにくい

## More Information

- 配布方式: [ADR 0004](0004-user-config-distribution-symlink-import.md)、settings.json のマージ:
  [ADR 0009](0009-settings-json-merge.md)
- 既存のワークフローグラフ（intake → design → build → review）: [ADR 0018](0018-workflow-graph-three-sccs.md)、
  [ADR 0020](0020-workflow-graph-control-flow.md)。この改善ループは、その intake を Issue に、人間ノードを Issue / PR 上の
  非同期のやり取りに置き換えたものにあたる
- 出典: [Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions)（OAuth トークンの対応プラン、
  write 権限のチェック）、[Automate work with routines](https://code.claude.com/docs/en/routines)（GitHub トリガーが
  対応するイベント）
- 名前（2026-10-14 決定）: 起票スキル・ラベル・ワークフロー・指示のディレクトリをすべて `agent-kaizen` にした。
  「課題」と「実現したいこと」の両方を含み、使った分だけ少しずつ良くしていくという意図に合うため。
  候補は `friction`（課題しか指さない）/ `papercut`（さらに狭い）/ `wish`（課題の報告には軽い）/ `kaizen` だった。
  実装の当初は仮に `agent-dx` としていたので、このファイル名と PR #48〜#52 には `agent-dx` が残る
- 未決事項:
  - 試用専用の HOME で `/login` したログインが、普段のログインと別に保存されるか（ドキュメントに基づく。実機では未検証）。
    `HOME` を差し替えた環境で `user/install.sh` と `apm install -g` が動くことは確かめた（PR #51 の試用）
