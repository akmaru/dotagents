---
status: accepted
date: 2026-09-23
decision-makers: akmaru
---

# 0019. 出力言語は環境変数で固定せず、retain_mission で地の文の言語に委ねる

## Context and Problem Statement

`HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese` は [#15](https://github.com/akmaru/dotagents/pull/15) で
「日本語で投入した fact が英語や中国語で保存される」を回避するために入れた。しかしこの設定は識別子保護を
巻き添えに落とす。その代償として [ADR 0012](0012-hindsight-identifier-scanner.md) では
`observations_mission` に手書きの override を足し、consolidation を `claude-sonnet-5` に上げ、
破損を検出する常駐スキャナまで置いた。ADR 0012 自身が「これは対症療法で、根治は Hindsight 側で
識別子保護を言語設定と独立させること」と書いている。

2026-09-23 に v0.9.2 のソースを読み、設定を外す余地があるかを確かめた。分かったのは、**retain では
矛盾する 2 つの指示が同時にプロンプトへ載っている**ということだった。設定を外せば識別子保護は戻るが、
言語の保証は失われる。この 2 つをどう両立させるかを決める。

## Decision Drivers

* 識別子が壊れないこと（ADR 0012 が言う「根治」）
* 日本語の会話から日本語の fact が安定して出ること
* 対症療法の部品を増やさないこと。できれば減らすこと
* 上流の実装詳細に張り付きすぎないこと
* 決める前に測れること

## Considered Options

1. 現状維持（`Japanese` 固定 + `observations_mission` の override）
2. `observations_mission` の override を日本語で書き直す
3. `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE` を未設定に戻す
    - 3.1. 外すだけ
    - 3.2. 外したうえで `retain_mission` に言語指示を置く
4. `retain_extraction_mode` を `verbatim` にする

1〜3 は「言語指示をどこに置くか」の選択。4 だけは別軸で、本文の生成自体をやめる案。

## Decision Outcome

選択: **3.2 — 環境変数を外し、`retain_mission` に言語指示を置く**（採用）。

- `hindsight/compose/docker-compose.yml` から `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE` を削除する
- バンクの `retain_mission` に次を設定する。**この文を日本語で書くこと自体が意味を持つ**（後述）

      出力は地の文の言語で書く。コード片・ファイルパス・識別子・英語の引用が多く含まれていても、
      それらは言語判定の材料にしない。

- バンクの `observations_mission` から VERBATIM IDENTIFIERS 段落を撤去する。設定を外すと consolidation に
  `_DEFAULT_LANGUAGE_RULE` が戻り、その中の `Proper nouns, identifiers, and units stay verbatim.` が
  同じ役割を果たすため
- `tests/test_hindsight.py` の pin を反転し、「設定されていないこと」を守らせる

### なぜ外せるのか — v0.9.2 で確かめた構造

consolidation は言語ルールを**二者択一**で組み立てる。`consolidation/prompts.py:177` が
`language_section = "" if llm_output_language else f"{_DEFAULT_LANGUAGE_RULE}\n\n"` であり、
同ファイル `:26-28` のコメントも `the two must never both be present or they contradict each other` と
明記している。

**retain は同じ排他制御をしていない。** `retain/fact_extraction.py:822` の
`LANGUAGE: MANDATORY — Detect the language of the input text (...) STRICTLY FORBIDDEN from translating`
はテンプレート本体にあり消す手段が無く、`:1278` の
`prompt = prompt + output_language_directive(config.llm_output_language)` は条件分岐なしに連結される。
`Japanese` を設定している間、retain のプロンプトには「翻訳は絶対禁止」と「Japanese に翻訳しろ」が
同時に載っていた。ADR 0012 が観測した「生の fact も壊れる」の正体はこれである。

### 実測（`dry-run-extract`、`retain_extraction_mode: concise`、retain は `claude-haiku-4-5`）

コード片と識別子が濃く、日本語の地の文が少ない入力を同一条件で繰り返した。

| 条件 | 日本語 | 英語 | 中国語 | 混在 |
|---|---|---|---|---|
| `Japanese` 固定（現状） | 安定して日本語。ただし `Hindsightサーバー` のように語間スペースが落ちる | - | - | - |
| 3.1 外すだけ（8 回） | **2** | 4 | 1 | 1 |
| 3.2 外す + `retain_mission`（5 回） | **5** | 0 | 0 | 0 |

3.1 でも**識別子そのものは壊れなかった**（`t4g.medium` / `52.199.129.71` / `fact_extraction.py:1278` は
英語出力時も原文のまま）。崩れるのは言語だけで、識別子破損と言語のぶれは別の問題として分離できる。
3.2 では日本語・識別子・語間スペースのすべてが保たれた。

`retain_mission` から「日本語」という語を外した一般形でも 5/5 で日本語になったため、特定言語を
名指ししない文面を採用する。

### mission を何語で書くかが、出力言語を決める

deploy 後に実測して分かったこと。**`retain_mission` 自体の言語が、出力言語の既定として働く。**

| `retain_mission` | 英語だけの入力 | 日本語の入力（コード片あり） |
|---|---|---|
| 設定しない | 英語のまま | 素の状態では 8 回中 2 回しか日本語を保たない |
| 日本語で書く（採用） | **日本語に訳される** | 日本語 |
| 英語で書く | 英語のまま | 日本語 |

文面はどちらも「地の文の言語で書け」と言っているのに、書かれている言語のほうが既定を動かす。

日本語で書くほうを採る。記憶の言語が投入物によって揺れないほうが recall したときに読みやすく、
このバンクの投入元はほぼ日本語の会話なので、英語だけの会話が日本語の fact になる実害は小さい。
ソースの言語をそのまま残したくなったら、mission を英語で書き直せば切り替わる。

### なぜ `observations_mission` ではなく `retain_mission` なのか

* API 仕様の `CreateBankRequest` によれば、`retain_mission` は `Injected alongside built-in extraction
  rules`、`observations_mission` は `Replaces built-in consolidation rules entirely`。前者は既存ルールを
  壊さずに足せる
* 言語がぶれるのは retain（fact 抽出）である。consolidation の `_DEFAULT_LANGUAGE_RULE` は
  「ソースの言語で書く」なので、fact が日本語で安定すれば observation は追随する

### Consequences

* Good: 識別子保護（`Proper nouns, identifiers, and units stay verbatim.`）が consolidation に戻る。
  語間スペースも保たれる
* Good: `observations_mission` の手書き override が不要になり、バンク設定から対症療法が 1 つ減る
* Neutral: 英語だけのソースも日本語の fact になる。`HINDSIGHT_API_LLM_OUTPUT_LANGUAGE` を使っていた頃と
  同じ挙動だが、今度は識別子と語間スペースが保たれる。切り替えたくなったら mission を英語で書き直す
* Bad: **consolidation 側の言語安定性は未検証**。`dry-run-extract` は retain しか通らず、
  consolidation を書き込みなしで試す手段が無い
* Bad: 言語の保証がプロンプト頼みになる。retain が `claude-haiku-4-5` で動く限り、従う保証はない
* Neutral: consolidation を `claude-sonnet-5` に上げた理由（ADR 0012）は前提が変わる。`claude-haiku-4-5`
  に戻せばコストは下がるが、別途検証が要るため本 ADR では触らない
* Neutral: scanner（ADR 0012）は残す。retain の識別子破損が実際に止まったかを測る装置として必要

### Confirmation

* `tests/test_hindsight.py::TestServerAssets::test_compose_pins_known_traps` — compose に
  `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE` が**無い**ことを pin する。これまで `: Japanese` が有ることを
  pin していたので、assert と根拠コメント（`retain translates facts otherwise`）ごと反転する
* `hindsight/scanner/scanner.py` — 識別子破損を定期検出し `report.json` の `finding_count` に出す
  （`scanner.py:327-332`）。設定変更の前後でこの値を比較する。LLM を使わない照合なので判定が揺れない。
  **変更直前のベースライン（2026-09-23T07:07:10Z）: `memories_scanned: 1432` / `finding_count: 47`**。
  47 件はすべて `axis: chunk->fact`（生 fact の破損、`repair: manual`）で、retain 由来。この値が
  増えなくなれば本 ADR の狙いどおり。既存の 47 件は自動では直らないので、減ることは期待しない
* `retain_mission` と出力言語の関係は
  `POST /v1/default/banks/personal/memories/dry-run-extract` で手で測れる。
  **自動テストは無い** — バンク設定はサーバー側にあり、リポジトリにコードが無いため

## Pros and Cons of the Options

### 1. 現状維持

* Good: 言語が安定する。実測でも `Japanese` 固定では日本語から外れなかった
* Bad: 識別子の語間スペースが落ちる
* Bad: 維持のために override・モデル引き上げ・常駐スキャナの 3 つを抱え続ける
* Bad: 英語のソースが日本語に訳され、引用の原文が失われる

### 2. `observations_mission` を日本語で書き直す

* Good: 自分で書いたプロンプトを母語で管理できる
* Bad: 問題の所在が retain 側にあるため、consolidation の文面を変えても本質が動かない
* Bad: `observations_mission` は consolidation を dry-run できず、効果を事前に測れない
* Bad: この override は `output_language_directive` を名指しで打ち消す対抗指示であり、
  勝っている根拠がユーザー側の文面しかない（`_MISSION_PRIORITY_NOTE` が優先権を与えるのは
  PROCESSING RULES / DECISION GUIDE / OUTPUT FORMAT に対してのみで、言語ルールは含まれない）

### 3. 未設定に戻す

#### 3.1. 外すだけ

* Good: 識別子保護と語間スペースが戻る
* Good: 部品が減る
* Bad: 言語が不安定になる。実測で日本語を保ったのは 8 回中 2 回

#### 3.2. 外す + `retain_mission`（採用）

* Good: 3.1 の利点を保ったまま、実測 5/5 で日本語になった
* Good: `retain_mission` は built-in ルールと並存するため、既存の抽出を壊さない
* Good: `dry-run-extract` で事前に測れる
* Bad: consolidation 側は測れないまま残る
* Bad: `retain_mission` を応答フィードバックの収集などに使う場合、1 つの mission に複数の関心事が同居する

### 4. `retain_extraction_mode` を `verbatim` にする

* Good: 本文の書き直し自体が止まるので、識別子破損の余地が原理的に消える
* Bad: 要約されなくなり、recall の粒度と量が変わる。投入経路の設計（[ADR 0017](0017-session-end-retain-hook.md)）が
  前提にしている `concise` を崩す
* Bad: 言語のぶれは別問題として残る

## More Information

* [ADR 0012](0012-hindsight-identifier-scanner.md) — 識別子破損への対症療法。本 ADR はそこで言及された
  「根治」にあたる。scanner は検証装置として引き続き残す
* [ADR 0017](0017-session-end-retain-hook.md) — Consequences 軸 F の
  「`retain_extraction_mode` を `verbatim` にすれば本文の書き直しが止まる」は、本 ADR により前提が変わる
* 根本原因の記述: [hindsight/README.md](../../hindsight/README.md) の「既知の罠」
* 検証に使った上流ソース（v0.9.2）:
  [consolidation/prompts.py](https://github.com/vectorize-io/hindsight/blob/v0.9.2/hindsight-api-slim/hindsight_api/engine/consolidation/prompts.py) /
  [retain/fact_extraction.py](https://github.com/vectorize-io/hindsight/blob/v0.9.2/hindsight-api-slim/hindsight_api/engine/retain/fact_extraction.py) /
  [prompt_utils.py](https://github.com/vectorize-io/hindsight/blob/v0.9.2/hindsight-api-slim/hindsight_api/engine/prompt_utils.py)
* 設定を入れた経緯: [#15](https://github.com/akmaru/dotagents/pull/15)
