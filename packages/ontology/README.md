# ontology

用語集（`CONTEXT.md`）の語の間の構造を `ONTOLOGY.md` として持ち、問い詰めて組み立て、仕様・実装・理解の変化に
同期し、検証するスキル。

用語集は「語が何であるか」を定める。`ONTOLOGY.md` は「語どうしがどう関係するか」を定める:

- **種別**: kind / subkind / role / phase / relator / event / value（UFO・OntoUML の区別を簡略にしたもの）
- **包含と排他・網羅**: is-a、汎化集合（partition / disjoint-children / covering / overlapping-children）
- **関係と多重度**: 両方向の多重度（one / lone / some / set）
- **公理・帰結・事例**: 正しいと定める命題、そこから導かれるはずの命題、起こりうる／起こりえない具体例
- **言っていないこと**: 兄弟の語が排他か重なりうるか、網羅されるかを書き漏らすと `lint` が警告する

## 検証の 2 つの方式

`ONTOLOGY.md` の frontmatter の `verification:` で選ぶ。

| 方式 | 機械が確かめること | エージェントが確かめること |
|---|---|---|
| `markdown` | 参照・循環・排他と包含の矛盾・書き漏れ・用語集とのずれ（`lint`） | 帰結と事例を公理から推論する |
| `alloy` | 上に加え、無矛盾性・各語が実例を持てるか・帰結の反例・事例の成否を [Alloy](https://alloytools.org/) で有界に網羅検査。矛盾したときは衝突している制約の極小の組を出す | 反例や衝突を言葉に直して開発者に判断を仰ぐ |

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install -g ontology@dotagents
```

`project-layout` に依存する（用語集の置き場の決め方）。`scripts/ontology.py` は Python 3.10+ の標準ライブラリ
だけで動く。Alloy 方式には Java 17+ が要り、Alloy 6.2.0 の jar は初回に `~/.cache/ontology-skill/` へ取得する
（`ALLOY_JAR` で既存の jar を指せる）。

## 使い方

```
/ontology            # 無ければ雛形を作って grill、あれば検証して grill の続き
/ontology sync       # 仕様書・実装・用語集の変更に追従させる
/ontology verify     # 検証して結果を説明する
```

スクリプトを直接使う:

```bash
ONTO=~/.claude/skills/ontology/scripts/ontology.py
python3 $ONTO init --glossary CONTEXT.md --mode alloy   # 用語集から雛形
python3 $ONTO verify ONTOLOGY.md                         # lint +（alloy なら）Alloy
python3 $ONTO scan ONTOLOGY.md docs/internal/specs src   # 仕様・実装とのずれ
```

例: [examples/order/](.apm/skills/ontology/examples/order/)（`verify` がすべて通る）。

## 他のスキルとの住み分け

- `grill-with-docs` / `grill-spec`: 語と定義を決めて `CONTEXT.md` に書く。このスキルは定義を書かず、その上に構造を
  重ねる。新しい語が要るときは、先に用語集へ定義を書く
- `refine-design`: 設計判断の審議。オントロジーは設計判断の前提（語の構造）を固める

## 開発者向け

- 書式: [FORMAT.md](.apm/skills/ontology/FORMAT.md)、問いの型: [GRILL.md](.apm/skills/ontology/GRILL.md)、
  Alloy への翻訳: [ALLOY.md](.apm/skills/ontology/ALLOY.md)
- テスト: `uv run pytest tests/test_ontology.py`。Alloy を使うテストは `java` と jar（`ALLOY_JAR` か取得済みの
  キャッシュ）があるときだけ走る
