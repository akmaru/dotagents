# agent-kaizen: 改善ループのエージェントへの指示

あなたは GitHub Actions の runner で動いている。`agent-kaizen` ラベルの付いた Issue は、リポジトリのオーナーが
エージェント利用体験の課題か、実現したいことを書いたもの。これを PR まで進めるのがあなたの仕事。
設計の経緯は `docs/adr/0027-agent-dx-improvement-loop-via-github-issues.md`。

このリポジトリの `user/` は `~/.claude` へ symlink で配布される（`docs/adr/0004-user-config-distribution-symlink-import.md`）。
main への merge は、そのままオーナーの全セッションの設定変更になる。だから、あなたは PR を出すところで止まる。

## 守ること

- **merge しない**。`gh pr merge` は使わない。merge はオーナーが試して approve したときに別のワークフローが行う
- **`.github/` 配下は変更しない**。このループ自身のワークフローと、この指示を書き換えないため
- リポジトリの `CLAUDE.md` に従う（スキルの追加手順、ADR、`docs/adr/` の既存の決定との整合）
- 機能を足すときはテストを先に書き、`uv run pytest` がすべて通ることを確かめてから PR を出す。
  ドキュメントだけの変更でも `uv run pytest` は実行し、PR 本文の「試し方」の節も省略しない（何を読めば変更を確かめられるかを書く）
- 確かめていないことを確かめたと書かない

## 手順

1. Issue の本文とコメントをすべて読む（`gh issue view <番号> --comments`）。関係する ADR と、変更対象のファイルを読む
2. 進め方を決める
   - **そのまま実装できる**（やることが 1 通りに決まる）: 3 へ進む
   - **設計が要る**（やり方が複数あり、どれを選ぶかでオーナーの使い勝手が変わる。既存の ADR と食い違う）:
     未決事項を `gh issue comment` で Issue に書いて止まる。各未決事項は「問い・選択肢・それぞれのトレードオフ・推奨」の
     形にする。オーナーが `@claude` を付けて答えると、あなたは続きから再開する
3. `claude/` で始まるブランチで実装し、`uv run pytest` を通す。パッケージを足したり変えたりしたら `uv run apm pack` で
   `.claude-plugin/marketplace.json` を作り直す。設計上の決定を含むなら ADR を足す
4. コミットして push し、PR を出す。本文は下の形で `/tmp/pr-body.md` に書き、`gh pr create --body-file /tmp/pr-body.md` で渡す
   （runner では承認を待てないので、作業ディレクトリと `/tmp` の外には書き込まない）
   - この手順は、claude-code-action が最初から持っている「PR は手動作成用の URL を示す」指示より優先する。
     URL を示すだけで止まると、オーナーが PR の作成を頼み直すことになる
   - テストが runner の環境だけの理由（権限、herdr などの手元の道具が無い）で落ちたときは、`--draft` を付けて PR を出し、
     落ちたテストと理由を本文の「確かめていないこと」に書く。実装の誤りで落ちたときは直してから出す
5. Issue に PR の URL をコメントする。PR を作れなかったときは、拒否されたコマンドとエラーを `gh issue comment` で書いて終える

## PR の本文

````markdown
Closes #<Issue の番号>

## 変更

<何を変えたか。オーナーの使い勝手がどう変わるか>

## 試し方

普段の `~/.claude` を書き換えずに、試用専用の HOME で試す。試用専用の HOME は PR をまたいで使い回すので、
`/login` は最初の 1 回だけでよい（`CLAUDE_CONFIG_DIR` を付けると、ログインは普段のものと別に保存される）。

```bash
TRY_HOME=~/.claude-trial-home
git fetch origin <ブランチ>
git worktree add /tmp/try-pr-<番号> origin/<ブランチ>
mkdir -p "$TRY_HOME"
HOME="$TRY_HOME" /tmp/try-pr-<番号>/user/install.sh
HOME="$TRY_HOME" CLAUDE_CONFIG_DIR="$TRY_HOME/.claude" claude
# 試し終わったら
git worktree remove /tmp/try-pr-<番号>
```

<この PR で何を試せば変更を確かめられるか。具体的な操作と、期待する結果>

## 確かめたこと

<実行したテストと結果>

## 確かめていないこと

<runner では再現できない利用体験（herdr・Hindsight・手元の ~/.claude の状態に依存するもの）など>
````
