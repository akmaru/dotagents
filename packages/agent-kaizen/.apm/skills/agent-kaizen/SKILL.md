---
name: agent-kaizen
description: エージェントを使っていて感じた利用体験の課題（引っかかり・やり直し・面倒）や実現したいことを、今のセッションの文脈を添えて akmaru/dotagents の GitHub Issue に agent-kaizen ラベル付きで起票する。起票された Issue は GitHub Actions のエージェントが PR まで進める。ユーザーが「/agent-kaizen」と打ったとき、エージェントの使い勝手への不満や改善の要望を dotagents に起票したい・残したいと言ったときに使う。
---

## 何をするか

ユーザーの一言を、エージェントがそのまま着手できる Issue にして `akmaru/dotagents` に起票する。`agent-kaizen` ラベルを付けると、
GitHub Actions のエージェントがトリアージ・設計・実装を進めて PR を出す（`docs/adr/0027-agent-dx-improvement-loop-via-github-issues.md`）。
runner のエージェントは今のセッションを見られないので、Issue の本文だけで状況が分かるように書く。

## 手順

1. **種類と一言を決める**。ユーザーの言葉から、「課題」（いまの振る舞いが困る）か「要望」（まだ無いことをしたい）かを決める。
   一言が無ければ、何に引っかかったか・何をしたいかを 1 つだけ聞く
2. **文脈を集める**。会話とコマンドから次を拾う。推測で埋めず、分からないものは書かない
   - 何をしようとしていたか、エージェントが実際にどう振る舞ったか（課題のとき）
   - どうなってほしいか
   - 関係しそうな dotagents の部品（skill・役割・hook・`user/AGENTS.md` の節など）と、そのパス
   - 再現の手順（分かるとき）
3. **公開してよい内容にする**。`akmaru/dotagents` は**公開リポジトリ**で、Issue は誰でも読める。次は書かない。
   言い換えるか、ユーザーに確かめる
   - 会社のリポジトリ名・コード・顧客や案件の情報、社内の URL
   - API キー・トークン・パスワード、個人情報
4. **下書きを見せて確認を取る**。タイトルと本文を示し、`AskUserQuestion` で「起票する / 直す / やめる」を聞く。
   確認が取れるまで起票しない
5. **起票する**。本文はファイルに書いてから渡す（引用符の崩れを避けるため）

   ```bash
   gh issue create --repo akmaru/dotagents --label agent-kaizen --title "<タイトル>" --body-file <本文のファイル>
   ```

6. Issue の URL をユーザーに返す。エージェントが着手したら Issue に進捗のコメントが付くこと、設計が要る場合は
   Issue で質問されること（`@claude` を付けて答えると再開する）を一言添える

7. herdr の中なら（`HERDR_PANE_ID` がある）、その Issue 専用のセッションを立ち上げて、元のセッションは今の作業に戻る

   ```bash
   ~/.config/herdr/scripts/agent-kaizen-session.sh <Issue 番号>
   ```

   herdr の外、またはスクリプトが無いときは立ち上げず、Issue の URL を返すだけにする。1 つの kaizen は 1 つのセッションで扱う
   （`docs/adr/0029-agent-kaizen-dedicated-session-and-blocked-reporting.md`）。

## 専用セッション

プロンプトに「agent-kaizen スキルの『専用セッション』の節に従い、Issue #N を担当して」とあるときは、このセッションは
その Issue 1 件だけを担当する。ほかの作業は引き受けない。

1. Monitor ツールで `agent-kaizen-watch.sh <N>` をバックグラウンドで起動する。出力が 1 行出るたびにそれがユーザーの番の知らせになる
2. **質問**（エージェントが Issue に書いて止まった）: Issue の最新コメントを `gh issue view <N> --repo akmaru/dotagents --comments`
   で読み、質問を `AskUserQuestion` でユーザーに出す。`AskUserQuestion` で止まると、hook が herdr に blocked を報告する
3. **答えの投稿**: ユーザーの答えをコメント本文に整え、**本文を見せて確認を取ってから**
   `gh issue comment <N> --repo akmaru/dotagents --body-file <ファイル>` で投稿する。本文の先頭に `@claude` を含める
   （改善ループが再開する条件）。公開リポジトリなので、「手順」3 の「公開してよい内容にする」を守る。確認なしでは投稿しない
4. **PR が出た**: PR の URL と、本文の「試し方」「確かめていないこと」をユーザーに伝える。試して approve するのはユーザー。
   直してほしい点があれば、2.〜3. と同じ手順で `@claude` 付きコメントにする
5. **完了**（merge された・Issue が閉じられた）: その旨をユーザーに伝え、監視を止めてセッションを終える

## 本文の形

```markdown
## 種類

課題 / 要望

## 何が起きたか / 何をしたいか

## どうなってほしいか

## 文脈

- 関係しそうな部品: <パス>
- 再現: <手順>

## 起票元

`agent-kaizen` スキルで、作業中のセッションから起票した。
```

## しないこと

- 起票の前に自分で直さない。直すのは改善ループのエージェントの仕事で、ユーザーは今の作業に戻る
- ラベルを外して起票しない（ラベルが無いとループが動かない）
