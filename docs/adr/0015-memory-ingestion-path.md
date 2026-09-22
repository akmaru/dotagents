---
status: accepted
date: 2026-09-22
decision-makers: akmaru
---

# 記憶の投入はメインセッションのモデルが行い、hook による自動化は設計として保留する

## Context and Problem Statement

Hindsight への記憶の投入は、`user/AGENTS.md` の Memory (Hindsight) の 1 行だけを根拠に、メインセッションの
モデルが会話中に自分で判断して `retain` を呼ぶ形になっている。自動化は一切入っておらず、誰も呼ばなければ
記憶は増えない。一方でその呼び出しはメインのコンテキストを消費する（1 回あたり 200〜400 トークン）。

2026-09-22 の検討で、この「誰がいつ何を投入するか」の案は 7 つまで広がり、判断軸も 6 つに整理された。
同じ議論を繰り返さないために、採否と軸を残す。決めるのは「投入経路を今変えるか、変えないか」である。

## Decision Drivers

* メインセッションのコンテキストを無駄に消費しない
* 秘密（API キー・トークン）を記憶に入れない。`invalidate_memory` は soft-retire で、本文は監査用に残るため
  事後の完全な除去ができない
* `recall` / `reflect` の精度を保つ。母数が増えるほど重要な fact が相対的に希釈される
* 却下された案・検討中の仮説を、肯定形の事実として保存しない
* Claude Code と OpenCode の両方で成立すること（[ADR 0001](0001-target-claude-code-and-opencode.md)）
* 実験的機能に基盤を依存させない
* 個人用途なので運用の手数を増やさない（[ADR 0012](0012-hindsight-identifier-scanner.md) と同じ制約）

## Considered Options

1. プロンプト方式 — `AGENTS.md` のルールに従い、メインのモデルが判断して投入する（現状）
2. Claude Mods（function hooks）で投入する
3. 通常 hook から transcript の生ログをそのまま投入する
4. 通常 hook から、text ブロックだけを抽出して投入する
5. 通常 hook から、別プロセスの headless（`claude -p`）を起動して選別させる
    - 5.1. `SessionEnd` / `PreCompact` で発火する（セッション単位の粒度）
    - 5.2. `Stop` でデバウンスして発火する（ターン単位の粒度）
6. hook は `additionalContext` で「retain しろ」と促すだけにする
7. サブエージェントに投入を委譲する

選択肢は「**誰が残す価値を判断するか**」（モデル / 機械）と「**何が発火を保証するか**」（モデルの気まぐれ /
hook）の 2 軸で分かれる。3 と 4 は判断者が居ない側、5 は両方を満たそうとする案。

## Decision Outcome

選択: **1. プロンプト方式を維持する**（採用）。5 は実装せず、設計として本 ADR に記録するにとどめる。

理由は 3 つ。

- 5 の利得が実測に見合わない。過去 48 transcript の実績で `sync_retain` 12 回 / `retain` 5 回が呼ばれており、
  「モデルが忘れる」問題は想定より軽い。得られるのはメイン消費ゼロと発火保証だが、そのために hook・水位管理・
  ロック・再帰ガード・headless の常時起動を抱えることになる
- 5 は Claude Code 専用で、[ADR 0001](0001-target-claude-code-and-opencode.md) の前提と衝突する。OpenCode 側は
  プロンプト方式が残るため、結局 2 経路を維持することになる
- 6 軸のうち現に壊れているのは投入経路ではなく**サーバー側の抽出モード（軸 F）**であり、そこは投入経路と
  独立に直せる。順序として投入経路を先に触る理由がない

適用するルール:

- 投入はメインセッションのモデルが行う。根拠は `user/AGENTS.md` の Memory (Hindsight)
- 生ログ（tool_result / thinking / attachment）は投入しない
- 記録したこと自体はユーザーに報告しない
- 自動化を再検討するときは、思いつきの比較ではなく下記の 6 軸で評価する

