"""
Validate each skill under packages/ against the agentskills.io specification.
https://agentskills.io/specification

Skills live at packages/<pkg>/.apm/skills/<skill>/SKILL.md (standard APM layout).
"""

import re
from pathlib import Path

import pytest
import yaml

PACKAGES_DIR = Path(__file__).parent.parent / "packages"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def skill_dirs():
    if not PACKAGES_DIR.exists():
        return []
    return sorted(PACKAGES_DIR.glob("*/.apm/skills/*"))


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=lambda d: d.name)
class TestSkillStructure:
    def test_skill_md_exists(self, skill_dir):
        assert (skill_dir / "SKILL.md").exists(), f"SKILL.md not found in {skill_dir}/"

    def test_frontmatter_is_valid_yaml(self, skill_dir):
        content = (skill_dir / "SKILL.md").read_text()
        parts = content.split("---", 2)
        assert len(parts) >= 3, "SKILL.md must have YAML frontmatter delimited by ---"
        yaml.safe_load(parts[1])  # raises if invalid

    def test_name_field_exists(self, skill_dir):
        fm = _frontmatter(skill_dir)
        assert "name" in fm, "frontmatter must have a 'name' field"

    def test_name_matches_directory(self, skill_dir):
        fm = _frontmatter(skill_dir)
        assert fm.get("name") == skill_dir.name, (
            f"name '{fm.get('name')}' must match skill directory name '{skill_dir.name}'"
        )

    def test_name_format(self, skill_dir):
        name = _frontmatter(skill_dir).get("name", "")
        assert 1 <= len(name) <= 64, "name must be 1-64 characters"
        assert NAME_PATTERN.match(name), (
            f"name '{name}' must be lowercase alphanumeric with single hyphens"
        )

    def test_description_field_exists(self, skill_dir):
        fm = _frontmatter(skill_dir)
        assert "description" in fm, "frontmatter must have a 'description' field"

    def test_description_length(self, skill_dir):
        desc = _frontmatter(skill_dir).get("description", "")
        assert 1 <= len(str(desc)) <= 1024, "description must be 1-1024 characters"

    def test_body_not_empty(self, skill_dir):
        content = (skill_dir / "SKILL.md").read_text()
        parts = content.split("---", 2)
        assert len(parts) == 3 and parts[2].strip(), "SKILL.md body must not be empty"


def test_packages_dir_exists():
    assert PACKAGES_DIR.exists() and PACKAGES_DIR.is_dir(), "packages/ directory must exist"


def test_at_least_one_skill():
    assert len(skill_dirs()) >= 1, "packages/ must contain at least one skill"


# ADR などの置き場を参照する汎用のスキルと役割。置き場の決め方は project-layout だけに書き、
# ここでは project-layout を参照させる（docs/adr/0025）。
LAYOUT_SKILL = PACKAGES_DIR / "project-layout/.apm/skills/project-layout/SKILL.md"
LAYOUT_CONSUMERS = [
    PACKAGES_DIR / "madr-writer/.apm/skills/madr-writer/SKILL.md",
    PACKAGES_DIR / "grill-with-docs/.apm/skills/grill-with-docs/SKILL.md",
    PACKAGES_DIR / "refine-design/.apm/skills/refine-design/SKILL.md",
    PACKAGES_DIR.parent / "user/agents/designer.md",
    PACKAGES_DIR.parent / "user/agents/critic.md",
]


def test_project_layout_defines_the_adr_location_order():
    content = LAYOUT_SKILL.read_text()
    for word in ("AGENTS.md", "CLAUDE.md", "docs/internal/adr/", "docs/adr/"):
        assert word in content


@pytest.mark.parametrize("path", LAYOUT_CONSUMERS, ids=lambda p: p.parent.name if p.name == "SKILL.md" else p.stem)
def test_layout_consumers_refer_to_project_layout(path):
    content = path.read_text()
    assert "project-layout" in content, "置き場は project-layout スキルに従わせる"
    assert "docs/adr/" not in content, "置き場の決め方を自前で持たない"


def _frontmatter(skill_dir: Path) -> dict:
    content = (skill_dir / "SKILL.md").read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}
