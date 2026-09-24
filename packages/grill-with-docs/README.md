# grill-with-docs

リポジトリの中で、計画・設計をラウンド形式で問い詰めながら、決まった用語を `CONTEXT.md` に、
戻しにくい決定を ADR に**その場で**書き残すスキル。`grill-me` はセッションを頭の中に残すが、
こちらはファイルとして残す（stateful）。

[mattpocock/skills](https://github.com/mattpocock/skills) の `grill-with-docs`（`grilling` + `domain-modeling`
への 1 行委譲）を、単体で動く 1 スキルに畳んで日本語化したもの。ADR の書式はこのリポジトリの正典である
`madr-writer`（MADR）に合わせている。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install grill-with-docs@dotagents
```

## 使い方

```
/grill-with-docs
```

リポジトリの中で変更の計画がまだ曖昧なとき、用語が定まっていないときに使う。
リポジトリの外の話題（コードの無い計画）は `grill-me`。

セッションから出てくるもの:

| 決まったもの | 行き先 |
|---|---|
| 用語（このプロジェクト固有の言葉） | `CONTEXT.md`（決まった瞬間にその場で） |
| 戻しにくく、文脈なしでは意外で、実際のトレードオフだった決定 | `docs/adr/`（MADR 形式） |
| それ以外の決定 | 会話の中だけ。最後のまとめで拾う |

## スキル一覧

| スキル | 内容 |
|--------|------|
| `grill-with-docs` | ラウンド形式のインタビュー + 用語集と ADR のインライン更新 |
