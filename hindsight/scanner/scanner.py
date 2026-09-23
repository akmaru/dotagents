#!/usr/bin/env python3
"""
Hindsight に保存されたテキストから、識別子の破損を定期検出する。

HINDSIGHT_API_LLM_OUTPUT_LANGUAGE を設定していた間、retain / consolidation の
プロンプトから識別子保護ルール (_DEFAULT_LANGUAGE_RULE の
"Proper nouns, identifiers, and units stay verbatim.") が外れ、
「エンティティ名を含め全て翻訳しろ」という指示だけが残っていた。その結果 LLM が
識別子を日本語化し、区切り文字ごと潰した。2026-09-23 にこの設定をやめて保護を戻した
(../../docs/adr/0019-output-language-via-retain-mission.md) が、本スキャナは
再発を測る装置として残す。詳細は ../README.md の既知の罠。

検出は「正解 → 生成物」の 2 段を突き合わせる:

    投入テキスト ──retain──▶ 生 fact ──consolidation──▶ observation
       (chunk)                (text)                      (text)
           └──── 軸1 ────────────┘        └──── 軸2 ────────┘

軸2 の破損は元 fact を同じ本文で PATCH すれば consolidation が observation を
作り直すので自動修復する (本文を書き換えないため、データを壊しようがない)。
軸1 は fact 本文そのものを直す＝内容の書き換えになるので検出だけにとどめ、
人が判断する。

LLM は一切使わない。純粋な文字列照合のみ。
"""

import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scanner")

API_URL = os.environ.get("HINDSIGHT_API_URL", "http://hindsight-api:8888").rstrip("/")
API_KEY = os.environ.get("HINDSIGHT_API_TENANT_API_KEY", "")
BANKS = [b for b in os.environ.get("SCANNER_BANKS", "").split(",") if b]
INTERVAL = int(os.environ.get("SCANNER_INTERVAL_SECONDS", "900"))
# consolidation は retain の後ろで非同期に走る。更新直後のものを見ると
# 「まだ observation が出来ていない」状態を壊れていると誤判定するので待つ。
GRACE = int(os.environ.get("SCANNER_GRACE_SECONDS", "300"))
STATE_DIR = Path(os.environ.get("SCANNER_STATE_DIR", "/state"))
REPAIR = os.environ.get("SCANNER_REPAIR", "1") not in ("0", "false", "no")
# 修復 → 再 consolidation → また破損、の無限ループを止める上限。
MAX_REPAIRS = int(os.environ.get("SCANNER_MAX_REPAIRS", "2"))
REPAIR_COOLDOWN = int(os.environ.get("SCANNER_REPAIR_COOLDOWN_SECONDS", "3600"))
PAGE = 100

# 区切り文字で繋がった英数字の塊だけを識別子とみなす。区切りの無い語
# (Hindsight, maru) は「潰れる」という壊れ方をしないので最初から対象外。
SEPARATORS = "._/:@-"
IDENTIFIER = re.compile(r"[A-Za-z0-9]+(?:[" + re.escape(SEPARATORS) + r"][A-Za-z0-9]+)+")
_STRIP_SEP = re.compile("[" + re.escape(SEPARATORS) + "]")
_WHITESPACE = re.compile(r"\s+")
_LINE_NUMBER_SUFFIX = re.compile(r":\d+")

# 偶然の一致で誤検出しないための下限。短い識別子ほど無関係な箇所に紛れ込む。
MIN_STRIPPED = 6
MIN_SPACED = 8
MIN_PREFIX = 8


