# ontology

用語集（`CONTEXT.md`）に語の**構造**を書き足し、問い詰めて組み立て、仕様・実装・理解の変化に同期し、検証する
スキル。語の定義（何であるか）と構造（どう関係するか）は同じ用語集に並び、語を 1 つ読めば両方が分かる。

- **種別**: kind / subkind / role / phase / relator / event / value（UFO・OntoUML の区別を簡略にしたもの）
- **上位と排他・網羅**: `_上位_`、`_分割_` / `_排他な下位_` / `_網羅する下位_` / `_重なりうる下位_`
- **関係と多重度**: 両方向の多重度（one / lone / some / set）
- **公理・帰結・事例**: 正しいと定める命題、そこから導かれるはずの命題、起こりうる／起こりえない具体例
- **言っていないこと**: 兄弟の語が排他か重なりうるか、網羅されるかを書き漏らすと `lint` が警告する
- **公理の書き方**: 公理は規範文の 4 つの文型（定義・十分条件・必要条件・禁止）で書き（[NORMATIVE.md](.apm/skills/ontology/NORMATIVE.md)）、十分条件・必要条件には
  外側の扱い（否定・未決定・対象外）を添える。定義に別の公理が条件を足す食い違い（C1）、網羅していない場合分け
  （C2）、閉包の書き漏れ（C3）、依存と根拠の参照切れ（C4）を検査する

書式は `glossary` パッケージの `CONTEXT-FORMAT.md` が唯一の正本で、このパッケージは持たない。

```md
**顧客（Customer）**:
当事者のうち、注文を 1 件以上出したもの。
_使わない_: 購入者、クライアント
_種別_: role
_上位_: 当事者
_重なりうる_: 個人、法人
```

## 検証の 2 つの方式

用語集の frontmatter の `verification:` で選ぶ（無ければ markdown）。

| 方式 | 機械が確かめること | エージェントが確かめること |
|---|---|---|
| `markdown` | 参照・循環・排他と上位の矛盾・書き漏れ・定義と上位のずれ・使わない語（`lint`） | 帰結と事例を公理から推論する |
| `alloy` | 上に加え、無矛盾性・各語が実例を持てるか・帰結の反例・事例の成否を [Alloy](https://alloytools.org/) で有界に網羅検査。矛盾したときは衝突している制約の極小の組を出す | 反例や衝突を言葉に直して開発者に判断を仰ぐ |

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install -g ontology@dotagents
```

`project-layout`（用語集の置き場）と `glossary`（用語集の書式）に依存し、一緒に入る。`scripts/ontology.py` は
Python 3.10+ の標準ライブラリだけで動く。Alloy 方式には Java 17+ が要り、Alloy 6.2.0 の jar は初回に
`~/.cache/ontology-skill/` へ取得する（`ALLOY_JAR` で既存の jar を指せる）。

## 使い方

```
/ontology            # 検証して、構造の未記述・未定の点を grill する
/ontology sync       # 仕様書・実装・用語集の変更に追従させる
/ontology verify     # 検証して結果を説明する
```

スクリプトを直接使う:

```bash
ONTO=~/.claude/skills/ontology/scripts/ontology.py
python3 $ONTO verify CONTEXT.md                         # lint +（alloy なら）Alloy
python3 $ONTO scan CONTEXT.md docs/internal/specs src   # 仕様・実装とのずれ
```

例: [examples/order/CONTEXT.md](.apm/skills/ontology/examples/order/CONTEXT.md)（`verify` がすべて通る）と、その書き直し前の
[examples/order-before/CONTEXT.md](.apm/skills/ontology/examples/order-before/CONTEXT.md)（C1〜C4 と、Alloy の反例・充足不能が出る）。

## 他のスキルとの住み分け

- `grill-with-docs` / `grill-spec`: 語を決めて定義を書く。構造の行は消さずに残し、構造を持つ語の定義を変えたら
  まとめで知らせる
- `glossary`: 用語集の書式だけを持つ
- `refine-design`: 設計判断の審議。構造は設計判断の前提（語の関係）を固める

## 開発者向け

- 問いの型: [GRILL.md](.apm/skills/ontology/GRILL.md)、Alloy への翻訳: [ALLOY.md](.apm/skills/ontology/ALLOY.md)
- 決定: [ADR 0026](../../docs/adr/0026-glossary-format-package-and-structure-in-glossary.md)
- テスト: `uv run pytest tests/test_ontology.py`。Alloy を使うテストは `java` と jar（`ALLOY_JAR` か取得済みの
  キャッシュ）があるときだけ走る
