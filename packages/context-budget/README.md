# context-budget

Claude Code のコンテキスト使用量を計測し、削減余地を根拠つきで特定して対処するためのスキル。
計測本体は dotagents の `user/bin/claude-context.py`（`user/install.sh` で `~/.local/bin` に配布）で、
このスキルはその結果の読み方と、削減のレバー・手順をエージェントに教える。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install context-budget@dotagents
```

計測スクリプトは APM パッケージではなく `user/install.sh` が配る（docs/adr/0013）。

## 使い方

```
/context-budget
```

「コンテキストを減らしたい」「どこにトークンを使っているか」と言えば発動する。
SessionStart hook が出す `[context-budget]` の指摘に対応するときにも使う。

手で計測だけしたい場合:

```bash
claude-context.py snapshot --cwd "$PWD"          # 起動直後の内訳を保存（API は呼ばれない）
claude-context.py report --cwd "$PWD" --days 14  # セッションごとの増加要因と削減候補
```

## スキル一覧

| スキル | 内容 |
|--------|------|
| `context-budget` | コンテキスト使用量を計測し、削減候補を提案・適用・再計測するスキル |
