# scanner

Hindsight に保存されたテキストから、識別子が壊れていないかを定期検出する常駐サービス。

`HINDSIGHT_API_LLM_OUTPUT_LANGUAGE` を設定すると retain / consolidation のプロンプトから
識別子保護ルールが外れ、LLM が `hindsight-mcp-api-key` を `hindsightmcpapikey` のように
日本語化して潰す。根本原因と経緯は [../README.md](../README.md) の「既知の罠」、
設計判断は [ADR 0012](../../docs/adr/0012-hindsight-identifier-scanner.md) を参照。

LLM は使わない。文字列照合だけなので、走査コストは実質ゼロ。

## 何を比べているか

保存済みのデータには「正解 → 生成物」のペアが 2 段ある。

```
投入テキスト ──retain──▶ 生 fact ──consolidation──▶ observation
   (chunk)                (text)                      (text)
       └──── 軸1 ────────────┘        └──── 軸2 ────────┘
```

| 軸 | 正解 | 生成物 | 破損時の扱い |
|---|---|---|---|
| 軸1 | chunk（投入した原文） | 生 fact | 検出のみ。修正は fact 本文の書き換えになるので人が判断する |
| 軸2 | 元 fact | observation | 自動修復（元 fact を同じ本文で PATCH して作り直させる） |

retain は `claude-haiku-4-5` のままなので、軸1 は今後も破損しうる。軸2 は
`claude-sonnet-5` に上げた経路の回帰監視。

## 判定ルール

正解側にある「区切り文字を含む識別子」だけを対象にする。区切りの無い語
(`Hindsight`, `maru`) は潰れようがないので最初から見ない。

| ルール | 例 |
|---|---|
| `separator-to-space` | `start-session` → `start session` |
| `separator-loss` | `t4g.medium` → `t4gmedium` |
| `prefix-truncation` | `HINDSIGHT_API_CONSOLIDATION_LLM_MODEL` → `..._LLM` + 直後に仮名 |

**生成物に識別子が現れないだけなら破損としない。** 要約で落ちるのは正常なので、
「崩れた形で現れている」ときだけ指摘する。完全形がそのまま含まれていればその時点で無傷と判定するため、
`HINDSIGHT_API_REFLECT_LLM_MODELで` のように助詞が続くだけのケースは拾わない。

## 検出できないもの

- **言い換え**。`Postgres` → `PostgreSQL` のような書き換えや、人名の漢字化
  （同じ翻訳ディレクティブの副作用）は対象外。見ているのは文字の欠落だけ
- **chunk が残っていない古いデータ**の軸1
- `prompts.py:177` → `prompts.py` のような**行番号の脱落**は、意図的に除外している。
  ソース引用のたびに指摘が出て報告が埋もれるため

これは対症療法であることに注意。本来は Hindsight 側で識別子保護を言語設定と
独立させるべきで、それが入れば不要になる。

## 動かし方

compose の `scanner` サービスとして常駐する。`deploy.sh` がビルドして起動するので、
サーバー上で個別に操作する必要はない。

ローカルから 1 回だけ実行して確かめることもできる（`--once`）。
公開 URL 経由の場合はテナント API キーが要る。

```bash
KEY=$(security find-generic-password -a "$USER" -s hindsight-mcp-api-key -w)
HINDSIGHT_API_URL=https://hindsight.akmaru.dev \
HINDSIGHT_API_TENANT_API_KEY="$KEY" \
SCANNER_REPAIR=0 \
SCANNER_STATE_DIR=/tmp/scanner \
python3 scanner.py --once
```

## 設定

| 環境変数 | 既定値 | 説明 |
|---|---|---|
| `HINDSIGHT_API_URL` | `http://hindsight-api:8888` | compose ネットワーク内の API |
| `HINDSIGHT_API_TENANT_API_KEY` | （必須） | `Authorization: Bearer` に載せる |
| `SCANNER_BANKS` | 全バンク | カンマ区切りで対象を限定する |
| `SCANNER_INTERVAL_SECONDS` | `900` | 走査間隔 |
| `SCANNER_GRACE_SECONDS` | `300` | 更新直後のものを見ない猶予。consolidation は retain の後ろで非同期に走るため |
| `SCANNER_REPAIR` | `1` | `0` で修復せず検出だけ |
| `SCANNER_MAX_REPAIRS` | `2` | 同一 fact への修復試行の上限。超えたら隔離する |
| `SCANNER_REPAIR_COOLDOWN_SECONDS` | `3600` | 修復後、再 consolidation の結果を待つ時間 |
| `SCANNER_STATE_DIR` | `/state` | レポートとウォーターマークの置き場所 |

## 出力

`${HINDSIGHT_DATA_DIR}/scanner/`（既定 `/data/hindsight/scanner/`）に 2 つ置く。
EBS のデータボリューム上なので、スナップショットに含まれる。

- `report.json` — 現在判明している破損の一覧。修復済みのものは次の走査で消える
- `state.json` — バンクごとのウォーターマークと修復試行の回数

通知は出さない。修復が効く限り人が見る必要はなく、修復できないものだけが
`report.json` に残り続ける設計。確認するときは次のように読む。

```bash
aws ssm send-command --profile maru --region ap-northeast-1 \
  --instance-ids <instance-id> --document-name AWS-RunShellScript \
  --parameters 'commands=["cat /data/hindsight/scanner/report.json"]'
```

## 差分走査について

API に `updated_at` での絞り込みが無いので、毎回全件引いてクライアント側で
ウォーターマークと比較している。個人バンクの規模（数百件）では問題にならないが、
桁が変わったら API 側の対応を待つか Postgres を直接見る必要がある。
内部スキーマに依存すると Hindsight のバージョン上げで黙って壊れるため、
今は REST に寄せている。