class ApiError(RuntimeError):
    pass


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None):
    url = f"{API_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if API_KEY:
        req.add_header("Authorization", f"Bearer {API_KEY}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read() or "null")
    except urllib.error.HTTPError as e:
        raise ApiError(f"{method} {path} -> {e.code} {e.read()[:200]!r}") from e
    except urllib.error.URLError as e:
        raise ApiError(f"{method} {path} -> {e.reason}") from e


def list_banks() -> list[str]:
    data = _request("GET", "/v1/default/banks") or {}
    return [b["bank_id"] for b in data.get("banks", data.get("items", []))]


def list_memories(bank_id: str) -> list[dict]:
    out, offset = [], 0
    while True:
        # updated_at での絞り込みは API に無いので全件引いてクライアント側で
        # ウォーターマーク比較する。個人バンクの規模では問題にならない。
        data = _request(
            "GET",
            f"/v1/default/banks/{bank_id}/memories/list",
            {"limit": PAGE, "offset": offset},
        )
        items = data.get("items", [])
        out.extend(items)
        offset += len(items)
        if len(items) < PAGE or offset >= data.get("total", offset):
            return out


def get_chunk_text(chunk_id: str) -> str | None:
    try:
        data = _request("GET", f"/v1/default/chunks/{urllib.parse.quote(chunk_id)}")
    except ApiError as e:
        log.warning("chunk %s を取得できませんでした: %s", chunk_id, e)
        return None
    return (data or {}).get("chunk_text")


def touch_memory(bank_id: str, memory_id: str, text: str) -> None:
    """同じ本文で PATCH して再 consolidation を促す (本文は変えない)。"""
    _request(
        "PATCH",
        f"/v1/default/banks/{bank_id}/memories/{urllib.parse.quote(memory_id)}",
        body={"text": text, "resolve_entities": False},
    )


def find_damage(source: str, target: str) -> list[dict]:
    """source にあった識別子が target で崩れていないか調べる。

    target に単に現れないだけ (要約で落ちた) は破損としない。崩れた形で
    現れているものだけを拾う。
    """
    target_nospace = _WHITESPACE.sub("", target)
    findings = []
    for token in sorted({m.group(0) for m in IDENTIFIER.finditer(source)}):
        if token in target:
            continue
        # スペース化の判定を先に置く。separator-loss は空白を除去した本文と
        # 比較するので、後ろに置くと「区切りがスペースに化けた」ケースまで
        # 飲み込んでしまい、レポートの表示が実態とずれる。
        spaced = _STRIP_SEP.sub(" ", token)
        if len(token) >= MIN_SPACED and spaced in target:
            findings.append({"rule": "separator-to-space", "expected": token, "found": spaced})
            continue
        stripped = _STRIP_SEP.sub("", token)
        if len(stripped) >= MIN_STRIPPED and stripped in target_nospace:
            findings.append({"rule": "separator-loss", "expected": token, "found": stripped})
            continue
        truncated = _find_truncation(token, target)
        if truncated:
            findings.append({"rule": "prefix-truncation", "expected": token, "found": truncated})
    return findings


def _find_truncation(token: str, target: str) -> str | None:
    """識別子の途中までが現れ、直後が非 ASCII になっている箇所を探す。

    `HINDSIGHT_API_CONSOLIDATION_LLM_MODEL` の末尾 `_MODEL` が「モデル」と
    和訳される壊れ方。完全形が target にあるときは呼ばれないので、
    `..._MODELで` のように助詞が続くだけのケースは誤検出しない。
    """
    cuts = [m.start() for m in re.finditer("[" + re.escape(SEPARATORS) + "]", token)]
    for cut in sorted(cuts, reverse=True):
        prefix = token[:cut]
        if len(prefix) < MIN_PREFIX:
            continue
        # `prompts.py:177` から行番号が落ちて `prompts.py` になるのは要約であって
        # 識別子の破損ではない。これを拾うとソース引用のたびに指摘が出る。
        if _LINE_NUMBER_SUFFIX.fullmatch(token[cut:]):
            continue
        for m in re.finditer(re.escape(prefix), target):
            rest = target[m.end() :]
            if rest and not rest[0].isascii():
                return prefix + rest[0]
    return None


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def scan_bank(bank_id: str, state: dict) -> tuple[list[dict], str | None]:
    memories = list_memories(bank_id)
    by_id = {m["id"]: m for m in memories}
    watermark = _iso(state.get("watermarks", {}).get(bank_id))
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=GRACE)

    targets = []
    for m in memories:
        if m.get("state") != "valid":
            continue
        updated = _iso(m.get("updated_at")) or _iso(m.get("date"))
        if updated is None or updated > cutoff:
            continue
        if watermark and updated <= watermark:
            continue
        targets.append((m, updated))

    findings = []
    chunk_cache: dict[str, str | None] = {}
    for m, _ in targets:
        if m["fact_type"] == "observation":
            # 軸2: 元 fact (正解) → observation
            sources = [by_id[s] for s in (m.get("source_memory_ids") or []) if s in by_id]
            if not sources:
                continue
            source_text = " ".join(s["text"] for s in sources)
            for d in find_damage(source_text, m["text"]):
                findings.append(
                    {
                        **d,
                        "bank_id": bank_id,
                        "axis": "fact->observation",
                        "memory_id": m["id"],
                        "source_ids": [s["id"] for s in sources],
                        "excerpt": m["text"][:160],
                    }
                )
        else:
            # 軸1: chunk (投入した原文) → 生 fact
            chunk_id = m.get("chunk_id")
            if not chunk_id:
                continue
            if chunk_id not in chunk_cache:
                chunk_cache[chunk_id] = get_chunk_text(chunk_id)
            chunk_text = chunk_cache[chunk_id]
            if not chunk_text:
                continue
            for d in find_damage(chunk_text, m["text"]):
                findings.append(
                    {
                        **d,
                        "bank_id": bank_id,
                        "axis": "chunk->fact",
                        "memory_id": m["id"],
                        "source_ids": [chunk_id],
                        "excerpt": m["text"][:160],
                    }
                )

    new_watermark = max((u for _, u in targets), default=None)
    return findings, new_watermark.isoformat() if new_watermark else None