### Consequences

判断軸は 6 つ。軸 A と B は同じトレードオフの両端で、ここが設計の中心になる。

* Neutral（軸 A: 投入タイミング）— 早く投げれば同じセッション中に `recall` で引けるが、その時点の内容は
  まだ確定していない。遅く投げれば確定しているが、そのセッションからは引けない。両立しない。本 ADR は
  「会話中に、決定が固まった時点で投げる」として中間を取り、判断をモデルに委ねている
* Neutral（軸 B: 投入単位）— 効くのはタイミングそのものではなく、投入単位が議論の完結単位と一致しているか。
  生ログを遅く投げても `retain_chunk_size = 3000` で機械的に切られ、chunk ごとに独立して抽出されるため
  「A を試した → 失敗 → B にした」が境界に割れると「A を採用した」という誤った fact が生まれる
* Bad（軸 C: 発火の決定性）— モデルに任せる以上、投入されない保証がない。長いセッションや作業に集中した
  セッションでは取りこぼす。hook なら発火は保証できるが、保証できるのは発火であって記録内容の質ではない
* Good（軸 D: 投入主体の場所）— メインのモデルが投入するため、ツール呼び出しぶんのコンテキストを消費する。
  別プロセス化すればゼロにできるが、今はその複雑さを持たない側を選んでいる
* Good（軸 E: 投入前の選別）— 選別する主体がモデルとして存在するため、秘密のゲートが機能し、投入量も
  小さく保たれる。transcript 全体のうち会話実体は 1.9% しかなく、選別の有無がノイズ比とコストを決める
* Bad（軸 F: サーバー側の抽出モード）— `retain_extraction_mode` は `concise` のままで、LLM が本文を書き直す。
  これが [ADR 0012](0012-hindsight-identifier-scanner.md) の識別子破損の発生源であり、投入側をどれだけ
  丁寧にしても 2 段目で壊される。`verbatim`（本文を保持し entity・時制のみ抽出）への変更は本 ADR の
  範囲外だが、投入経路と独立に実施できる

### Confirmation

**この決定を自動で検証する仕組みは無い。** 投入がプロンプト方式で行われているかは、コードではなく
`user/AGENTS.md` の記述と各セッションの振る舞いに依存する。

関連して実在するチェックは 2 つだけで、どちらもこの決定そのものではなく前提を守るものである。

- `tests/test_user_config.py` — `user/AGENTS.md` の存在・非空・cross-agent clean を検査する。
  ただし Memory (Hindsight) のルール本文は検査していない
- `tests/test_hindsight.py:240` — compose に `HINDSIGHT_API_LLM_OUTPUT_LANGUAGE: Japanese` が固定されていることを
  検査する。軸 F の破損はこの設定に起因するため、外れたことに気づくための番人になっている

軸 F の実害は `hindsight/scanner/` が定期検出して報告する（[ADR 0012](0012-hindsight-identifier-scanner.md)）。
軸 C の取りこぼしを検出する手段は無く、「recall で出てくるべき記憶が出てこない」ことで事後に気づくしかない。

## Pros and Cons of the Options

### 1. プロンプト方式（採用）

* Good: 文脈を見て「残す価値があるか」「秘密が混じっていないか」を判断できる。判断主体が存在する唯一の系統
* Good: Claude Code と OpenCode の両方で同じ 1 つのルールが効く
* Good: 実装がゼロ。壊れる部品が無い
* Bad: 発火の保証が無い（軸 C）
* Bad: メインのコンテキストを消費する（軸 D）

### 2. Claude Mods（function hooks）

* Good: ツール呼び出しの傍受と UI 追加ができる
* Bad: この用途では通常 hook と同じイベントしか使わず、追加の利得が無い
* Bad: `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1` が必要な early access で、API がリリース間で予告なく変わる。
  `user/settings.json` で `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` を設定している方針とも矛盾する
* Bad: Claude Code 専用

