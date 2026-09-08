---
status: accepted
date: 2026-09-08
decision-makers: akmaru
---

# herdr プラグインは install.sh でコミット固定して宣言配布する

## Context and Problem Statement

herdr 0.8.2 のプラグイン機構（`herdr plugin install <owner/repo>`）を使い始め、2 つを採用した。

* [kryptamine/herdr-auto-title](https://github.com/kryptamine/herdr-auto-title) — タブ名を作業内容から自動生成する
* [persiyanov/herdr-reviewr](https://github.com/persiyanov/herdr-reviewr) — エージェントの差分をレビューし、行コメントを
  エージェントの入力欄へ送る

`user/herdr/config.toml` にはこれらを呼ぶキーバインドが入っており（[ADR 0008](0008-herdr-config-in-dotagents.md)）、
設定だけが symlink で配られてプラグイン本体が無い状態になる。他マシンでも同じ構成を再現する方法が要る。

`user/` の既定は symlink 配布だが、プラグインの状態は symlink できない。
`~/.config/herdr/plugins.json` は `manifest_path` / `plugin_root` の絶対パスと `installed_unix_ms`、
インストール時にリポジトリごとに生成されるハッシュ付きディレクトリ名（`herdr.auto-title-4b7d61f48ce8`）を持つ。
実体の `~/.config/herdr/plugins/` にはビルド成果物（Go バイナリ、12MB の Rust バイナリ）が入る。

## Decision Drivers

* 他マシンで `user/install.sh` 一発で同じプラグインが入ること
* マシン間で解決先コミットがドリフトしないこと
* ビルド成果物をリポジトリに入れないこと
* herdr 未インストールのマシンでも `install.sh` が失敗しないこと（[ADR 0008](0008-herdr-config-in-dotagents.md) の性質を維持）

## Considered Options

1. `plugins.json` と `plugins/` を symlink 配布する
2. `install.sh` にプラグインを宣言し、コミット固定で `herdr plugin install` する
3. 各マシンで手動 `herdr plugin install`

## Decision Outcome

選択: **「`install.sh` にプラグインを宣言し、コミット固定で `herdr plugin install` する」**。

`HERDR_PLUGINS` 配列に `owner/repo@<40 桁コミット SHA>` を並べ、`herdr plugin list` の
`github:<repo>@<ref>` 表記と突き合わせて未導入のものだけ入れる。

**ref はタグでもブランチでもなくコミットに固定する。** タグでは解決先が動く。実際 auto-title の
`v0.4.0` タグは同じ `version = "0.4.0"` を名乗るデフォルトブランチ HEAD より古く、
タグ指定と無指定で別のコミットが入る。

更新は配列の ref を書き換えて再実行するだけでよい。`herdr plugin install` は同一 id の既存
インストールを replace するため、uninstall は要らない。

### Consequences

* Good: 他マシンで `install.sh` を流すだけで同じコミットのプラグインが入る。
* Good: ビルド成果物（合計 12MB 超）をリポジトリに持たない。ビルドは各マシンで走る。
* Good: 採用したプラグインとその版がリポジトリの diff に残り、更新が意図的な操作になる。
* Bad: 更新が自動追従しない。上流の修正を取り込むには ref の手動更新が要る。
* Bad: auto-title のビルドに Go が要るなど、プラグインごとの依存が暗黙に増える。失敗しても
  `install.sh` 全体は止めず警告にとどめる。
* Neutral: 初回導入後はプラグインが起動していない。herdr サーバがセッションを復元するときに
  起動するため `herdr server stop` が別途要る（`herdr server reload-config` では起動しない）。

### 外部コマンドは PATH を明示する

`config.toml` の `[[keys.command]]` から呼ぶ外部コマンド（lazygit の popup など）は、
絶対パスか `PATH=` の明示が要る。herdr サーバはデーモン化されており PATH が
`/usr/bin:/bin:/usr/sbin:/sbin` まで削られている。通常のペインは login shell 起動でフル PATH を
得るが、カスタムコマンドはその経路を通らない。補わないと exit 127 で popup が即閉じし、
キーバインドが効いていないようにしか見えない。

### Confirmation

`tests/test_herdr.py` が、宣言された ref が 40 桁コミットであること、`plugin_action` の
キーバインドに対応するプラグインが宣言されていること、`popup` / `pane` のコマンドが
絶対パスか PATH 明示を持つことを検証する。
`tests/test_install.py` は呼び出しを記録するだけの `herdr` スタブを PATH に置き、宣言された
各プラグインが固定 ref 付きで install されること、および `DOTAGENTS_SKIP_HERDR_PLUGINS=1` で
打たれないことを検証する。

スタブが必要なのは、herdr が設定ディレクトリを `$HOME` ではなく OS のユーザーから解決するため。
`HOME` を差し替えても `~/.config/herdr` は実ユーザーのものが使われる（`HOME=/tmp/x herdr plugin
config-dir` が実ユーザーのパスを返す）。他のテストのように偽 HOME では隔離できず、実バイナリを
呼ばせると実行した開発機にプラグインが入ってしまう。

## Pros and Cons of the Options

### 1. `plugins.json` と `plugins/` を symlink 配布

* Good: `user/` の既定である symlink 配布に揃う。
* Bad: `plugins.json` が絶対パスとインストール時刻を持ち、マシン間で成立しない。
* Bad: ビルド成果物をリポジトリに入れることになり、プラットフォーム依存のバイナリを抱える。

### 2. `install.sh` で宣言配布（採用）

* Good: 再現性があり、リポジトリはテキストだけを持つ。
* Bad: 更新が手動。

### 3. 手動 install

* Good: 仕組みが要らない。
* Bad: マシン間でドリフトする。config.toml のバインドだけが配られて本体が無い状態が起きる。

## More Information

関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)（`user/` の symlink 配布方式）、
[ADR 0008](0008-herdr-config-in-dotagents.md)（herdr 設定を dotagents で管理する）。
参考: [herdr plugins](https://herdr.dev/docs/plugins/)、[herdr marketplace](https://herdr.dev/docs/marketplace/)。
