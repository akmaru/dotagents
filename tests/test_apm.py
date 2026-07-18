"""
Validate the root marketplace apm.yml and each package's apm.yml.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
APM_YML = ROOT / "apm.yml"
PACKAGES_DIR = ROOT / "packages"


@pytest.fixture(scope="module")
def apm():
    return yaml.safe_load(APM_YML.read_text())


def test_apm_yml_exists():
    assert APM_YML.exists()


def test_required_fields(apm):
    for field in ("name", "version"):
        assert field in apm, f"apm.yml must have '{field}' field"


def test_has_marketplace_block(apm):
    assert "marketplace" in apm, "apm.yml must have a 'marketplace' block"


def test_owner_has_name(apm):
    owner = apm["marketplace"].get("owner", {})
    assert owner.get("name"), "marketplace.owner.name is required"


def test_packages_listed(apm):
    packages = apm["marketplace"].get("packages", [])
    assert len(packages) >= 1, "marketplace.packages must list at least one package"


def test_local_package_sources_exist(apm):
    for p in apm["marketplace"]["packages"]:
        source = p.get("source", "")
        if isinstance(source, str) and source.startswith("./"):
            assert (ROOT / source[2:]).exists(), (
                f"package '{p.get('name')}' source '{source}' does not exist"
            )


def test_marketplace_packages_match_directories(apm):
    listed = {
        p["source"][2:].split("/")[-1]
        for p in apm["marketplace"]["packages"]
        if isinstance(p.get("source"), str) and p["source"].startswith("./packages/")
    }
    on_disk = {d.name for d in PACKAGES_DIR.iterdir() if d.is_dir()}
    assert listed == on_disk, (
        f"packages/ dirs {on_disk} must match locally-sourced marketplace entries {listed}"
    )


def _package_apm_files():
    if not PACKAGES_DIR.exists():
        return []
    return sorted(PACKAGES_DIR.glob("*/apm.yml"))


@pytest.mark.parametrize("apm_file", _package_apm_files(), ids=lambda p: p.parent.name)
class TestPackageManifest:
    def test_required_fields(self, apm_file):
        data = yaml.safe_load(apm_file.read_text())
        for field in ("name", "version", "description", "author", "license"):
            assert field in data, f"{apm_file.parent.name}/apm.yml must have '{field}'"

    def test_name_matches_directory(self, apm_file):
        data = yaml.safe_load(apm_file.read_text())
        assert data["name"] == apm_file.parent.name, (
            f"name '{data['name']}' must match directory '{apm_file.parent.name}'"
        )
