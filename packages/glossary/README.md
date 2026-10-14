# glossary

用語集（`CONTEXT.md` / `CONTEXT-MAP.md`）の書式を 1 か所で定める参照用のスキル。ファイルは作らない。

用語集は、語の**定義**（何であるか）と、語どうしの**構造**（どう関係するか）を同じファイルに持つ。構造は省略
でき、定義だけの用語集もこの書式に従う。

| 何を | どこが |
|---|---|
| 用語集の書式 | このパッケージの [CONTEXT-FORMAT.md](.apm/skills/glossary/CONTEXT-FORMAT.md)（唯一の正本） |
| 用語集の置き場 | `project-layout` |
| 語の定義を書く | `grill-with-docs`、`grill-spec` |
| 構造を書き、検証する | `ontology` |

用語集を読み書きするパッケージは、このパッケージに `../glossary` で直接依存する。書式のコピーは持たない
（[ADR 0026](../../docs/adr/0026-glossary-format-package-and-structure-in-glossary.md)）。

## インストール

単独で入れる必要はない。`grill-with-docs` / `grill-spec` / `ontology` を入れると一緒に入る。

```bash
apm marketplace add akmaru/dotagents
apm install glossary@dotagents
```
