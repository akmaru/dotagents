---
verification: alloy
alloy-scope: 4
---

# 受注

EC サイトで顧客の注文を受け付けてから発送するまでを扱う。スコープ: ある 1 つの時点の、語どうしの関係だけを
扱う。時間に沿った状態の移り変わりは対象外。

## 用語

**当事者（Party）**:
取引の相手になりうる人または組織。
_種別_: kind
_分割_: 個人、法人

**個人（Person）**:
当事者のうち、自然人であるもの。
_種別_: subkind
_上位_: 当事者

**法人（Organization）**:
当事者のうち、組織であるもの。
_種別_: subkind
_上位_: 当事者

**顧客（Customer）**:
当事者のうち、注文を 1 件以上出したもの。
_使わない_: 購入者、クライアント
_種別_: role
_上位_: 当事者
_重なりうる_: 個人、法人
_コード_: Customer

**注文（Order）**:
顧客が商品の購入を申し込んだ記録。
_使わない_: 購入、トランザクション
_種別_: kind
_分割_: 下書きの注文、確定した注文、取り消した注文
_コード_: Order

**下書きの注文（DraftOrder）**:
注文のうち、まだ確定していないもの。
_種別_: phase
_上位_: 注文

**確定した注文（PlacedOrder）**:
注文のうち、確定して発送を待つか発送されたもの。
_種別_: phase
_上位_: 注文

**取り消した注文（CancelledOrder）**:
注文のうち、確定の前後を問わず取り消されたもの。
_種別_: phase
_上位_: 注文

**取り消せる注文（CancellableOrder）**:
注文のうち、今の時点で顧客が取り消してもよいもの。
_種別_: role
_上位_: 注文
_重なりうる_: 下書きの注文、確定した注文
_排他_: 取り消した注文

**発送（Shipment）**:
確定した注文の商品を倉庫から送り出した記録。
_種別_: event
_コード_: Shipment

## 関係

| id | name | from | to | mult | inverse | closure | status | meaning |
|----|------|------|----|------|---------|---------|--------|---------|
| R1 | places | 当事者 | 注文 | set | one | closed | confirmed | [[当事者]] が [[注文]] を出す。記録された組がすべて |
| R2 | target | 発送 | 注文 | one | lone | closed | confirmed | [[発送]] が送り出す [[注文]]。記録された組がすべて |

## 公理

### AX1: 顧客の定義
- form: 定義
- subject: 顧客
- statement: [[当事者]] が [[顧客]] であるのは、その当事者が [[注文]] を 1 件以上出している場合であり、かつその場合に限る
- alloy: `Customer = places.Order`

### AX2: 発送の対象
- form: 必要条件
- subject: 発送
- statement: [[注文]] が [[発送]] の対象であるのは、[[確定した注文]] の場合に限る
- closure: 否定
- closure-note: [[確定した注文]] でも、発送の対象であるとは限らない（発送を待つものがある）
- alloy: `Shipment.target in PlacedOrder`

### AX3: 取り消せる注文の定義
- form: 定義
- subject: 取り消せる注文
- statement: [[注文]] が [[取り消せる注文]] であるのは、注文の段階に応じて下の表の条件を満たす場合であり、かつその場合に限る
- depends: 注文、AX2
- alloy: `CancellableOrder = DraftOrder + (PlacedOrder - Shipment.target)`

| 注文 | 取り消せる注文である条件 |
|---|---|
| 下書きの注文 | 常に |
| 確定した注文 | [[発送]] の対象でない場合 |
| 取り消した注文 | なし |

### AX4: 発送された注文は取り消せない
- status: retired
- merged-into: AX3
- statement: [[発送]] の対象になった [[注文]] は、[[取り消せる注文]] であってはならない

## 帰結

### CHK1: 取り消した注文は発送されない
- statement: [[取り消した注文]] を対象にする [[発送]] は無い
- grounds: AX2、注文
- alloy: `no CancelledOrder & Shipment.target`

### CHK2: 発送された注文は取り消せない
- statement: [[発送]] の対象になった [[注文]] は [[取り消せる注文]] ではない
- grounds: AX3、AX2
- alloy: `no CancellableOrder & Shipment.target`

## 事例

### SC1: 法人が顧客になる
- expect: possible
- statement: [[法人]] が [[注文]] を出して [[顧客]] になる
- grounds: AX1
- alloy: `some Organization & Customer`

### SC2: 2 つの当事者が 1 つの注文を出す
- expect: impossible
- statement: 1 つの [[注文]] を 2 つの [[当事者]] が出す
- grounds: R1
- alloy: `some o: Order | not lone places.o`

### SC3: 下書きの注文が発送される
- expect: impossible
- statement: [[下書きの注文]] が [[発送]] の対象になる
- grounds: AX2
- alloy: `some DraftOrder & Shipment.target`

### SC4: 発送を待つ確定した注文を取り消す
- expect: possible
- statement: まだ [[発送]] の対象でない [[確定した注文]] が [[取り消せる注文]] である
- grounds: AX3、AX2
- alloy: `some (PlacedOrder & CancellableOrder) - Shipment.target`

## 未決事項

- Q1: 取り消しの後に発送済みの記録をどう扱うか（返品と同じか）（related: 取り消した注文、発送）

## 対象外

- 支払い、請求、返品は扱わない
- 注文の状態の時間に沿った移り変わり（下書き → 確定 → 取り消し）は扱わない。ある時点の状態どうしの関係だけを扱う
