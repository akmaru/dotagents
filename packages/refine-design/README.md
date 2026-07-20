# refine-design

設計判断が固まる前に、それを批判的に検証してリファインするスキル。代替案の洗い出し・トレードオフの明確化・
既存の設計判断（`docs/adr`）との整合／シナジー／矛盾の確認・弱い根拠への指摘を行う。

決まった判断を記録する [madr-writer](../madr-writer/) と対になる: **refine-design は「決める」まで、
madr-writer は「残す」まで**を担う。

## インストール

```bash
apm marketplace add akmaru/dotagents
apm install refine-design@dotagents
```

## 使い方

機能開発やプランで設計方針・アプローチを議論するときに発動する（スラッシュコマンドでも起動できる）:

```
/refine-design
```

## スキル一覧

| スキル | 内容 |
|--------|------|
| `refine-design` | 設計判断を代替案・トレードオフ・既存決定との整合の観点で審議・リファインするスキル |
