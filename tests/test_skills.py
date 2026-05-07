"""
Validate each skill in skills/ against the agentskills.io specification.
https://agentskills.io/specification
"""

import re
from pathlib import Path

import pytest
import yaml

SKILLS_DIR = Path(__file__).parent.parent / "skills"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def skill_dirs():
    return sorted(SKILLS_DIR.iterdir()) if SKILLS_DIR.exists() else []


@pytest.mark.parametrize("skill_dir", skill_dirs(), ids=lambda d: d.name)
class TestSkillStructure:
    def test_skill_md_exists(self, skill_dir):
        assert (skill_dir / "SKILL.md").exists(), f"SKILL.md not found in {skill_dir.name}/"

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
            f"name '{fm.get('name')}' must match directory name '{skill_dir.name}'"
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


def test_skills_dir_exists():
    assert SKILLS_DIR.exists() and SKILLS_DIR.is_dir(), "skills/ directory must exist"


def test_at_least_one_skill():
    assert len(skill_dirs()) >= 1, "skills/ must contain at least one skill"


def _frontmatter(skill_dir: Path) -> dict:
    content = (skill_dir / "SKILL.md").read_text()
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}
