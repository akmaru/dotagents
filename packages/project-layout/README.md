# project-layout

リポジトリの標準構成と、ADR・仕様書・用語集・公開ドキュメントの置き場の決め方を定める参照用のスキル。
ファイルは作らない。作るのは [init-project](../init-project/)。

- `SKILL.md`: 置き場の決め方と標準のツリー
- `layout.json`: 機械可読の定義。`init-project` のスクリプトが読む

`init-project`・`madr-writer`・`grill-with-docs`・`refine-design` は、このパッケージに相対パス
（`../project-layout`）で依存している。理由は dotagents の
[ADR 0025](https://github.com/akmaru/dotagents/blob/main/docs/adr/0025-project-layout-knowledge-skill.md)。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install project-layout@dotagents
```
