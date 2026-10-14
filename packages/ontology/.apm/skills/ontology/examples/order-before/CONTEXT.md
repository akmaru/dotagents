---
verification: alloy
alloy-scope: 4
---

# 受注（書き直し前）

examples/order/CONTEXT.md を書き直す前の版。lint と Alloy が問題を見つけるべき入力として置いている。

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

**注文（Order）**:
顧客が商品の購入を申し込んだ記録。
_使わない_: 購入、トランザクション
_種別_: kind
_分割_: 下書きの注文、確定した注文、取り消した注文

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

## 関係

| id | name | from | to | mult | inverse | status | meaning |
|----|------|------|----|------|---------|--------|---------|
| R1 | places | 当事者 | 注文 | set | one | confirmed | [[当事者]] が [[注文]] を出す |
| R2 | target | 発送 | 注文 | one | lone | confirmed | [[発送]] が送り出す [[注文]] |

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
- alloy: `Shipment.target in PlacedOrder`

### AX3: 取り消せる注文の定義
- form: 定義
- subject: 取り消せる注文
- statement: [[注文]] が [[取り消せる注文]] であるのは、[[取り消した注文]] でない場合であり、かつその場合に限る
- alloy: `CancellableOrder = Order - CancelledOrder`

### AX4: 発送された注文は取り消せない
- form: 禁止
- subject: 取り消せる注文
- statement: [[発送]] の対象になった [[注文]] は、[[取り消せる注文]] であってはならない
- alloy: `no CancellableOrder & Shipment.target`

### AX5: 取り消せる場合
- form: 十分条件
- subject: 取り消せる注文
- statement: [[下書きの注文]] と、発送前の [[確定した注文]] ならば、顧客が取り消すことができる
- alloy: `DraftOrder + (PlacedOrder - Shipment.target) in CancellableOrder`

| 注文 | 取り消せる注文である条件 |
|---|---|
| 下書きの注文 | 常に |
| 確定した注文 | [[発送]] の対象でない場合 |

## 帰結

### CHK1: 取り消した注文は発送されない
- statement: [[取り消した注文]] を対象にする [[発送]] は無い
- alloy: `no CancelledOrder & Shipment.target`

## 事例

### SC1: 法人が顧客になる
- expect: possible
- statement: [[法人]] が [[注文]] を出して [[顧客]] になる
- alloy: `some Organization & Customer`

## 対象外

- 支払い、請求、返品は扱わない
