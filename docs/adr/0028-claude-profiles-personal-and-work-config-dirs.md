---
status: accepted
date: 2026-10-14
decision-makers: akmaru
---

# Claude Code の設定を個人（~/.claude）と会社（~/.claude-work）の 2 つのディレクトリに分け、会社は個人を土台として参照する

## Context and Problem Statement

これまで dotagents と dotfiles_fixstars は同じ `~/.claude` に書き込んでいた。dotagents が土台を置き
（[ADR 0004](0004-user-config-distribution-symlink-import.md)、[ADR 0009](0009-settings-json-merge.md)）、dotfiles_fixstars が
その上に社内 AI のゲートウェイ設定（settings.json の `env` の `ANTHROPIC_AUTH_TOKEN` など）を重ねる。Team プランへは
`claude --settings ~/.claude/team-auth.json` でゲートウェイの変数を空にし、`/login` のログイン（Team）に戻して切り替えていた。

ここに個人の Max アカウントを加え、会社の環境では「社内 AI / Team / 個人」の 3 つを選んで使えるようにしたい
（[ADR 0027](0027-agent-dx-improvement-loop-via-github-issues.md) の改善ループを個人アカウントで回すため）。
ユーザーが決めた利用ジャーニーは次のとおり:

1. どの環境でも、まず dotagents の install を実行する。Claude はデフォルトで個人アカウントを使う
2. 会社の環境では、次に dotfiles_fixstars の install を実行する。デフォルトは会社（社内 AI）になり、Team と個人も選べる
3. 1 と 2 の後に 1 を再実行すると、個人の設定を更新する。デフォルトは変えない
4. 1 と 2 の後に 2 を再実行すると、会社の設定を更新し、デフォルトを会社にする

問題は、`/login` のログインが設定ディレクトリごとに 1 つしか保存できないこと（macOS の Keychain のエントリは
`CLAUDE_CONFIG_DIR` ごとに分かれる）。Team と個人の 2 つの claude.ai アカウントを `/login` で持つには、ディレクトリを
分けるか、一方を別の認証にする必要がある。

## Decision Drivers

* 上の利用ジャーニー 1〜4 を満たす
* Team と個人のどちらも、claude.ai のコネクタ・Remote Control・`/schedule` を失わない
* dotfiles_fixstars が dotagents の checkout の場所や install.sh の呼び方を知らずに済む（今の依存の形を保つ）
* dotagents の変更が、install の再実行なしで会社のプロファイルにも届く範囲を広く取る

## Considered Options

1. 1 つのディレクトリのまま、一方のアカウントを `claude setup-token` のトークン（`CLAUDE_CODE_OAUTH_TOKEN`）で認証する
2. ディレクトリを個人（`~/.claude`）と会社（`~/.claude-work`）に分ける
    - 2.1. dotfiles_fixstars の install が `CLAUDE_CONFIG_DIR=~/.claude-work` を付けて dotagents の install を呼ぶ
    - 2.2. dotagents の install が、`~/.claude-work` があればそこにも dotagents の層を置く
    - 2.3. dotfiles_fixstars が `~/.claude`（個人プロファイル）を土台として参照する
3. `~/.claude` を symlink にし、向き先を個人と会社で差し替える

## Decision Outcome

選択: **2.3**。ディレクトリを分けることで、2 つの claude.ai ログインをどちらも機能を失わずに持てる。会社のプロファイルは
dotagents の checkout ではなく個人のプロファイル `~/.claude` を参照するので、依存の形は今の「dotagents が先に
`~/.claude` を整えていること」のまま変わらない。

| プロファイル | 設定ディレクトリ | 認証 | 起動 |
|---|---|---|---|
| 個人 | `~/.claude`（`CLAUDE_CONFIG_DIR` は未設定） | `/login`（個人 Max） | `claude-personal`（`CLAUDE_CONFIG_DIR` を外して起動） |
| 会社・社内 AI | `~/.claude-work` | settings.json の `ANTHROPIC_AUTH_TOKEN` | `claude-work` |
| 会社・Team | `~/.claude-work` | `/login`（Team） | `claude-team`（`claude-work --settings team-auth.json`） |

