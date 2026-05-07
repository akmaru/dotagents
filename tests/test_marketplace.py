"""
Validate .claude-plugin/marketplace.json and its consistency with apm.yml.
"""

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
MARKETPLACE_JSON = ROOT / ".claude-plugin" / "marketplace.json"
APM_YML = ROOT / "apm.yml"
SKILLS_DIR = ROOT / "skills"


@pytest.fixture(scope="module")
def marketplace():
    return json.loads(MARKETPLACE_JSON.read_text())


@pytest.fixture(scope="module")
def apm():
    return yaml.safe_load(APM_YML.read_text())


def test_marketplace_json_exists():
    assert MARKETPLACE_JSON.exists()


def test_marketplace_json_is_valid_json():
    json.loads(MARKETPLACE_JSON.read_text())


def test_required_fields(marketplace):
    for field in ("name", "description", "owner", "plugins"):
        assert field in marketplace, f"marketplace.json must have '{field}' field"


def test_owner_has_name(marketplace):
    assert "name" in marketplace.get("owner", {}), "owner must have 'name'"


def test_plugins_is_list(marketplace):
    assert isinstance(marketplace.get("plugins"), list)


def test_at_least_one_plugin(marketplace):
    assert len(marketplace["plugins"]) >= 1


class TestPlugin:
    def test_each_plugin_has_required_fields(self, marketplace):
        for p in marketplace["plugins"]:
            for field in ("name", "description", "source"):
                assert field in p, f"plugin '{p.get('name')}' must have '{field}'"

    def test_each_plugin_source_has_required_fields(self, marketplace):
        for p in marketplace["plugins"]:
            src = p.get("source", {})
            for field in ("source", "url", "path", "ref"):
                assert field in src, (
                    f"plugin '{p.get('name')}' source must have '{field}'"
                )

    def test_each_plugin_source_path_exists(self, marketplace):
        for p in marketplace["plugins"]:
            path = ROOT / p["source"]["path"]
            assert path.exists(), (
                f"plugin '{p['name']}' source.path '{p['source']['path']}' does not exist"
            )

    def test_each_plugin_source_url_matches_repo(self, marketplace):
        for p in marketplace["plugins"]:
            url = p["source"].get("url", "")
            assert "akmaru/dotagents" in url, (
                f"plugin '{p['name']}' source.url should reference akmaru/dotagents"
            )


class TestConsistencyWithApmYml:
    def test_plugin_names_match_apm_yml(self, marketplace, apm):
        json_names = {p["name"] for p in marketplace["plugins"]}
        apm_names = {p["name"] for p in apm.get("marketplace", {}).get("plugins", [])}
        assert json_names == apm_names, (
            f"marketplace.json plugins {json_names} must match apm.yml plugins {apm_names}"
        )

    def test_each_plugin_has_corresponding_skill_dir(self, marketplace):
        for p in marketplace["plugins"]:
            skill_dir = SKILLS_DIR / p["name"]
            assert skill_dir.exists(), (
                f"plugin '{p['name']}' has no corresponding skills/{p['name']}/ directory"
            )