def repair(findings: list[dict], memories_by_id: dict[str, dict], state: dict) -> None:
    """軸2 の破損だけ、元 fact を触って observation を作り直させる。"""
    repairs = state.setdefault("repairs", {})
    now = time.time()
    for f in findings:
        if f["axis"] != "fact->observation":
            f["repair"] = {"status": "manual", "note": "fact 本文の書き換えになるため自動修復しない"}
            continue
        for source_id in f["source_ids"]:
            entry = repairs.setdefault(source_id, {"attempts": 0, "last_at": 0})
            if entry["attempts"] >= MAX_REPAIRS:
                f["repair"] = {"status": "quarantined", "attempts": entry["attempts"]}
                continue
            if now - entry["last_at"] < REPAIR_COOLDOWN:
                f["repair"] = {"status": "cooldown", "attempts": entry["attempts"]}
                continue
            source = memories_by_id.get(source_id)
            if source is None:
                f["repair"] = {"status": "source-missing"}
                continue
            if not REPAIR:
                f["repair"] = {"status": "disabled"}
                continue
            try:
                touch_memory(f["bank_id"], source_id, source["text"])
                entry["attempts"] += 1
                entry["last_at"] = now
                f["repair"] = {"status": "touched", "attempts": entry["attempts"]}
                log.info("修復を試行: fact %s (observation %s)", source_id, f["memory_id"])
            except ApiError as e:
                f["repair"] = {"status": "failed", "error": str(e)}
                log.error("修復に失敗: %s", e)


def load_state() -> dict:
    path = STATE_DIR / "state.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            log.warning("state.json が壊れていたので作り直します")
    return {}


def save_json(name: str, payload: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / f".{name}.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(STATE_DIR / name)


def run_once() -> int:
    state = load_state()
    banks = BANKS or list_banks()
    # 走査しなかったアイテムの指摘は前回の結果を引き継ぐ (差分走査のため)。
    carried = {f["memory_id"]: f for f in state.get("findings", [])}
    all_findings = []
    scanned = 0
    for bank_id in banks:
        memories = {m["id"]: m for m in list_memories(bank_id)}
        scanned += len(memories)
        findings, watermark = scan_bank(bank_id, state)
        for m_id in {f["memory_id"] for f in findings} | set(carried):
            carried.pop(m_id, None)
        repair(findings, memories, state)
        all_findings.extend(findings)
        if watermark:
            state.setdefault("watermarks", {})[bank_id] = watermark
    all_findings.extend(carried.values())

    state["findings"] = all_findings
    save_json("state.json", state)
    save_json(
        "report.json",
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "banks": banks,
            "memories_scanned": scanned,
            "finding_count": len(all_findings),
            "findings": all_findings,
        },
    )
    if all_findings:
        log.warning("識別子の破損 %d 件を検出しました", len(all_findings))
    else:
        log.info("破損は検出されませんでした (%d 件を走査)", scanned)
    return len(all_findings)


def main() -> int:
    once = "--once" in sys.argv
    while True:
        try:
            run_once()
        except ApiError as e:
            log.error("API エラー: %s", e)
        except Exception:
            log.exception("スキャンが失敗しました")
        if once:
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
