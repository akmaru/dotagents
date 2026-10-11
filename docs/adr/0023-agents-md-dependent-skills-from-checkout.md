---
status: accepted
date: 2026-10-10
decision-makers: akmaru
---

# AGENTS.md が参照する skill は、install.sh が checkout の packages/ から apm install -g する

## Context and Problem Statement

文章の書き方の規則（`clear-writing`）を `user/AGENTS.md` に全文で置くと、毎セッション約 47 行が常時ロードされる。
そこで、毎回の返答に効かせたい核だけを AGENTS.md に残し、詳細と例を marketplace の skill
（`packages/clear-writing/`）に分けた。AGENTS.md の核は「数段落以上の文章では `clear-writing` skill に従う」と
skill を参照する。

AGENTS.md は `user/install.sh` が symlink で配るので、checkout を更新した時点で反映される
（[ADR 0004](0004-user-config-distribution-symlink-import.md)）。一方 marketplace の skill を
`apm install clear-writing@dotagents` で入れると、GitHub の公開版が `~/.claude/skills/` にコピーされる。
このままでは、AGENTS.md だけが新しく参照先の skill が入っていない状態や、push 前の AGENTS.md と公開版の
skill の版が食い違う状態が起こる。AGENTS.md と、AGENTS.md が参照する skill のインストール状態をどう揃えるか。

## Decision Drivers

* AGENTS.md と、AGENTS.md が参照する skill は、同じ版が入っていてほしい
* skill は APM の通常の経路（`apm install`）で入れたい（ユーザーの希望 2026-10-10）
* skill を marketplace に載せたまま、他リポジトリや他マシンからも入れられるようにしたい
* `tests/test_install.py` は HOME を差し替えた環境で install.sh を走らせて検証する。その前提を保ちたい

## Considered Options

1. A: skill を `user/skills/<name>/` に置き、install.sh が `~/.claude/skills/<name>` へ symlink する
2. B: skill を `packages/<name>/` に置き、install.sh がその skill ディレクトリへ symlink する
3. C: skill を `packages/<name>/` に置き、install.sh が checkout の絶対パスで `apm install -g` する
4. C': C と同じだが、`apm install -g <name>@dotagents`（GitHub の公開版）を入れる

## Decision Outcome

選択: **3. C（checkout の絶対パスで `apm install -g`）**（ユーザー決定 2026-10-10）。

- `user/install.sh` の `AGENTS_MD_SKILLS` に AGENTS.md が参照する skill を宣言し、それぞれ
  `apm install -g "<checkout>/packages/<name>" --target claude` する。install.sh は `apm` が無ければ止まる。
- APM 0.26.0 は、ユーザースコープでも絶対パスのローカルパッケージを受け付け、プロジェクト単位と同じ
  コピーの経路で配置する（`apm_cli/install/package_resolution.py` の `user_scope_rejection_reason`）。
  ローカルパッケージを symlink で配置するオプションは無い（`apm_cli/install/phases/local_content.py` は
  パッケージ内の symlink も実体化してコピーし、`apm_cli/integration/skill_integrator.py` は配置先が
  symlink なら拒否する）。

### Consequences

* Good: skill は GitHub を経由せず checkout から入るので、push 前でも AGENTS.md と同じ checkout の版になる。
* Good: APM の通常の経路で入るので、`apm.lock.yaml` に記録され、`apm` のコマンドで管理できる。
* Good: skill は marketplace にも載り、単体で `apm install clear-writing@dotagents` できる。
* Bad: 配置はコピーなので、checkout を更新（`git pull`、ブランチ切り替え、編集）してから install.sh を
  再実行するまでの間は、AGENTS.md だけが新しく skill は古い。
* Bad: install.sh が `apm` コマンドに依存する（これまでは `jq` と `ln` だけ）。
* Bad: `~/.apm/apm.yml` に checkout の絶対パスが記録される。checkout を移動したら install.sh を再実行する。

### Confirmation

`tests/test_install.py` が、HOME を差し替えた環境で install.sh を走らせ、`AGENTS_MD_SKILLS` の skill が
`~/.claude/skills/<name>/SKILL.md` に checkout と同じ内容のコピーとして入ること、`~/.apm/apm.yml` に
checkout の絶対パスが 1 回だけ記録されること（再実行しても重複しない）を検証する。
`tests/test_user_config.py` は AGENTS.md の参照先 `packages/clear-writing/.apm/skills/clear-writing/SKILL.md`
の実在を検証する。

## Pros and Cons of the Options

### 1. A: user/skills/ + symlink

* Good: symlink なので、checkout を更新した瞬間に AGENTS.md と skill の両方が変わり、版が常に一致する。
* Bad: marketplace に載らず、APM の経路でも管理されない。skill の置き場が `packages/` と `user/skills/` に分かれる。

### 2. B: packages/ + symlink

* Good: 版が常に一致し、marketplace にも載る。
* Bad: APM の経路を通らないので、`apm` のコマンドでは管理できない。同じ skill を `apm install` でも入れると
  どちらが残っているか分かりにくい。

### 3. C: checkout の絶対パスで apm install -g（採用）

* Good: APM の通常の経路で、checkout と同じ版が入る。
* Bad: コピーなので、install.sh を再実行するまで版がずれ得る。

### 4. C': GitHub の公開版を apm install -g

* Good: install.sh が checkout のパスに依存しない。
* Bad: push 前は版がずれる。install.sh がネットワークに依存し、`tests/test_install.py` の前提が崩れる。

## More Information

関連: [ADR 0004](0004-user-config-distribution-symlink-import.md)、
[ADR 0010](0010-herdr-plugins-declared-in-install-sh.md)（install.sh に宣言した外部の導入を install.sh が行う先例）、
[ADR 0021](0021-target-claude-code-only.md)。
