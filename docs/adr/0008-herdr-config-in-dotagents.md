---
status: accepted
date: 2026-09-06
decision-makers: akmaru
---

# herdr の設定は dotagents の user/ で管理する

## Context and Problem Statement

herdr（コーディングエージェント向けのターミナルワークスペースマネージャ）の設定を、汎用の dotfiles と
dotagents のどちらで管理するか。ターミナル multiplexer の設定は本来 dotfiles の領分だが、
「フォーカス中の Claude Code セッションを分岐して隣の pane で開く」キーバインドを実装した結果、
herdr 設定の中身がエージェント依存の資産で占められることが分かった。

具体的には次の 3 つが揃って初めて機能する:

* `~/.config/herdr/config.toml` の `[[keys.command]]` バインド
* そこから起動する `fork-claude-session.sh`（herdr の socket API と `claude --resume --fork-session` を叩く）
* `~/.claude/settings.json` の SessionStart hook（pane と Claude セッション ID の対応を herdr に報告する）

3 つ目はすでに dotagents 管理下（[ADR 0004](0004-user-config-distribution-symlink-import.md)）にあり、
リポジトリを跨ぐと整合が取れない。

## Decision Drivers

* エージェント連携部分と設定を同じリポジトリに置き、片方だけ古い状態を作らない
* 他マシンへの展開を `user/install.sh` 一発で完結させたい
* herdr のランタイムデータ（socket・log・`session.json`）は決して巻き込まない
* dotfiles / dotagents のスコープ境界をこれ以上曖昧にしない

## Considered Options

1. dotfiles で管理する（ターミナル設定としての分類を優先）
2. dotagents の `user/herdr/` で管理する
3. 管理せず各マシンで手動コピーする

## Decision Outcome

選択: **「dotagents の `user/herdr/` で管理する」**。

`user/install.sh` が `~/.config/herdr/config.toml` と `~/.config/herdr/scripts` を symlink し、
同ディレクトリ内のランタイムデータには触れない。[ADR 0004](0004-user-config-distribution-symlink-import.md)
で定義した `user/` の配布先に `~/.config/herdr` を追加する形になる。

分類上は dotfiles 寄りだが、設定の実質がエージェント連携である以上、分類の一貫性より整合性を優先する。

### Consequences

* Good: キーバインド・スクリプト・hook エントリが 1 リポジトリで揃い、`install.sh` だけで他マシンに展開できる。
* Good: hook スクリプト本体（`~/.claude/hooks/herdr-agent-state.sh`）と settings.json のエントリはどちらも
  herdr が生成・更新するため管理対象外にでき、herdr のバージョン更新に自動で追従できる。
* Bad: dotagents がターミナルマルチプレクサの設定も持つことになり、`user/` のスコープが広がる。
* Bad: herdr 自身が `config.toml` に書き込む（`onboarding` など）ため、リポジトリに意図しない差分が出ることがある。
* Neutral: herdr 未インストールのマシンでも `install.sh` は symlink を張るだけで失敗しない。

### hook エントリはマシンローカルに置く

`herdr integration install claude` が書く SessionStart hook は**絶対パス**を含み、herdr は既存エントリとの
重複判定を文字列一致で行う。そのため共有ファイルに `$HOME` 形式で置くと、再インストールのたびに
絶対パス版が追加され hook が二重発火する。

この hook エントリはリポジトリで管理せず、各マシンの `herdr integration install claude` が
ローカルの `~/.claude/settings.json` に書く。`install.sh` は settings.json を symlink ではなく
マージで配るため、そのマシン固有のキーは保持される（[ADR 0009](0009-settings-json-merge.md)）。

### Confirmation

`tests/test_herdr.py` がキーバインドとスクリプトの対応、および `user/settings.json` に
マシン固有の hook が混入していないことを検証する。
`tests/test_install.py` が一時 HOME で symlink 生成と既存 `config.toml` の退避を検証する。

## Pros and Cons of the Options

### 1. dotfiles で管理

* Good: 「ターミナル設定は dotfiles」という分類が保たれる。
* Bad: hook エントリ（dotagents 側）と config・スクリプト（dotfiles 側）が分かれ、片方だけ更新される事故が起きる。
* Bad: 他マシン展開に 2 リポジトリの clone と 2 つの install 手順が要る。

### 2. dotagents の `user/herdr/` で管理（採用）

* Good: エージェント連携資産が 1 箇所に揃う。
* Bad: `user/` のスコープが広がる。

### 3. 手動コピー

* Good: 仕組みが要らない。
* Bad: マシン間でドリフトする。

## More Information

関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)（`user/` の symlink 配布方式）、
[ADR 0009](0009-settings-json-merge.md)（settings.json のみマージで配る）。
参考: [herdr integrations](https://herdr.dev/docs/integrations/)、[herdr configuration](https://herdr.dev/docs/configuration/)。
