---
status: accepted
date: 2026-10-14
decision-makers: akmaru
---

# 出力中の用語の定義は、マウスオーバーではなく herdr の popup で出す

## Context and Problem Statement

エージェントの出力に出た用語の意味を忘れたとき、用語集を開き直さずに、その場で定義を見たい（Issue #54）。
当初はマウスオーバーのポップアップを想定したが、ターミナルはホバーで定義を出す手段を標準では持たない。

## Considered Options

1. ターミナル内のホバー（OSC 8 やマウスイベント）
2. 出力を HTML で別に表示する
3. explainer pane に定義を常時並べる
4. herdr の popup をキーで開き、pane の直近の出力と用語集を照合して並べる

## Decision Outcome

選んだ案: 4。`prefix+alt+t` で popup を開き、`user/herdr/scripts/glossary-popup.py` が `herdr pane read` で
フォーカス中の pane の出力を取り、cwd から上へ見つけた `CONTEXT.md`（`CONTEXT-MAP.md` が指すものを含む）の語と照合する。

* 出すのは定義の 1〜2 行だけ。構造の行（種別・上位・関係）は後から足す
* 拾うのは見出し語と、見出しの括弧の中の別名の完全一致だけ。ASCII の語は語境界で比べる
* 読む場所がターミナルから移らず、herdr の既存の仕組み（popup、ADR 0010 の PATH 明示）だけで作れる

### Consequences

* Bad: 要望の「マウスオーバー」ではなくキー操作になる
* Bad: `herdr pane read` の出力形式と、popup への環境変数（`HERDR_ACTIVE_PANE_ID`）の渡り方は実機で確かめていない
* Bad: 語が多いときの絞り込みは未実装（一覧を出すだけ）

### Confirmation

`tests/test_glossary_popup.py` が、スタブの herdr で見出し語・別名の照合、完全一致、キーバインドを検証する。
