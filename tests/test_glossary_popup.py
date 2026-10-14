"""user/herdr/scripts/glossary-popup.py: 用語集の語を pane の出力から拾う（docs/adr/0029）。"""
import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "user" / "herdr" / "scripts" / "glossary-popup.py"

GLOSSARY = """# X

## 用語

**注文（Order）**:
顧客が商品の購入を申し込んだ記録。
_使わない_: 購入
_種別_: kind

**顧客（Customer）**:
注文を出した当事者。
"""


def _run(tmp_path, output):
    (tmp_path / "CONTEXT.md").write_text(GLOSSARY)
    stub = tmp_path / "herdr"
    stub.write_text(f"#!/usr/bin/env bash\ncat <<'EOF'\n{output}\nEOF\n")
    stub.chmod(0o755)
    env = {**os.environ, "HERDR_BIN_PATH": str(stub), "HERDR_ACTIVE_PANE_ID": "p1",
           "HERDR_ACTIVE_PANE_CWD": str(tmp_path)}
    return subprocess.run([sys.executable, "-I", str(SCRIPT)], env=env,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL)


def test_matches_headword_and_alias_with_definition_only(tmp_path):
    r = _run(tmp_path, "Order を確定した。顧客の話")
    assert r.returncode == 0
    assert "顧客が商品の購入を申し込んだ記録。" in r.stdout
    assert "注文を出した当事者。" in r.stdout
    assert "_種別_" not in r.stdout and "_使わない_" not in r.stdout


def test_exact_match_only(tmp_path):
    r = _run(tmp_path, "Orders and Reorder")
    assert "申し込んだ" not in r.stdout
    assert "出ていない" in r.stdout


def test_keybinding_points_at_an_executable_popup():
    commands = tomllib.loads((ROOT / "user" / "herdr" / "config.toml").read_text())["keys"]["command"]
    cmd = next(c for c in commands if "glossary-popup" in c["command"])
    assert cmd["type"] == "popup"
    assert SCRIPT.stat().st_mode & 0o111
