# ONTOLOGY.md の書式

`scripts/ontology.py` が読める形。完全な例は [examples/order/ONTOLOGY.md](./examples/order/ONTOLOGY.md)。

## 全体

```md
---
verification: markdown   # markdown | alloy
alloy-scope: 4           # Alloy で探す各集合の要素数の上限（alloy のときだけ使う）
glossary: CONTEXT.md     # 用語集の相対パス。省略すると同じディレクトリの CONTEXT.md
---

# {コンテキスト名} のオントロジー

{1〜2 文で範囲を書く。}

## 用語
## 関係
## 公理
## 帰結
## 事例
## 未決事項
## 対象外
## 変更履歴
```

節の見出しは上の日本語か、英語（Terms / Relations / Axioms / Checks / Scenarios / Open Questions / Non-Goals /
Changelog）。

## 用語

1 語につき `###` 見出し 1 つ。見出しは用語集と同じ `語（English）` の形にする。括弧の中は別名として扱い、
識別子として使える別名があれば Alloy ではそれを名前にする。

```md
### 顧客（Customer）
- kind: role
- is-a: 当事者
- status: confirmed
- overlaps: 個人, 法人
- code: Customer, customer_id
```

| 欄 | 必須 | 値 |
|---|---|---|
| `kind` | ○（`open` の間は空でよい） | 下の「種別」のいずれか |
| `status` | ○ | `confirmed`（確定）/ `assumed`（暫定で採る）/ `open`（未決、制約として使わない）/ `rejected`（使わない） |
| `is-a` | subkind・role・phase では ○ | 上位の語。複数なら `,` 区切り（すべての共通部分に属する） |
| `partition` | | 下位の語の組で、互いに排他かつ全体を網羅するもの。組が複数なら入れ子の箇条書きで 1 行 1 組 |
| `disjoint-children` | | 下位の語の組で、互いに排他（網羅はしない） |
| `covering` | | 下位の語の組で、全体を網羅する（重なってよい） |
| `overlapping-children` | | 下位の語の組で、互いに重なりうると明言するもの |
| `complete` | | `no`（下位の語で網羅されないと明言）/ `open`（未決）。網羅するなら `partition` か `covering` を使う |
| `overlaps` | | この語と重なりうると明言する語 |
| `disjoint` | | この語と排他な語（兄弟でなくてよい） |
| `code` | | 実装上の識別子。`scan` が実装に残っているか確かめる |
| `id` | | Alloy での名前を明示するとき |
| `replaced-by` | rejected では ○ | 代わりに使う語 |
| `definition` | 用語集が無いときだけ | 用語集があれば書かない（定義の正は用語集） |
| `note` | | 補足。`[[語]]` で他の語を参照できる |

### 種別

UFO / OntoUML の区別を簡略にしたもの。どれにするかの問い方は [GRILL.md](./GRILL.md)。

| kind | 何か | 例 |
|---|---|---|
| `kind` | 実例の同一性を与える最上位の種類。実例は一生その種類のまま | 当事者、注文 |
| `subkind` | kind の下位で、実例は一生それのまま（固定的） | 個人、法人 |
| `role` | 他との関係によって一時的に当てはまる | 顧客（注文を出したから顧客） |
| `phase` | 自分の状態によって一時的に当てはまる | 下書きの注文、確定した注文 |
| `relator` | 複数の語を結びつけること自体が実体になったもの | 契約、雇用 |
| `event` | 起きたこと。時点を持つ | 発送 |
| `value` | 同一性を持たず、値で比べるもの | 金額、住所 |

## 言っていないことを残さない

`lint` は次を `UNSTATED` として警告する。黙っていると「重なりうるのか、たまたま書いていないのか」を読み手が
区別できないため。

- 同じ親を持つ下位の語の**すべての組**について、排他（`partition` / `disjoint-children` / `disjoint`）か、
  重なりうる（`overlaps` / `overlapping-children`）かのどちらか
- 下位の語を持つ語について、網羅される（`partition` / `covering`）か、されない・未決（`complete: no|open`）か

最上位の語（`is-a` を持たない語）どうしは、互いに排他として扱う（Alloy のトップレベルの sig と同じ）。

## 関係

表 1 つ。`mult` は「from の各実例が、to の実例をいくつ持つか」、`inverse` は「to の各実例が、from の実例から
いくつ指されるか」。値は `one`（ちょうど 1）/ `lone`（0 か 1）/ `some`（1 以上）/ `set`（制約なし）。

```md
| id | name | from | to | mult | inverse | status | meaning |
|----|------|------|----|------|---------|--------|---------|
| R1 | places | 当事者 | 注文 | set | one | confirmed | [[当事者]] が [[注文]] を出す |
```

`name` は Alloy の式で使う名前で、用語と重ねない。

## 公理・帰結・事例

3 つとも `###` 見出し 1 つにつき 1 件。見出しは `ID: 短い題`。`statement` には自然言語で命題を書き、語は
`[[語]]` で参照する（`lint` が未定義の語・使わない語を検出する）。

- **公理**: 正しいと**定める**命題。Alloy では fact になる
- **帰結**: 公理から**導かれるはず**の命題。Alloy では check になり、反例があれば失敗する
- **事例**: 具体的な状況が `expect: possible`（起こりうる）か `impossible`（起こりえない）か。Alloy では
  run になる。grill で開発者が答えた具体例をここに残す

```md
### AX2: 発送するのは確定した注文だけ
- status: confirmed
- statement: [[発送]] の対象は必ず [[確定した注文]]
- alloy: `Shipment.target in PlacedOrder`
```

`alloy:` は 1 行ならバッククォートで、複数行なら直後に ```` ```alloy ```` のコードブロックで書く。
`status` は省略すると `confirmed`。`confirmed` と `assumed` だけが Alloy の検証に使われる。

## 未決事項・対象外・変更履歴

箇条書き。未決事項は `- Q1: 問い（related: 語, 語）` の形にし、`status: open` / `assumed` の語はどれかの
未決事項から `related:` で参照する（`lint` が確かめる）。変更履歴は `- 日付: 何を・なぜ`。
