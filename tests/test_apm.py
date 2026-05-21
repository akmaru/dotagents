"""
Validate apm.yml structure.
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
    for field in ("name",):
        assert field in apm, f"apm.yml must have '{field}' field"
