---
verification: alloy   # markdown | alloy
alloy-scope: 4        # Alloy で探す各集合の要素数の上限
glossary: CONTEXT.md
---

# 受注 のオントロジー

CONTEXT.md の語の間の構造（種別・包含・排他・関係・公理）を定める。語の定義は CONTEXT.md が正で、ここには書かない。

## 用語

### 当事者（Party）
- kind: kind
- status: confirmed
- partition: 個人, 法人

### 個人（Person）
- kind: subkind
- is-a: 当事者
- status: confirmed

### 法人（Organization）
- kind: subkind
- is-a: 当事者
- status: confirmed

### 顧客（Customer）
- kind: role
- is-a: 当事者
- status: confirmed
- overlaps: 個人, 法人
- code: Customer

### 注文（Order）
- kind: kind
- status: confirmed
- partition: 下書きの注文, 確定した注文, 取り消した注文
- code: Order

### 下書きの注文（DraftOrder）
- kind: phase
- is-a: 注文
- status: confirmed

### 確定した注文（PlacedOrder）
- kind: phase
- is-a: 注文
- status: confirmed

### 取り消した注文（CancelledOrder）
- kind: phase
- is-a: 注文
- status: confirmed

### 発送（Shipment）
- kind: event
- status: confirmed
- code: Shipment

## 関係

| id | name | from | to | mult | inverse | status | meaning |
|----|------|------|----|------|---------|--------|---------|
| R1 | places | 当事者 | 注文 | set | one | confirmed | [[当事者]] が [[注文]] を出す。どの注文も出した当事者はちょうど 1 つ |
| R2 | target | 発送 | 注文 | one | lone | confirmed | [[発送]] が送り出す [[注文]]。1 つの注文の発送は高々 1 回 |

## 公理

### AX1: 顧客とは注文を出した当事者
- status: confirmed
- statement: [[当事者]] が [[顧客]] であることと、[[注文]] を 1 件以上出していることは同値
- alloy: `Customer = places.Order`

### AX2: 発送するのは確定した注文だけ
- status: confirmed
- statement: [[発送]] の対象は必ず [[確定した注文]]
- alloy: `Shipment.target in PlacedOrder`

## 帰結

### CHK1: 取り消した注文は発送されない
- statement: [[取り消した注文]] を対象にする [[発送]] は無い（AX2 と注文の分割から導かれるはず）
- alloy: `no CancelledOrder & Shipment.target`

## 事例

### SC1: 法人が顧客になる
- expect: possible
- statement: [[法人]] が [[注文]] を出して [[顧客]] になる
- alloy: `some Organization & Customer`

### SC2: 2 つの当事者が 1 つの注文を出す
- expect: impossible
- statement: 1 つの [[注文]] を 2 つの [[当事者]] が出す
- alloy: `some o: Order | not lone places.o`

### SC3: 下書きの注文が発送される
- expect: impossible
- statement: [[下書きの注文]] が [[発送]] の対象になる
- alloy: `some DraftOrder & Shipment.target`

## 未決事項

- Q1: 取り消しの後に発送済みの記録をどう扱うか（返品と同じか）（related: 取り消した注文, 発送）

## 対象外

- 支払い、請求、返品はこのオントロジーでは扱わない
- 注文の状態の時間的な遷移（下書き → 確定 → 取り消し）は扱わない。ある時点の状態どうしの関係だけを扱う

## 変更履歴

- 2026-10-13: 例として作成