### 3. 通常 hook + 生ログ投入

* Good: 発火が保証される。メインの消費がゼロ
* Bad: **判断主体が居なくなるため、秘密のゲートが消える**。transcript には `aws ssm ... --with-decryption` の
  出力や 64 桁 hex（`tenant_api_key` と同じ形）が実際に含まれており、正規表現では git の SHA と区別できない
* Bad: 会話実体は 1.9%。残り 98% のノイズが recall 精度と observation の質を下げる
* Bad: 投入量に比例して抽出 LLM が走るためコストが跳ねる。軸 F の破損も投入量に比例する
* Bad: `attachment` に `CLAUDE.md` / `AGENTS.md` が含まれるため、自分への指示が「事実」として記憶される

### 4. 通常 hook + text ブロックのみ抽出

* Good: 1.4MB → 27KB になり、3 のノイズ・コスト・破損の問題はほぼ解決する
* Bad: 秘密は地の文にも書かれるため、ゲートが無い問題は残る（軸 E）
* Bad: Claude Code 専用

### 5. 通常 hook + 別プロセスの headless（設計のみ記録）

* Good: メインの消費がゼロでありながら、判断主体（別インスタンスのモデル）が存在する。軸 C・D・E を同時に満たす
* Good: `--allowed-tools` を `mcp__hindsight__sync_retain` だけに絞れば、headless 側に不要な権限を渡さずに済む
* Bad: `SessionEnd` / `PreCompact` は全 hook 合計 1.5 秒の予算しか無いため同期実行できず、detach が必須
* Bad: hooks は `-p` モードでも動くため、再帰ガードが無いと headless が headless を生む
* Bad: 水位管理・ロック・再帰ガード・失敗時のログという常時動く部品が増える
* Bad: Claude Code 専用

#### 5.1. `SessionEnd` / `PreCompact` で発火

* Good: 発火回数が少なくコストが読める。議論が完結してから投入するため軸 B に有利
* Bad: そのセッション中には引けない（軸 A）

#### 5.2. `Stop` でデバウンス発火

* Good: 会話の切れ目ごとに記録されるため、数ターン後には同じセッションで引ける（軸 A）
* Bad: 途中で覆った案が事実として残る。2026-09-22 の会話では「Mods で実装する」「mcp_enabled_tools を
  絞る」が中間状態として存在し、どちらも後に撤回された
* Bad: 多重起動の抑制とデバウンス閾値という調整点が増える

### 6. hook は `additionalContext` で促すだけ

* Good: 発火は保証される。実装が軽い
* Bad: 判断も投入もメインで行うため、コンテキスト消費が減らない（軸 D が解決しない）

### 7. サブエージェントに委譲

* Bad: 本文をプロンプトで渡す時点でメインが同じ量を払う。transcript のパスだけ渡すなら 5 と等価で、
  それなら hook の方が素直

## More Information

* [ADR 0001](0001-target-claude-code-and-opencode.md) — Claude Code と OpenCode の両対応。案 2〜6 が単独では
  満たせない制約
* [ADR 0012](0012-hindsight-identifier-scanner.md) — 識別子破損とスキャナ。軸 F は 0012 の前提を変えうる。
  `retain_extraction_mode` を `verbatim` にすると本文の書き直しが止まるため、破損の主因が消える（entity 名の
  抽出には LLM が走るため完全な解決ではない）
* [ADR 0013](0013-context-budget-monitoring.md) — コンテキスト使用量の計測。軸 D を数値で追う手段
* 検討時点の実測値: `retain_extraction_mode = concise` / `retain_chunk_size = 3000` /
  `retain_chunk_batch_size = 100`
* フォローアップ: 軸 F（`verbatim` の導入可否）は本 ADR とは独立に判断できる。軸 C を自動で検証したい場合は、
  `user/AGENTS.md` の Memory (Hindsight) の本文を検査するテストを `tests/test_user_config.py` に足す案がある
