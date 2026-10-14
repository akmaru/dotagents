---
status: proposed
date: 2026-10-14
decision-makers: akmaru
---

# ユーザーが答える番を herdr に出す: 回答待ちを hook で blocked にし、kaizen ごとに専用セッションを立てる

## Context and Problem Statement

[ADR 0027](0027-agent-dx-improvement-loop-via-github-issues.md) の改善ループは、設計が要るとき Issue に質問を書いて止まる。
いまは、その質問も、PR が出たことも、作業中のセッションには届かない（Issue #55）。また、セッション自身が
`AskUserQuestion` や権限確認でユーザーの回答を待っているとき、herdr はそれを「回答待ち」として区別できていない。
herdr が Claude Code に入れる hook は `SessionStart` の 1 つだけである（手元で確認）。

## Decision Outcome

1. **回答待ちの報告**: 別ファイルの hook `user/bin/herdr-report-state.sh` が `herdr pane report-agent --state blocked|working`
   を送る。`PreToolUse(AskUserQuestion)` と `Notification(permission_prompt|elicitation_dialog)` で blocked、
   `PostToolUse(*)` で working に戻す。working は blocked を送った pane にだけ返す（印のファイルで足切りする）。
   herdr が生成するスクリプトは再インストールで上書きされるので、そこには足さない。登録は `install.sh` の `add_hook_once`
   （herdr や他ツールも書く配列なので、deep merge に任せない。ADR 0020 と同じ）。
2. **1 つの kaizen は 1 つのセッション**: `agent-kaizen` スキルが起票した後、herdr の中なら
   `user/herdr/scripts/agent-kaizen-session.sh <N>` が `kaizen-<N>` という名前の専用セッションを隣の pane に立ち上げる
   （フォーカスは奪わない）。元のセッションは今の作業に戻る。
3. **専用セッションが Issue を見張る**: 専用セッションは Monitor ツールで `agent-kaizen-watch.sh <N>` を動かす。
   これは `gh` を一定間隔（既定 60 秒）で呼び、次のときだけ 1 行出す。
   * エージェントが Issue に書いて止まった（最新コメントが `claude` で、実行中の表示でない）
   * `claude/issue-<N>-` の PR が open になった（レビューと merge はユーザーの番）
   * PR が merge された / Issue が閉じられた（出力して終了）
4. **質問と回答**: 専用セッションは質問を `AskUserQuestion` で出す（1 により herdr で blocked になる）。答えは `@claude` を
   含むコメントにし、**本文を見せて確認を取ってから** `gh issue comment` で投稿する（公開リポジトリのため）。

セッション開始時の確認やプロンプト送信時の再確認は採らない。ユーザーが何も打っていない間は届かないため。

### Consequences

* Good: ユーザーが答える番の項目が herdr の attention 順と `next_agent` に乗る
* Good: 常駐プロセスを足さない。監視は専用セッション（Claude Code の Monitor）の寿命と同じ
* Bad: 専用セッションは kaizen の数だけセッション（= 使用量）を使う
* Bad: `PostToolUse(*)` はツール実行のたびにプロセスを 1 つ起動する（印が無ければすぐ終わる）
* Bad: 権限確認が拒否されたとき `PostToolUse` が来ず、次にツールが完了するまで blocked が残りうる

### Confirmation

`tests/test_kaizen_session.py` が、スタブの herdr / gh で次を確かめる: blocked と working の報告（working は blocked の後だけ）、
Issue の状態ごとの出力（質問・実行中・回答済み・PR・merge）、専用セッションの起動（1 Issue 1 セッション、フォーカスを奪わない）、
`install.sh` への登録、スキルの記述。

実機の herdr で確かめていないこと: `herdr pane report-agent` の引数（`--pane` の指定）、herdr 自身の画面検出が blocked を
上書きしないか、`agent start` の `--` 以降の文字列が初回プロンプトになるか、`Notification` の `matcher` 値。

## More Information

- [ADR 0008](0008-herdr-config-in-dotagents.md)、[ADR 0010](0010-herdr-plugins-declared-in-install-sh.md)
