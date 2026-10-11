# init-project

リポジトリを新規プロジェクトの標準構成と突き合わせ、無いファイルだけを作るスキル。既存のファイルは上書きしない。
GitHub か GitLab か、`SECURITY.md` や issue / PR テンプレートなどの要否は質問で選ぶ。

標準構成の定義は [project-layout](../project-layout/) の `layout.json` にあり、このパッケージは
相対パス（`../project-layout`）で依存している。理由は dotagents の
[ADR 0024](https://github.com/akmaru/dotagents/blob/main/docs/adr/0024-new-project-standard-layout.md) と
[ADR 0025](https://github.com/akmaru/dotagents/blob/main/docs/adr/0025-project-layout-knowledge-skill.md)。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install init-project@dotagents
```

## 構成

- `SKILL.md`: 入力の集め方・質問・報告の手順
- `scripts/init_project.py`: 存在の確認と作成（Python 標準ライブラリのみ）。隣の `project-layout/layout.json` を読む
- `templates/<id>`: 作るファイルのテンプレート。名前は `layout.json` の `id`

## 開発中に試す

push する前の変更をディレクトリ指定で `-g` インストールすると、APM 0.31.0 では相対パスの依存
（`project-layout`）が配置されない。2 つとも指定して入れる。

```bash
apm install -g <dotagents>/packages/project-layout <dotagents>/packages/init-project
```
