# explainer pane と transcript digest の設計

メインセッション（オーケストレータ）と同じ herdr タブの固定 pane に、解説役の Claude セッション
（explainer）を常駐させる仕組み。決定の記録は [ADR 0016](../adr/0016-explainer-pane-transcript-digest.md)、
役割定義の形式と配布は [ADR 0014](../adr/0014-agent-roles-dual-key-per-file-symlink.md)。
本書は機構の説明で、段階 1b の実装仕様を兼ねる（2026-09-22 時点、Claude Code 2.1.278 / herdr 0.9.0）。

## 要件

1. 聞きたいことが増えても pane やセッションが増殖しない。
2. explainer はメインと同じタブの別 pane に常にある。話題が終わったらそこで文脈を区切り、
   新しい話題は新しい文脈で扱える。
3. メインの作業状態・会話状態を explainer に逐一食わせる手段がある。

サブエージェントでは成立しない（ユーザーと対話できず、会話履歴も持たない）。fork（`--resume
--fork-session`）は履歴を継承できるが、話題ごとに fork し直す運用になり、メインの会話が長いと fork も
同じ量の文脈を抱えて始まる。そこで**常駐セッションがメインのトランスクリプトを読む**方式を採る。

## 3 つの部品

```
[herdr キー prefix+alt+f]
   │ フォーカス pane = メイン と決め、ラベル main を付ける
   ▼
explainer-pane.sh ──起動──▶ 固定 pane: claude --agent explainer -n explainer
                              │ 質問のたびに Bash から
                              ▼
                        claude-main-digest.sh ──herdr pane get──▶ メインの現在の session id / cwd
                              │
                              ▼
                        ~/.claude/projects/<cwd>/<session id>.jsonl を直近 N ターンに整形して出力
```

| 部品 | 置き場所 | 役割 |
|---|---|---|
| 役割定義 `explainer.md` | `user/agents/`（`~/.claude/agents/` へ symlink） | system prompt、`disallowedTools`、`initialPrompt` |
| 起動スクリプト `explainer-pane.sh` | `user/herdr/scripts/` | メイン pane の指定、固定 pane の作成・再利用、explainer の起動 |
| 整形スクリプト `claude-main-digest.sh` | `user/bin/`（`~/.local/bin/` へ symlink） | メインのセッション特定とトランスクリプトの整形 |
| キーバインド | `user/herdr/config.toml` | `prefix+alt+f` → `explainer-pane.sh` |

既存の fork スクリプト（`prefix+f`）は改造しない。共通部（通知・pane 分割・busy リトライ）は当面複製し、
3 本目が出たら共通化する。

## メイン pane の特定（確定事項）

herdr は Claude Code の SessionStart フック（`herdr integration install claude` が登録）経由で、
各 pane の Claude セッション ID を **pane 単位**で保持する。フックは Claude 自身のフック入力にある
`session_id` を、herdr が pane の環境に注入した `HERDR_PANE_ID` と共に報告するので、画面出力に依存しない。
`/clear` や resume でも再報告される。サブエージェントは報告しない。

ただし「どの pane がメインか」は herdr が決めない。次の規約で決める。

- キーを押した時点のフォーカス pane（`HERDR_ACTIVE_PANE_ID`）をメインとみなす。
- explainer 起動時に `herdr pane split --env HERDR_MAIN_PANE_ID=<pane_id>` で初期値を渡す。
- 同時に `herdr pane rename <pane_id> main` でラベルを付ける（pane 枠に表示され、人間にも見える）。
  同タブの他 pane に付いている `main` は外し、常に 1 つにする。
- explainer は質問のたびに**現在の**値を引き直す。解決順:
  1. `--pane <id>`（手動指定）
  2. `--file <jsonl>`（herdr を使わない。テストと herdr 無し環境用）
  3. 現在のタブ（`herdr pane get $HERDR_PANE_ID` の `tab_id`。環境変数の tab_id は pane 移動で古くなる）で
     `label == "main"` の pane
  4. `HERDR_MAIN_PANE_ID`（pane が存在し `agent == "claude"` のとき）
  5. 同タブで `agent == "claude"` かつ自分以外の pane がちょうど 1 つ
  6. 失敗: exit 2。stderr に候補（pane_id / label / タイトル / 状態）を出し、explainer はユーザーに確認する
