"""
Validate apm.yml structure and marketplace plugin references.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
APM_YML = ROOT / "apm.yml"


@pytest.fixture(scope="module")
def apm():
    return yaml.safe_load(APM_YML.read_text())


def test_apm_yml_exists():
    assert APM_YML.exists()


def test_required_fields(apm):
    for field in ("name", "version", "description"):
        assert field in apm, f"apm.yml must have '{field}' field"


def test_marketplace_block_exists(apm):
    assert "marketplace" in apm, "apm.yml must have a 'marketplace' block"


def test_marketplace_owner(apm):
    owner = apm.get("marketplace", {}).get("owner", {})
    assert "name" in owner, "marketplace.owner must have a 'name' field"


def test_marketplace_plugins_exist(apm):
    plugins = apm.get("marketplace", {}).get("plugins", [])
    assert len(plugins) >= 1, "marketplace must declare at least one plugin"


class TestMarketplacePlugin:
    @pytest.fixture(autouse=True)
    def plugins(self, apm):
        self._plugins = apm.get("marketplace", {}).get("plugins", [])

    def _each(self):
        return self._plugins

    def test_each_plugin_has_name(self, apm):
        for p in apm.get("marketplace", {}).get("plugins", []):
            assert "name" in p, f"plugin entry must have 'name': {p}"

    def test_each_plugin_has_source(self, apm):
        for p in apm.get("marketplace", {}).get("plugins", []):
            assert "source" in p, f"plugin '{p.get('name')}' must have 'source'"

    def test_each_plugin_source_dir_exists(self, apm):
        for p in apm.get("marketplace", {}).get("plugins", []):
            source = p.get("source", "")
            if source.startswith("./"):
                path = ROOT / source[2:]
                assert path.exists(), (
                    f"plugin '{p.get('name')}' source '{source}' does not exist"
                )

    def test_each_plugin_has_description(self, apm):
        for p in apm.get("marketplace", {}).get("plugins", []):
            assert "description" in p, f"plugin '{p.get('name')}' must have 'description'"
