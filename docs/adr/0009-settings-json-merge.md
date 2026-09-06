---
status: accepted
date: 2026-09-06
decision-makers: akmaru
---

# settings.json だけは symlink ではなくマージで配る

## Context and Problem Statement

`user/` の配布はネイティブ symlink で行う（[ADR 0004](0004-user-config-distribution-symlink-import.md)）。
しかし `settings.json` だけは他と性質が違い、**マシン固有のキーが後から書き込まれる**。

* `herdr integration install claude` が SessionStart hook を**絶対パス**で書き込む
  （[ADR 0008](0008-herdr-config-in-dotagents.md)）
* Claude Code 自身が `/config` の変更を書き込む
* 将来、所属会社用の settings.json をマージする想定がある

symlink だと `~/.claude/settings.json` への書き込みがそのままリポジトリの実体を書き換える。
`/Users/<name>` を含む hook が commit され、他マシンで動かなくなる。エージェントに作業させることが
多いリポジトリでは `git add -A` による混入事故の確率も無視できない。

なお dotfiles 時代の `install/claude_code.sh` には `jq -s '.[0] * .[1]'` によるマージと
「Not symlink settings.json directly to avoid confusing another settings on updates」という
コメントが存在した。ただし直後に `ln -sf` が走ってマージ結果を上書きしていたため、実効挙動は
symlink であり、dotagents への移管時にマージは引き継がれなかった。本 ADR はその意図を復元する。

## Decision Drivers

* マシン固有のキーをリポジトリに持ち込まない
* 外部ツール（herdr）が書き込む形式に自動で追従する
* 会社用 settings.json をマージする余地を残す
* 配布は `user/install.sh` 一発で完結させる

## Considered Options

1. symlink を維持し、書き込まれたエントリを install 時に正規化する
2. symlink を維持し、マシン固有のエントリを未コミットのまま抱える
3. symlink をやめ、`jq -s '.[0] * .[1]'` でマージする

## Decision Outcome

選択: **「`jq` でマージする」**。`settings.json` のみ symlink 対象から外し、`install.sh` が

```sh
jq -s '.[0] * .[1]' "${HOME}/.claude/settings.json" "${USER_DIR}/settings.json"
```

でローカル × リポジトリを deep merge する。競合したキーはリポジトリ側が勝ち、
ローカルにしかないキー（herdr の `hooks` など）は保持される。
既存の symlink は初回実行時に実ファイルへ置き換える。

`settings.json` 以外（`AGENTS.md` / `CLAUDE.md` / `rules/` / herdr 設定）は symlink のままとする。
これらは外部ツールが書き込まないため、ADR 0004 の「即時反映」の利点をそのまま享受できる。

### Consequences

* Good: リポジトリにマシン固有の値が入らない。`git status` がクリーンに保たれる。
* Good: herdr が hook の書式を変えても追従不要（herdr が書いたものをそのまま残す）。
* Good: 会社用 settings.json はマージ元を増やすだけで載せられる。
* Bad: `/config` で変更した設定がリポジトリに自動で乗らなくなる。versioning したい値は
  `user/settings.json` に手で書く必要がある。
* Bad: `user/settings.json` を編集しても即時反映されず、`install.sh` の再実行が要る。
* Bad: `jq` に依存する（未インストールなら install.sh は明示的に失敗する）。
* Neutral: マージは deep merge だが配列は置換される。`permissions.allow` はリポジトリ側の値で
  丸ごと入れ替わる。

### Confirmation

`tests/test_install.py` が一時 HOME で、settings.json が symlink ではないこと・ローカル固有キーが
残ること・競合キーはリポジトリが勝つこと・旧 symlink からの移行を検証する。
`tests/test_herdr.py` が `user/settings.json` に herdr の hook が混入していないことを検証する。

## Pros and Cons of the Options

### 1. symlink + 正規化スクリプト

* Good: `/config` の変更がそのままバージョン管理に乗る。
* Bad: 正規化スクリプトとそのテストを維持する必要がある。
* Bad: herdr が hook の書式を変えると、正規化が古い形へ書き戻す。失敗が静かで気づきにくい。

### 2. symlink + 未コミットで抱える

* Good: 仕組みが要らない。
* Bad: `git status` が常に dirty になり、無関係な変更のコミット時に部分ステージが必要。
* Bad: マシン固有パスを誤ってコミットする事故が起きやすい。

### 3. `jq` マージ（採用）

* Good: マシン固有のキーとリポジトリの設定を両立できる。
* Bad: 即時反映と `/config` の往復を失う。

## More Information

関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)（`user/` の symlink 配布方式。
本 ADR は settings.json に限りこれを上書きする）、
[ADR 0008](0008-herdr-config-in-dotagents.md)（herdr 設定の管理場所）。