- **dotagents の担当（変更なし）**: これまでどおり `~/.claude` にだけ書き込む。`~/.claude-work` とデフォルトの指定には触れない
- **dotfiles_fixstars の担当**: `~/.claude-work` を次のように組み立てる
  - (a) symlink の層と (c) skill: `~/.claude-work` の各ファイルから `~/.claude` の同じファイルへ、ファイル単位で symlink を張る
    （ディレクトリごと張ると、fixstars の agents や rules が個人のプロファイルに入るため）
  - (b) settings.json: `~/.claude/settings.json` に fixstars のキーを重ねたものを `~/.claude-work/settings.json` として書き出す
  - fixstars の層（`CLAUDE.work.md`、`team-auth.json`、fixstars の agents・rules）は `~/.claude-work` にだけ置く
  - `~/.claude-work/CLAUDE.md` だけは symlink にせず生成する。中身は `@~/.claude/CLAUDE.md`（個人の層）と
    `@CLAUDE.work.md`（会社の層）の 2 つの import。symlink にした CLAUDE.md の相対 import は symlink の実体の
    ディレクトリを基準に解決されるため、symlink のままでは `~/.claude-work` の `CLAUDE.work.md` を読めない（検証結果は下記）
  - `claude-personal` / `claude-work` / `claude-team` を `~/.local/bin` に置く
  - デフォルトを表すファイル `~/.config/claude/profile.env`（`export CLAUDE_CONFIG_DIR=~/.claude-work`）を毎回書く
- **~/dotfiles の担当**: zshrc に「`~/.config/claude/profile.env` があれば読み込む」1 行を置く。ファイルが無い環境
  （個人の Mac）では何も起きず、`~/.claude` がデフォルトになる

ジャーニーとの対応:

| ジャーニー | 起きること |
|---|---|
| 1 | `~/.claude` が作られる。`profile.env` が無いので個人がデフォルト |
| 2 | `~/.claude-work` が組み立てられ、`profile.env` が書かれて会社がデフォルトになる |
| 3 | `~/.claude` が更新される。(a)・(c) は symlink 経由で会社にも届く。`profile.env` は変わらない |
| 4 | `~/.claude-work` の settings.json が作り直され、`profile.env` が書き直される |

### Consequences

* Good: Team と個人の両方が `/login` のログインを持ち、コネクタ・Remote Control・`/schedule` を失わない
* Good: セッション履歴・メモリ・`~/.claude.json` が個人と会社で分かれる
* Good: dotfiles_fixstars は dotagents の checkout の場所を知らない
* Bad: dotagents の settings.json の変更は、1 の再実行だけでは会社のプロファイルに届かない。2 の再実行が要る
* Bad: dotagents が `~/.claude` にファイルを足したり消したりすると、会社のプロファイルの symlink は 2 を再実行するまで
  追従しない
* Bad: 移行が一度だけ要る。いまの `~/.claude/settings.json` から fixstars のキーを抜き、`~/.claude` で個人 Max に、
  `~/.claude-work` で Team に `/login` し直す
* Neutral: GUI から起動する Claude（Desktop アプリ、IDE の拡張）は zshrc を読まないので、`profile.env` のデフォルトに従わない

### Confirmation

現時点で、この決定が守られているかを自動で確かめるチェックは無い。dotagents 側でレビュー時に確かめること:

* `user/install.sh` が `~/.claude-work` と `~/.config/claude/profile.env` に書き込んでいない

## Pros and Cons of the Options

### 1. 1 つのディレクトリのまま、一方をトークンで認証する

