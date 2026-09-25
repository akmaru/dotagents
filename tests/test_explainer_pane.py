"""
Validate user/herdr/scripts/explainer-pane.sh against a stub herdr (docs/adr/0016).

The real herdr is never called: HERDR_BIN_PATH points at a bash stub that answers
each subcommand with canned JSON and records every invocation. The stub validates
agent names the way herdr does (invalid_agent_name), because the first real launch
failed exactly there: the tab id "w5:t6" was used verbatim in the agent name and
herdr rejects ':'.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "user" / "herdr" / "scripts" / "explainer-pane.sh"

pytestmark = pytest.mark.skipif(shutil.which("jq") is None, reason="explainer-pane.sh requires jq")

# herdr の agent name の規則（実機のエラーメッセージから）
AGENT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")

MAIN = "w5:pF"
TAB = "w5:t6"
NEW = "w5:pS"


def _pane(pane_id, label=None, agent="claude", sid="4a0c4e9e-52ec-4b1c-b693-ec62add97df4"):
    return {
        "pane_id": pane_id, "tab_id": TAB, "label": label, "agent": agent,
        "agent_status": "working" if agent else "unknown",
        "agent_session": {"kind": "id", "value": sid} if sid else {"kind": "none"},
        "cwd": "/tmp/work", "foreground_cwd": "/tmp/work",
    }


def _stub_herdr(tmp_path: Path, panes: list[dict]) -> tuple[Path, Path]:
    """subcommand ごとに固定 JSON を返し、呼び出しを log に記録する偽 herdr。"""
    log = tmp_path / "herdr-calls.log"
    data = tmp_path / "panes.json"
    data.write_text(json.dumps({"result": {"panes": panes}}))
    stub = tmp_path / "herdr"
    stub.write_text(f'''#!/usr/bin/env bash
echo "$@" >> "{log}"
case "$1 $2" in
  "pane get")
    jq -c --arg p "$3" '{{result: {{pane: (.result.panes[] | select(.pane_id == $p))}}}}' "{data}" ;;
  "pane list")   cat "{data}" ;;
  "pane layout") echo '{{"result":{{"layout":{{"panes":[{{"pane_id":"{MAIN}","rect":{{"width":460,"height":148}}}}]}}}}}}' ;;
  "pane split")  echo '{{"result":{{"pane":{{"pane_id":"{NEW}"}}}}}}' ;;
  "pane rename"|"pane close"|"agent focus"|"notification show") echo '{{"result":{{}}}}' ;;
  "agent start")
    name="$3"
    if [[ ! "$name" =~ ^[a-z][a-z0-9_-]{{0,31}}$ ]]; then
      echo '{{"error":{{"code":"invalid_agent_name","message":"agent name must start with a lowercase letter and contain only lowercase letters, digits, - or _ (1-32 characters)"}}}}'
      exit 1
    fi
    echo '{{"type":"agent_started","result":{{}}}}' ;;
  *) echo '{{"error":{{"code":"unknown","message":"'"$1 $2"'"}}}}'; exit 1 ;;
esac
''')
    stub.chmod(0o755)
    return stub, log


def _run(tmp_path: Path, panes: list[dict], focus=MAIN):
    stub, log = _stub_herdr(tmp_path, panes)
    env = {**os.environ, "HERDR_BIN_PATH": str(stub), "HERDR_ACTIVE_PANE_ID": focus, "HERDR_PANE_ID": focus}
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    calls = log.read_text().splitlines() if log.exists() else []
    return r, calls


def test_agent_name_is_valid_for_herdr_even_though_tab_id_contains_a_colon(tmp_path):
    """実機で最初に起動したとき、名前 explainer-w5:t6 が invalid_agent_name で弾かれ、
    作った pane が閉じられて終わった。タブ ID は名前に使える文字に落とす。"""
    r, calls = _run(tmp_path, [_pane(MAIN)])
    starts = [c for c in calls if c.startswith("agent start ")]
    assert starts, f"agent start が呼ばれていない: {calls}\n{r.stderr}"
    name = starts[0].split()[2]
    assert AGENT_NAME.match(name), f"herdr が受け付けない名前: {name!r}"
    assert TAB.replace(":", "-") in name, "タブ由来で一意にする（ADR 0016 のレビュー指摘）"
    assert r.returncode == 0, r.stderr
    assert not any(c.startswith("pane close") for c in calls), "起動に失敗して pane を閉じている"


def test_new_pane_is_split_labelled_and_focused(tmp_path):
    r, calls = _run(tmp_path, [_pane(MAIN)])
    assert r.returncode == 0, r.stderr
    assert f"pane rename {MAIN} main" in calls, "フォーカス pane に main ラベルを付ける"
    assert any(c.startswith(f"pane split --pane {MAIN} --direction right") and f"HERDR_MAIN_PANE_ID={MAIN}" in c for c in calls)
    assert f"pane rename {NEW} explainer" in calls
    assert f"agent focus {NEW}" in calls, "フォーカスは名前でなく pane id で"


def test_existing_explainer_pane_is_reused_without_split(tmp_path):
    r, calls = _run(tmp_path, [_pane(MAIN), _pane(NEW, label="explainer")])
    assert r.returncode == 0, r.stderr
    assert not any(c.startswith("pane split") for c in calls)
    assert not any(c.startswith("agent start") for c in calls), "Claude が居るなら再起動しない"
    assert f"agent focus {NEW}" in calls


def test_main_label_moves_to_the_focused_pane(tmp_path):
    other = "w5:pB"
    r, calls = _run(tmp_path, [_pane(MAIN), _pane(other, label="main")])
    assert r.returncode == 0, r.stderr
    assert f"pane rename {MAIN} main" in calls
    assert f"pane rename {other} --clear" in calls, "同タブの他 pane から main を外す"


def test_pressing_in_the_explainer_pane_does_nothing(tmp_path):
    r, calls = _run(tmp_path, [_pane(MAIN, label="explainer")])
    assert r.returncode == 0
    assert not any(c.startswith(("pane split", "agent start", "pane rename")) for c in calls)
