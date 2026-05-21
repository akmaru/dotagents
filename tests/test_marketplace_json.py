"""
Validate marketplace.json structure and plugin references.
"""

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
MARKETPLACE_JSON = ROOT / "marketplace.json"


@pytest.fixture(scope="module")
def marketplace():
    return json.loads(MARKETPLACE_JSON.read_text())


def test_marketplace_json_exists():
    assert MARKETPLACE_JSON.exists()


def test_marketplace_json_is_valid_json():
    json.loads(MARKETPLACE_JSON.read_text())


def test_required_fields(marketplace):
    for field in ("name", "version", "description", "author", "license", "owner", "plugins"):
        assert field in marketplace, f"marketplace.json must have '{field}' field"


def test_owner_has_name(marketplace):
    assert "name" in marketplace.get("owner", {}), "owner must have 'name'"


def test_at_least_one_plugin(marketplace):
    assert len(marketplace["plugins"]) >= 1


class TestPlugin:
    def test_each_plugin_has_required_fields(self, marketplace):
        for p in marketplace["plugins"]:
            for field in ("name", "source", "description"):
                assert field in p, f"plugin '{p.get('name')}' must have '{field}'"

    def test_each_plugin_source_exists(self, marketplace):
        for p in marketplace["plugins"]:
            source = p.get("source", "")
            if source.startswith("./"):
                path = ROOT / source[2:]
                assert path.exists(), (
                    f"plugin '{p['name']}' source '{source}' does not exist"
                )
