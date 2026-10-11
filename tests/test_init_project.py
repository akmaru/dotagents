"""
init-project の雛形スクリプト（packages/init-project/.apm/skills/init-project/scripts/init_project.py）を、
空のディレクトリと既存ファイルのあるディレクトリで実行して検証する。構成の定義は project-layout の
layout.json にあり、その中身を docs/adr/0024-new-project-standard-layout.md と突き合わせる。
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SKILL_DIR = ROOT / "packages/init-project/.apm/skills/init-project"
SCRIPT = SKILL_DIR / "scripts/init_project.py"
TEMPLATES = SKILL_DIR / "templates"
LAYOUT_SKILL_DIR = ROOT / "packages/project-layout/.apm/skills/project-layout"
LAYOUT = LAYOUT_SKILL_DIR / "layout.json"
ADR_0024 = ROOT / "docs/adr/0024-new-project-standard-layout.md"

BASELINE = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "docs/public/.gitkeep",
    "docs/internal/adr/0001-record-architecture-decisions.md",
    ".claude/.gitignore",
]

OPTIONAL_GITHUB = {
    "security": "SECURITY.md",
    "code-of-conduct": "CODE_OF_CONDUCT.md",
    "support": "SUPPORT.md",
    "changelog": "CHANGELOG.md",
    "issue-template": ".github/ISSUE_TEMPLATE/bug_report.md",
    "pr-template": ".github/pull_request_template.md",
    "codeowners": ".github/CODEOWNERS",
}

OPTIONAL_GITLAB = {
    **OPTIONAL_GITHUB,
    "issue-template": ".gitlab/issue_templates/Bug.md",
    "pr-template": ".gitlab/merge_request_templates/Default.md",
    "codeowners": "CODEOWNERS",
}


def run(target: Path, *args: str) -> dict:
    out = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--target", str(target), "--layout", str(LAYOUT),
         "--name", "demo", "--holder", "Alice", "--year", "2026", *args],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def files_under(target: Path) -> set[str]:
    return {str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()}


def test_empty_dir_gets_exactly_the_baseline(tmp_path):
    report = run(tmp_path, "--hosting", "github")
    assert files_under(tmp_path) == set(BASELINE)
    assert sorted(report["created"]) == sorted(BASELINE)
    assert report["existing"] == []


@pytest.mark.parametrize("hosting,mapping", [("github", OPTIONAL_GITHUB), ("gitlab", OPTIONAL_GITLAB)])
def test_optional_files_go_to_the_hosting_specific_place(tmp_path, hosting, mapping):
    run(tmp_path, "--hosting", hosting, "--with", ",".join(mapping))
    assert files_under(tmp_path) == set(BASELINE) | set(mapping.values())


def test_existing_files_are_never_overwritten(tmp_path):
    (tmp_path / "README.md").write_text("mine\n")
    report = run(tmp_path, "--hosting", "github")
    assert (tmp_path / "README.md").read_text() == "mine\n"
    assert "README.md" in report["existing"]
    assert "README.md" not in report["created"]


def test_existing_adr_dir_is_used_and_0001_is_not_added(tmp_path):
    adr = tmp_path / "docs/adr"
    adr.mkdir(parents=True)
    (adr / "0001-something.md").write_text("x\n")
    report = run(tmp_path, "--hosting", "github", "--adr-dir", "docs/adr")
    assert not (adr / "0001-record-architecture-decisions.md").exists()
    assert not (tmp_path / "docs/internal/adr").exists()
    assert "docs/adr/0001-record-architecture-decisions.md" not in report["created"]
    assert "docs/adr" in (tmp_path / "AGENTS.md").read_text()


def test_placeholders_are_filled(tmp_path):
    run(tmp_path, "--hosting", "github")
    license_text = (tmp_path / "LICENSE").read_text()
    assert "MIT License" in license_text and "2026 Alice" in license_text
    assert (tmp_path / "README.md").read_text().startswith("# demo")
    assert (tmp_path / "CLAUDE.md").read_text().strip() == "@AGENTS.md"
    assert "{{" not in "".join((tmp_path / f).read_text() for f in BASELINE)


def test_agents_md_declares_the_placement_rules(tmp_path):
    run(tmp_path, "--hosting", "github")
    agents = (tmp_path / "AGENTS.md").read_text()
    for path in ("docs/internal/adr/", "docs/internal/specs/", "CONTEXT.md", "docs/public/"):
        assert path in agents


def test_existing_instruction_files_without_rules_are_warned(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# old\n")
    (tmp_path / "CLAUDE.md").write_text("# old\n")
    report = run(tmp_path, "--hosting", "github")
    warned = " ".join(report["warnings"])
    assert "AGENTS.md" in warned and "CLAUDE.md" in warned


def test_lazily_created_files_are_not_created(tmp_path):
    run(tmp_path, "--hosting", "github")
    assert not (tmp_path / "CONTEXT.md").exists()
    assert not (tmp_path / "docs/internal/specs").exists()


def layout() -> dict:
    return json.loads(LAYOUT.read_text())


def test_layout_matches_the_expected_files():
    data = layout()
    adr_dir = data["adr"]["default"]
    assert sorted(e["path"].format(adr_dir=adr_dir) for e in data["baseline"]) == sorted(BASELINE)
    assert {k: v["path"]["github"] for k, v in data["optional"].items()} == OPTIONAL_GITHUB
    assert {k: v["path"]["gitlab"] for k, v in data["optional"].items()} == OPTIONAL_GITLAB


def test_every_layout_entry_has_a_template():
    data = layout()
    ids = [e["id"] for e in data["baseline"]] + list(data["optional"])
    missing = [i for i in ids if not (TEMPLATES / i).is_file()]
    assert missing == [], f"テンプレートが無い: {missing}"
    unused = sorted({p.name for p in TEMPLATES.iterdir()} - set(ids))
    assert unused == [], f"layout.json に無いテンプレート: {unused}"


def test_layout_matches_adr_0024():
    adr = ADR_0024.read_text()
    data = layout()
    paths = [e["path"] for e in data["baseline"] + data["lazy"]]
    paths += [p for v in data["optional"].values() for p in v["path"].values()]
    for path in paths:
        name = Path(path.rstrip("/")).name
        if name in {".gitkeep", "bug_report.md", "Bug.md", "Default.md", "0001-record-architecture-decisions.md"}:
            # ADR はディレクトリ単位で書いているので、ディレクトリ名で突き合わせる
            name = Path(path).parent.name.replace("{adr_dir}", "adr")
        assert name in adr, f"{path} が ADR 0024 に書かれていない"


def test_script_finds_layout_next_to_its_own_skill_dir(tmp_path):
    """インストール後は skills/init-project と skills/project-layout が隣り合う（APM の依存解決の結果）。"""
    skills = tmp_path / "skills"
    shutil.copytree(SKILL_DIR, skills / "init-project")
    shutil.copytree(LAYOUT_SKILL_DIR, skills / "project-layout")
    target = tmp_path / "repo"
    target.mkdir()
    subprocess.run(
        [sys.executable, "-I", str(skills / "init-project/scripts/init_project.py"), "--target", str(target),
         "--hosting", "github", "--name", "demo", "--holder", "Alice"],
        capture_output=True, text=True, check=True,
    )
    assert files_under(target) == set(BASELINE)


def test_init_project_depends_on_project_layout_by_relative_path():
    """同じ ref の project-layout を取るため、依存は相対パスで張る（ADR 0025）。"""
    for pkg in ("init-project", "madr-writer", "grill-with-docs", "refine-design"):
        manifest = yaml.safe_load((ROOT / "packages" / pkg / "apm.yml").read_text())
        assert "../project-layout" in manifest["dependencies"]["apm"], pkg
