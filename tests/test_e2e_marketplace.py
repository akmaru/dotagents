"""
End-to-end test of the marketplace consumer UX using the real `apm` CLI.

Exercises the documented flow: `apm marketplace add <repo>` (reads the committed
.claude-plugin/marketplace.json) -> `apm install <pkg>@dotagents` -> skill deployed.
This validates that marketplace.json actually resolves and installs, which no other
test covers.

Skipped when `apm` is not on PATH, so `uv run pytest` still passes without apm. CI
installs apm via microsoft/apm-action, and locally apm is already on PATH.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
GRILL_SKILL = ROOT / "packages" / "grill-me" / ".apm" / "skills" / "grill-me" / "SKILL.md"

pytestmark = pytest.mark.skipif(shutil.which("apm") is None, reason="apm CLI not on PATH")


def _apm(args, home, cwd=None):
    # Isolate all apm state (marketplaces, install cache) under a throwaway HOME
    # so the real ~/.apm is never touched.
    env = {**os.environ, "HOME": str(home)}
    return subprocess.run(
        ["apm", *args], env=env, cwd=cwd, capture_output=True, text=True
    )


def test_marketplace_add_then_install_deploys_skill(tmp_path):
    home = tmp_path / "home"
    consumer = tmp_path / "consumer"
    home.mkdir()
    consumer.mkdir()

    # A local path is a git-backed source; apm reads marketplace.json at a ref
    # (default "main"). Use HEAD so this works on a detached-HEAD CI checkout and
    # reads the current commit's marketplace.json rather than whatever "main" holds.
    add = _apm(["marketplace", "add", str(ROOT), "--ref", "HEAD"], home)
    assert add.returncode == 0, f"marketplace add failed:\n{add.stderr or add.stdout}"

    install = _apm(
        ["install", "grill-me@dotagents", "--target", "claude"], home, cwd=consumer
    )
    assert install.returncode == 0, f"install failed:\n{install.stderr or install.stdout}"

    deployed = consumer / ".claude" / "skills" / "grill-me" / "SKILL.md"
    assert deployed.is_file(), f"skill not deployed:\n{install.stdout}"
    assert deployed.read_text() == GRILL_SKILL.read_text(), (
        "deployed SKILL.md differs from packages/grill-me source"
    )


# --- grill-spec: 同梱 4 ファイルの配備（プロジェクト / ユーザースコープ）と、Claude Code からの認識 ---
# 仕様書 packages/grill-spec/docs/internal/specs/0001-grill-spec.md の AC8（apm install / apm install -g で
# 導入できる）と AC9（/grill-spec で起動できる）を、実物の apm と claude で確かめる。

GRILL_SPEC_SRC = ROOT / "packages" / "grill-spec" / ".apm" / "skills" / "grill-spec"
GRILL_SPEC_FILES = ["SKILL.md", "SPEC-FORMAT.md", "CONTEXT-FORMAT.md", "REFINEMENT.md"]


def _install_grill_spec(tmp_path, scope):
    home = tmp_path / "home"
    consumer = tmp_path / "consumer"
    home.mkdir()
    consumer.mkdir()
    add = _apm(["marketplace", "add", str(ROOT), "--ref", "HEAD"], home)
    assert add.returncode == 0, f"marketplace add failed:\n{add.stderr or add.stdout}"
    args = ["install", "grill-spec@dotagents", "--target", "claude"]
    if scope == "user":
        args.insert(1, "-g")
    install = _apm(args, home, cwd=consumer)
    assert install.returncode == 0, f"install failed:\n{install.stderr or install.stdout}"
    deployed = (home if scope == "user" else consumer) / ".claude" / "skills" / "grill-spec"
    return home, consumer, deployed, install


@pytest.mark.parametrize("scope", ["project", "user"])
def test_grill_spec_deploys_all_bundled_files(tmp_path, scope):
    _, _, deployed, install = _install_grill_spec(tmp_path, scope)
    for name in GRILL_SPEC_FILES:
        f = deployed / name
        assert f.is_file(), f"{name} not deployed ({scope}):\n{install.stdout}"
        assert f.read_bytes() == (GRILL_SPEC_SRC / name).read_bytes(), f"{name} differs from source"
    # パッケージ内の仕様書（docs/internal/）はスキルの文脈に入れない
    assert sorted(p.name for p in deployed.iterdir()) == sorted(GRILL_SPEC_FILES)


@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not on PATH")
@pytest.mark.parametrize("scope", ["project", "user"])
def test_claude_code_lists_grill_spec_as_slash_command(tmp_path, scope):
    """Claude Code のヘッドレス実行は、最初の system/init 行に使えるスキルとスラッシュコマンドを出す。
    この行は API を呼ぶ前に出るので、認証の無い隔離 HOME でも確かめられる（その後の API 呼び出しは
    認証が無くて失敗するが、料金はかからない）。確かめられるのは「認識されて一覧に載る」までで、
    スキルを実行した振る舞いは見ていない。"""
    home, consumer, _, _ = _install_grill_spec(tmp_path, scope)
    # Claude Code はプロジェクトのルートを git リポジトリで判定するので、導入先を空のリポジトリにする
    subprocess.run(["git", "init", "-q"], cwd=consumer, check=True)
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")}
    env["HOME"] = str(home)
    r = subprocess.run(
        ["claude", "-p", "hello", "--output-format", "stream-json", "--verbose"],
        cwd=consumer, env=env, capture_output=True, text=True, timeout=120,
    )
    init = None
    for line in r.stdout.splitlines():
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "system" and o.get("subtype") == "init":
            init = o
            break
    assert init is not None, f"no system/init line ({scope}):\nstdout={r.stdout[:500]}\nstderr={r.stderr[:500]}"
    assert "grill-spec" in init.get("slash_commands", []), (
        f"/grill-spec not listed ({scope}): {init.get('slash_commands')}"
    )
