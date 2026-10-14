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
import sys
from pathlib import Path

import pytest
import yaml

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


# --- grill-spec: 同梱 3 ファイルの配備（プロジェクト / ユーザースコープ）と、Claude Code からの認識 ---
# 仕様書 packages/grill-spec/docs/internal/specs/0001-grill-spec.md の AC8（apm install / apm install -g で
# 導入できる）と AC9（/grill-spec で起動できる）を、実物の apm と claude で確かめる。

GRILL_SPEC_SRC = ROOT / "packages" / "grill-spec" / ".apm" / "skills" / "grill-spec"
GRILL_SPEC_FILES = ["SKILL.md", "SPEC-FORMAT.md", "REFINEMENT.md"]
GLOSSARY_FORMAT_SRC = ROOT / "packages" / "glossary" / ".apm" / "skills" / "glossary" / "CONTEXT-FORMAT.md"


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


def test_grill_spec_from_local_marketplace_deploys_glossary_format_alongside(tmp_path):
    """用語集の書式は grill-spec に同梱せず、依存の glossary が隣に入る（ADR 0026）。ローカルの marketplace は -g で
    相対パスの依存を配置しないので（ADR 0025）、ここではプロジェクトスコープだけを確かめる。"""
    _, _, deployed, install = _install_grill_spec(tmp_path, "project")
    fmt = deployed.parent / "glossary" / "CONTEXT-FORMAT.md"
    assert fmt.is_file(), f"glossary not deployed next to grill-spec:\n{install.stdout}"
    assert fmt.read_bytes() == GLOSSARY_FORMAT_SRC.read_bytes()


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


# --- init-project: 相対パスの依存（../project-layout）が隣に入り、同じコミットから取られる（ADR 0025） ---

INIT_PROJECT_SRC = ROOT / "packages" / "init-project" / ".apm" / "skills" / "init-project"
LAYOUT_SRC = ROOT / "packages" / "project-layout" / ".apm" / "skills" / "project-layout" / "layout.json"
# CI が "<owner>/<repo>@<commit>" を渡したときだけ、GitHub から clone する本番と同じ経路で確かめる。
REMOTE = os.environ.get("DOTAGENTS_E2E_REMOTE")


def _install_init_project(tmp_path, source, ref, scope):
    home = tmp_path / "home"
    consumer = tmp_path / "consumer"
    home.mkdir()
    consumer.mkdir()
    add = _apm(["marketplace", "add", source, "--ref", ref], home)
    assert add.returncode == 0, f"marketplace add failed:\n{add.stderr or add.stdout}"
    args = ["install", "init-project@dotagents", "--target", "claude"]
    if scope == "user":
        args.insert(1, "-g")
    install = _apm(args, home, cwd=consumer)
    assert install.returncode == 0, f"install failed:\n{install.stderr or install.stdout}"
    base = home if scope == "user" else consumer
    lock = home / ".apm" / "apm.lock.yaml" if scope == "user" else consumer / "apm.lock.yaml"
    return base / ".claude" / "skills", lock, install


def _assert_init_project_runs_with_sibling_layout(skills, tmp_path, install):
    assert (skills / "project-layout" / "layout.json").read_bytes() == LAYOUT_SRC.read_bytes(), (
        f"project-layout not deployed next to init-project:\n{install.stdout}"
    )
    target = tmp_path / "repo"
    target.mkdir()
    r = subprocess.run(
        [sys.executable, "-I", str(skills / "init-project" / "scripts" / "init_project.py"),
         "--target", str(target), "--hosting", "github", "--name", "demo", "--holder", "Alice"],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert (target / "AGENTS.md").is_file() and (target / "docs/internal/adr").is_dir()


def test_init_project_from_local_marketplace_deploys_project_layout_alongside(tmp_path):
    """push 前でも回せる経路。ローカルの marketplace はパッケージを作業ツリーから入れるので、-g では相対パスの
    依存が配置されない（APM 0.31.0、ADR 0025）。ここではプロジェクトスコープだけを確かめる。"""
    skills, _, install = _install_init_project(tmp_path, str(ROOT), "HEAD", "project")
    _assert_init_project_runs_with_sibling_layout(skills, tmp_path, install)


@pytest.mark.skipif(not REMOTE, reason="DOTAGENTS_E2E_REMOTE (<owner>/<repo>@<commit>) is not set")
@pytest.mark.parametrize("scope", ["project", "user"])
def test_init_project_from_github_marketplace_pins_both_packages_to_one_commit(tmp_path, scope):
    repo, commit = REMOTE.split("@")
    skills, lock, install = _install_init_project(tmp_path, repo, commit, scope)
    _assert_init_project_runs_with_sibling_layout(skills, tmp_path, install)
    deps = {d["name"]: d for d in yaml.safe_load(lock.read_text())["dependencies"]}
    assert deps["init-project"]["resolved_commit"] == commit
    assert deps["project-layout"]["resolved_commit"] == commit, "project-layout が別のコミットから入った"


@pytest.mark.skipif(not REMOTE, reason="DOTAGENTS_E2E_REMOTE (<owner>/<repo>@<commit>) is not set")
@pytest.mark.parametrize("pkg", ["grill-spec", "grill-with-docs", "ontology"])
@pytest.mark.parametrize("scope", ["project", "user"])
def test_glossary_users_from_github_marketplace_get_glossary_from_same_commit(tmp_path, pkg, scope):
    """用語集を扱うパッケージは、glossary を同じコミットから隣に入れる（ADR 0026）。"""
    repo, commit = REMOTE.split("@")
    home = tmp_path / "home"
    consumer = tmp_path / "consumer"
    home.mkdir()
    consumer.mkdir()
    add = _apm(["marketplace", "add", repo, "--ref", commit], home)
    assert add.returncode == 0, f"marketplace add failed:\n{add.stderr or add.stdout}"
    args = ["install", f"{pkg}@dotagents", "--target", "claude"]
    if scope == "user":
        args.insert(1, "-g")
    install = _apm(args, home, cwd=consumer)
    assert install.returncode == 0, f"install failed:\n{install.stderr or install.stdout}"
    base = home if scope == "user" else consumer
    fmt = base / ".claude" / "skills" / "glossary" / "CONTEXT-FORMAT.md"
    assert fmt.read_bytes() == GLOSSARY_FORMAT_SRC.read_bytes(), f"glossary not deployed:\n{install.stdout}"
    lock = home / ".apm" / "apm.lock.yaml" if scope == "user" else consumer / "apm.lock.yaml"
    deps = {d["name"]: d for d in yaml.safe_load(lock.read_text())["dependencies"]}
    assert deps["glossary"]["resolved_commit"] == commit, "glossary が別のコミットから入った"