- pane が決まったら `herdr pane get <pane>` で `agent_session.value`（session id）と `foreground_cwd` を取る。
  `agent != "claude"` または `agent_status == "unknown"` なら exit 3（Claude 終了直後の古い値を弾く）。
- トランスクリプトは `find ~/.claude/projects -maxdepth 2 -name "<session id>.jsonl"` で探す
  （ディレクトリ名は cwd の `/` と `.` が `-` に置換されるので、自前変換より find が安全）。無ければ exit 4。

## explainer pane の再利用（確定事項）

explainer pane にもラベル `explainer` を付け、同タブで `label == "explainer"` の pane を探す。

- 無ければ split して起動する。
- あって Claude が居れば、`main` ラベルの付け替えとフォーカスだけ行う。
- あって Claude が居なければ（`/exit` 後など）、その pane に `herdr agent start` で再起動する。

herdr のエージェント名（`herdr agent list` の `name`）は `herdr agent start NAME` で起動したときしか
付かないため、名前ではなくラベルで判定する。

## 起動スクリプトの手順

1. フォーカス pane が Claude で、セッション ID が報告済みであることを確認する（fork スクリプトと同じ前提）。
   フォーカス pane 自身が `explainer` なら「メインの pane で押す」と通知して終了。
2. フォーカス pane に `main` ラベル、同タブの他 pane から `main` を外す。
3. 同タブの `explainer` ラベル pane を探し、上記の再利用規則に従う。
4. 新規なら `herdr pane split --cwd <メインの foreground_cwd> --env HERDR_MAIN_PANE_ID=<pane> --no-focus`。
   横長なら右、縦長なら下（fork スクリプトの判定を流用）。
5. `herdr agent start explainer --kind claude --pane <new> --timeout 60000 -- --agent explainer -n explainer`
   （分割直後の busy はリトライ）。`herdr pane rename <new> explainer`。
6. フォーカスを explainer に移し、通知する。

herdr が無い環境では別端末で `claude --agent explainer -n explainer` を起動し、質問時に
`claude-main-digest.sh --file <jsonl>` を使う（session id は `claude agents --json` で分かる）。

## 整形スクリプト `claude-main-digest.sh` の仕様

```
claude-main-digest.sh [--pane ID | --file JSONL] [--turns N] [--since UUID]
                      [--with-results] [--max-chars N] [--resolve-only]
```

- `--turns N`（既定 6）: 直近 N 個の「ユーザーのテキストターン」から末尾まで。
- `--since UUID`: 前回出力末尾の cursor 以降だけ。見つからなければ警告して既定窓。
- `--with-results`: ツール結果を 300 字まで載せる（既定は載せない）。
- `--max-chars N`（既定 12000）: 超過分は古い側から落とし `(truncated: N entries dropped)` を出す。
- `--resolve-only`: ヘッダ 1 行だけ（起動直後の `initialPrompt` 用）。

選別規則（実トランスクリプトの構造に合わせる）:

- 「ターン」は `type == "user"` かつ `message.content` が文字列または text ブロック配列で、`isMeta` でない行。
  ツール結果のラッパー（`content` が `tool_result` 配列。user 行の 7 割を占める）はターンに数えない。
- `isSidechain` が true の行（サブエージェント側）は除外。`attachment` / `system` / `thinking` / メタ行
  （`<local-command`、`<command-name`、`isMeta`）は除外。
- assistant はブロックごとに別行で `message.id` が共通なので、`message.id` で束ねて 1 応答にする。
  text は 2000 字で切り、`tool_use` は `- tool <name>: <input の最初の値 160 字>` の 1 行にする。
- 行単位で `jq -R 'fromjson? // empty'` として、書き込み中の末尾不完全行や壊れた行は捨て、捨てた件数を
  ヘッダに出す。有効行 0 件は exit 0 で `entries 0/0`（起動直後・`/clear` 直後は正常）。
- exit 5 は「ファイルが非空なのに有効行 0」に限定する（形式変化の疑い）。

出力:

```
# main: pane w5:p1 · session 54dcea44 · cwd /Users/maru/ghq/github.com/akmaru/dotagents · entries 412–471/471 · claude 2.1.278
## 06:31 user
<本文>
## 06:31 assistant
<text>
- tool Bash: ls -la && cat apm.yml…
cursor: <最後の uuid>
```

