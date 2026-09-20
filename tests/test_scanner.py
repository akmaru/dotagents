"""
hindsight/scanner/ の検出ロジックを検証する。

検出器は正規表現の塊で、ルールを足すたびに誤検出が増える性質がある。
ここに入れてあるのは 2026-09-20 に personal バンクで実際に起きた破損と、
誤検出させてはいけない実例なので、ルールを触るときはこれを通すこと。

API との通信部分はここでは検証しない (サーバーと Docker が要るため)。
"""

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SCANNER_DIR = ROOT / "hindsight" / "scanner"
COMPOSE_FILE = ROOT / "hindsight" / "compose" / "docker-compose.yml"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("scanner", SCANNER_DIR / "scanner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["scanner"] = module
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


# 2026-09-20 に実際に壊れた形。左が投入した原文、右が保存された本文。
REAL_DAMAGE = [
    (
        "API キーは macOS Keychain の hindsight-mcp-api-key に保管",
        "APIキーはmacOS Keychainのhindsightmcpapikeyに保管",
        "hindsight-mcp-api-key",
        "separator-loss",
    ),
    (
        "EC2 インスタンスは i-039d0c0f33dff67be（t4g.medium）",
        "EC2インスタンスはi039d0c0f33dff67be（t4gmedium）",
        "i-039d0c0f33dff67be",
        "separator-loss",
    ),
    (
        "backend.hcl と terraform.tfvars は gitignore している",
        "backend.hclおよびterraformtfvarsはgitignore対象",
        "terraform.tfvars",
        "separator-loss",
    ),
    (
        "aws ssm start-session または aws ssm send-command で操作する",
        "操作はaws ssm start sessionまたはaws ssm send commandで実行",
        "start-session",
        "separator-to-space",
    ),
    (
        "HINDSIGHT_API_CONSOLIDATION_LLM_MODEL で consolidation のモデルを上げる",
        "HINDSIGHT_API_CONSOLIDATION_LLMモデルでconsolidationのモデルを上げる",
        "HINDSIGHT_API_CONSOLIDATION_LLM_MODEL",
        "prefix-truncation",
    ),
]

# 壊れていない実例。ここで検出が出たら誤検出。
CLEAN = [
    # 識別子の直後に助詞が続くだけ。完全形が残っているので破損ではない。
    (
        "モデルごとの環境変数は HINDSIGHT_API_REFLECT_LLM_MODEL で指定する",
        "HINDSIGHT_API_REFLECT_LLM_MODELで指定する",
    ),
    # 要約で識別子が落ちただけ。崩れた形では現れていない。
    (
        "Terraform state は S3 バケット akmaru-dev-tfstate の key dotagents/hindsight.tfstate に配置",
        "Terraform state は S3 に配置している",
    ),
    # 表記の揺れ (言い換え) は対象外。
    (
        "postgres コンテナは pgvector/pgvector:pg17 を使う",
        "PostgreSQL コンテナは pgvector/pgvector:pg17 を使う",
    ),
    # 同じ綴りがそのまま残っている。
    (
        "aws sso login --profile maru が必要",
        "AWS 操作前に aws sso login --profile maru が必要",
    ),
    # ソース引用から行番号だけが落ちるのは要約であって識別子の破損ではない。
    # 2026-09-20 の実データで唯一これを誤検出した。
    (
        "engine/consolidation/prompts.py:177 の分岐で言語ルールを選ぶ",
        "engine/consolidation/prompts.pyの分岐で言語ルールを選ぶ",
    ),
]


@pytest.mark.parametrize("source,target,expected,rule", REAL_DAMAGE)
def test_detects_real_damage(source, target, expected, rule):
    findings = scanner.find_damage(source, target)
    assert [f for f in findings if f["expected"] == expected and f["rule"] == rule], findings


@pytest.mark.parametrize("source,target", CLEAN)
def test_no_false_positive(source, target):
    assert scanner.find_damage(source, target) == []


def test_identical_text_is_clean():
    text = "HINDSIGHT_API_LLM_OUTPUT_LANGUAGE=Japanese を compose/docker-compose.yml で設定"
    assert scanner.find_damage(text, text) == []


def test_short_identifiers_are_ignored():
    """下限未満の識別子は偶然の一致が多いので拾わない。"""
    assert scanner.find_damage("a-b を使う", "ab を使う") == []


def test_compose_runs_the_scanner():
    compose = yaml.safe_load(COMPOSE_FILE.read_text())
    service = compose["services"]["scanner"]
    assert service["build"] == "../scanner"
    # API は compose ネットワーク内で叩く (Caddy と公開 URL を経由しない)。
    assert service["environment"]["HINDSIGHT_API_URL"] == "http://hindsight-api:8888"
    # レポートはスナップショット対象の EBS ボリューム上に置く。
    assert any("/state" in v for v in service["volumes"])


def test_scanner_has_no_third_party_dependencies():
    """標準ライブラリだけで動くこと (Dockerfile に pip install を置かない)。"""
    assert "pip install" not in (SCANNER_DIR / "Dockerfile").read_text()