* Good: ディレクトリを分けずに済み、今の `--settings` による切り替えの延長で実現できる
* Bad: トークンで認証するアカウントは「モデルへのリクエストしかできない」ため、claude.ai のコネクタ・Remote Control・
  `/schedule` を失う（[Generate a long-lived token](https://code.claude.com/docs/en/authentication#generate-a-long-lived-token)）
* Bad: トークンは有効期間が 1 年で、平文のファイルに置くことになる
* Bad: 個人と会社のセッション履歴・メモリが混ざる

### 2. ディレクトリを分ける（採用）

* Good: 2 つの claude.ai ログインを、どちらも機能を失わずに持てる
  （[Log in with multiple accounts](https://code.claude.com/docs/en/authentication#log-in-with-multiple-accounts)）
* Bad: 会社のディレクトリにも dotagents の層を置く方法を決める必要がある（2.1〜2.3）

#### 2.1. dotfiles_fixstars が dotagents の install を呼ぶ

* Good: 会社のプロファイルにも、dotagents の install と同じ手順で dotagents の層が入る
* Bad: dotfiles_fixstars が dotagents の checkout の場所と、install.sh が `CLAUDE_CONFIG_DIR` を受け付けるという約束を
  知ることになる。今は無い呼び出しの依存が生まれる
* Bad: `user/install.sh` を `CLAUDE_CONFIG_DIR` に対応させる変更が要る

#### 2.2. dotagents の install が会社のプロファイルも更新する

* Good: 呼び出しの依存が生まれない
* Bad: dotagents が会社のプロファイルの場所を知ることになり、ジャーニー 3（1 の再実行は個人の更新）の範囲を超える

#### 2.3. dotfiles_fixstars が個人のプロファイルを土台として参照する（採用）

* Good: 依存の形が今と同じ（dotagents が先に `~/.claude` を整えていること）
* Good: dotagents 側の変更がほぼ要らない
* Bad: settings.json と、ファイルの追加・削除は 2 の再実行まで会社に届かない

### 3. `~/.claude` の向き先を差し替える

* Good: 起動のたびに `CLAUDE_CONFIG_DIR` を指定しなくてよい
* Bad: `CLAUDE_CONFIG_DIR` を設定しないときは Keychain の既定のエントリが使われるので、向き先を差し替えても
  ログインは差し替わらない（ドキュメントからの推論で、未検証）。設定は会社でログインは個人、という食い違いが起きる

## More Information

- 関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)（symlink による配布）、
  [ADR 0009](0009-settings-json-merge.md)（settings.json のマージ）、
  [ADR 0027](0027-agent-dx-improvement-loop-via-github-issues.md)（改善ループ。個人アカウントで回す）
- 出典: [Authentication](https://code.claude.com/docs/en/authentication)（複数アカウント、Keychain のエントリ、認証の優先順位）
- dotfiles_fixstars の変更は、社内の GitLab（repos.fixstars.com）で Issue と MR を立てて進める
- 検証結果（2026-10-14、一時的な `CLAUDE_CONFIG_DIR` で `claude -p` を起動し、`ANTHROPIC_BASE_URL` をローカルの
  ダミーサーバーに向けて、送られた system prompt を記録した）:
  - symlink にした CLAUDE.md の中の相対 import（`@CLAUDE.work.md`、`@./CLAUDE.work.md`）は、symlink の実体の
    ディレクトリのファイルを読んだ。`CLAUDE_CONFIG_DIR` 側の同名ファイルは読まれなかった
  - `CLAUDE_CONFIG_DIR` 直下の実ファイルの CLAUDE.md から、絶対パスの import と相対 import を並べると、両方が読まれた
  - 存在しないファイルの import はエラーにならず、読み飛ばされた
  - `CLAUDE_CONFIG_DIR/skills/<name>` を `~/.claude/skills/<name>`（`apm install -g` が置いた実ディレクトリ）への
    symlink にすると、その skill は一覧に出た
- フォローアップ: 移行後、個人のディレクトリには `CLAUDE.work.md` が無くなるので、`user/CLAUDE.md` の
  「Work-Specific Instructions」節（`@~/.claude/CLAUDE.work.md`）は読み飛ばされるだけの import になる。dotfiles_fixstars の
  変更が入った後に、この節を消すかを決める（先に消すと、移行前の会社の環境で CLAUDE.work.md が読まれなくなる）