終了コード: 0 正常 / 2 メイン未特定 / 3 メイン pane に Claude が居ない / 4 トランスクリプト無し /
5 整形失敗（形式変化の疑い）。

## explainer 本文に書くこと

- 質問を受けたら答える前に `claude-main-digest.sh` を実行する。同じ話題の 2 問目以降は前回の `cursor` を
  `--since` に渡し差分だけ読む。足りなければ `--turns` を増やす、`--with-results` を付ける、対象ファイルを
  直接読む。
- exit 2 なら候補を提示してユーザーに確認し、以後 `--pane` で呼ぶ。exit 3 / 4 は 1 行で伝え推測しない。
  exit 5 は形式変化の疑いとして伝え、古い情報で説明しない。
- 話題の区切り: 「この話題は終わり」と言われたら（または話題が明らかに変わったら）、理解済みの概念・
  つまずき・好む深さを Hindsight に 1 件 retain し（context `explainer: <話題>`、tags `project:<repo>` と
  `role:explainer`）、`/clear` で区切るようユーザーに伝える（自分では実行できない）。話題の開始時に
  同じタグで recall する。共通規則の retain とは重複させない。
- description に「サブエージェントとしては起動しない。`claude --agent explainer` で常駐起動する専用」と書き、
  自動委譲を防ぐ。
- `initialPrompt` で `claude-main-digest.sh --resolve-only` を実行し、メインの pane とセッションを 1 行で
  報告して待機する。紐付けの不備が起動直後に見える。

## テスト（段階 1b で追加）

- `tests/test_herdr.py`: `explainer-pane.sh` を指すバインドが `type = "shell"` で実行可能なスクリプトを指し、
  `--agent <x>` の `<x>` が `user/agents/<x>.md` に存在すること。
- `tests/test_user_config.py`: `user/bin/claude-main-digest.sh` が実行可能で `install.sh` が `~/.local/bin` へ
  配ること。`explainer.md` の description に「サブエージェントとしては起動しない」の趣旨があること。
- `tests/test_transcript_digest.py` + `tests/fixtures/transcript-sample.jsonl`: 実トランスクリプトから jq で
  抽出して匿名化した十数行（配列 content、`message.id` 分割、`isMeta`、tool_result ラッパー、`isSidechain`、
  壊れた行を含む）。`--file` 経路で選別・束ね・`--since`・`--max-chars`・終了コードを検証する。
  `DOTAGENTS_REAL_TRANSCRIPT=1` のときだけ手元の最新トランスクリプトで流すスモークで形式ドリフトを早期検知する。
- 手動: `prefix+alt+f` でメイン枠に `main`、隣に `@explainer`。同タブに別の Claude pane があってもメインが
  選ばれる。別 pane で押すと `main` が付け替わる。メインを `/clear` した後の質問で新しい session id を引く。
  explainer を `/clear` しても `@explainer` のまま。

## 失敗モードと緩和

| 失敗 | 挙動 | 緩和 |
|---|---|---|
| Claude を herdr 外や連携導入前に起動 | セッション ID 未報告 → exit 3 | fork スクリプトと同じ前提。通知で知らせる |
| メイン pane を閉じて作り直した | pane_id が変わる → ラベルで解決、無ければ候補提示 | キーをもう一度押せば付け直る |
| 同タブに fork した Claude pane がある | 解決順 5 は失敗するが 3 / 4 で決まる | ラベルと環境変数を先に見る |
| JSONL の形式が変わった | exit 5 | fixture とローカルスモークで検知。ヘッダの Claude 版で切り分け |
| 書き込み中の不完全行 | 行単位で捨てて件数表示 | jq の行単位パース |
| 既定窓が大きすぎる / 小さすぎる | トークン消費 / 情報不足 | 既定 6 ターン・1.2 万字から手動確認で調整 |

## 未検証事項

- `herdr pane get` の `agent_session` が Claude 終了後に残るか（`agent` フィールドで弾くので影響は小さい）。
- compaction 後のトランスクリプトの形（`isCompactSummary` 行）。
- `/clear` 後も `--agent` のプロンプトとツール制限が保たれるか。
