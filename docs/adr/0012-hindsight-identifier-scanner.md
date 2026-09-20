---
status: accepted
date: 2026-09-20
decision-makers: akmaru
---

# 識別子の破損はサーバー常駐のスキャナで定期検出し、observation 側は自動修復する

## Context and Problem Statement

`HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese` を設定すると、retain と consolidation のプロンプトから
識別子保護ルール (`_DEFAULT_LANGUAGE_RULE` の "Proper nouns, identifiers, and units stay verbatim.") が
丸ごと外れ、代わりに「エンティティ名を含め全て翻訳しろ」という指示だけが残る
(`engine/consolidation/prompts.py`)。その結果 LLM が識別子を日本語化し、日本語には語間スペースが無いため
区切り文字ごと潰れる。2026-09-20 に `hindsight-mcp-api-key` → `hindsightmcpapikey`、
`t4g.medium` → `t4gmedium`、`i-039d0c0f33dff67be` → `i039d0c0f33dff67be` などが実際に保存されていた。

この設定は [#15](https://github.com/akmaru/dotagents/pull/15) で「日本語で投入した fact が英語や中国語に
翻訳されて保存される」問題を回避するために入れたもので、外すと別の問題が再発する。
consolidation を `claude-sonnet-5` に上げて頻度は大きく下がったが、retain は投入量に比例して呼ばれるため
`claude-haiku-4-5` のまま据え置いており、そちらからの破損は残る。

壊れた値は recall でそのまま返るので、気づかずに設定値をコピーすると実際に動かない。
人手で見つけるのは現実的でなく、検出を自動化したい。

## Decision Drivers

* 壊れたまま放置されないこと（気づくのが数日後でも構わないが、見逃しは困る）
* 検出のために LLM を追加で叩かないこと（コストと、検出器自体が幻覚を見る危険）
* Hindsight 本体のバージョン上げで黙って壊れないこと
* 個人用途なので運用の手数を増やさないこと
* 誤検出で報告が埋もれないこと

## Considered Options

実行場所とトリガ:

1. サーバー常駐 + 定期ポーリング
2. Hindsight の `consolidation.completed` webhook で起動
3. ローカルのスキルとしてセッション開始時に実行

データ取得:

1. REST API
2. Postgres を直接読む

検出後の扱い:

1. 検出のみ。人が直す
2. 自動修復。ただし内容を書き換えない操作に限る
3. 全面的な自動修復（fact 本文の訂正も含む）

## Decision Outcome

選択: **サーバー常駐 + 定期ポーリング**、**REST API**、**軸を分けた部分的な自動修復**。

### なぜ webhook ではないか

`consolidation.completed` のペイロード (`webhooks/models.py` の `ConsolidationEventData`) には
`bank_id` / `operation_id` と件数カウントしか載らず、**どの observation が変わったかが分からない**。
受信しても結局「前回以降に更新されたものを引く」クエリが必要になるので、webhook で得られるのは
レイテンシだけになる。データ品質チェックに即時性は要らないため、HTTP 受信口を増やす対価に見合わない。

ローカル実行（案3）は、マシンが手元にある時しか回らず、サーバーに入った破損の発見が遅れる。

### なぜ Postgres 直読みではないか

内部スキーマに依存すると、Hindsight のバージョンを上げたときに黙って壊れる。
必要なものは REST で揃う: `memories/list` が `source_memory_ids` を返し、
`GET /v1/default/chunks/{chunk_id}` で投入原文が取れる。

### 自動修復の線引き

保存済みデータには「正解 → 生成物」のペアが 2 段ある。

| 軸 | 正解 | 生成物 | 扱い |
|---|---|---|---|
| 軸1 | chunk（投入原文） | 生 fact | 検出のみ |
| 軸2 | 元 fact | observation | 自動修復 |

軸2 の修復は「元 fact を**同じ本文で** PATCH して consolidation に作り直させる」だけで、
内容を一切書き換えない。したがって原理的にデータを壊しようがなく、失敗しても
consolidation の LLM 呼び出しを 1 回無駄にするだけで済む。この安全性があるので人間を挟まない。

軸1 の修復は fact 本文を chunk に合わせて直す＝**内容の書き換え**になるため自動ではやらない。

暴走を止める歯止めとして、同一 fact への修復試行は 2 回まで、修復後は 1 時間のクールダウンを置く
（修復 → 再 consolidation → また破損、のループを防ぐ）。

### 通知

出さない。修復が効く限り人が見る必要はなく、修復できなかったものだけが `report.json` に残る。
SNS でメールを飛ばす案もあったが、Terraform に topic と IAM を足す手数に対して、
飛ぶ頻度がほぼゼロと見込まれるため見送った。実際に修復失敗が出るようになってから足す。

### Consequences

* 良い: 破損が放置されなくなり、observation 側は人手を介さず直る
* 良い: LLM を使わないので、検出コストは実質ゼロ
* 悪い: 検出器が正規表現の塊なので、ルールを足すたびに誤検出のリスクが増える。
  実データで確認した破損と非破損の両方を `tests/test_scanner.py` に回帰ケースとして固定する
* 悪い: 差分走査のために毎回全件引いている。件数の桁が変われば作り直しが要る
* 悪い: これは対症療法で、根治は Hindsight 側で識別子保護を言語設定と独立させること。
  上流に issue を立てる価値がある

## More Information

* 検出ルールと限界: [hindsight/scanner/README.md](../../hindsight/scanner/README.md)
* 根本原因の記述: [hindsight/README.md](../../hindsight/README.md) の「既知の罠」
* consolidation のモデルを上げた経緯: [#23](https://github.com/akmaru/dotagents/pull/23)
