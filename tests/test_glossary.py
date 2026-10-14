"""
Validate the glossary package and the two rules from ADR 0026:

1. Every package that reads or writes the glossary (CONTEXT.md) depends directly on
   ../glossary, so the format file is installed next to it.
2. The glossary format (CONTEXT-FORMAT.md) exists only in the glossary package (SSOT).
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
PACKAGES = ROOT / "packages"
GLOSSARY = PACKAGES / "glossary"
FORMAT = GLOSSARY / ".apm" / "skills" / "glossary" / "CONTEXT-FORMAT.md"

# 用語集の置き場だけを知っていて、中身は読み書きしないパッケージ（ADR 0024 / 0025 / 0026）。
# init-project は CONTEXT.md を作らず、生成する AGENTS.md に置き場を 1 行書くだけ。
PLACEMENT_ONLY = {"glossary", "project-layout", "init-project"}


def _deps(pkg: Path) -> list:
    data = yaml.safe_load((pkg / "apm.yml").read_text())
    return (data.get("dependencies") or {}).get("apm") or []


def glossary_users():
    """スキルのファイル（.apm/ 配下）で CONTEXT.md に触れているパッケージ。"""
    users = []
    for pkg in sorted(p for p in PACKAGES.iterdir() if (p / "apm.yml").exists()):
        if pkg.name in PLACEMENT_ONLY:
            continue
        files = [f for f in (pkg / ".apm").rglob("*") if f.is_file() and f.suffix in {".md", ".py", ".json"}]
        if any("CONTEXT.md" in f.read_text(errors="ignore") for f in files):
            users.append(pkg)
    return users


class TestPackageFiles:
    @pytest.mark.parametrize("name", ["apm.yml", "README.md", "LICENSE"])
    def test_exists(self, name):
        assert (GLOSSARY / name).exists()

    def test_has_no_dependencies(self):
        assert _deps(GLOSSARY) == [], "書式は置き場を知らなくても書けるので、glossary は何にも依存しない"

    def test_listed_in_marketplace(self):
        data = yaml.safe_load((ROOT / "apm.yml").read_text())
        assert {"name": "glossary", "source": "./packages/glossary"} in data["marketplace"]["packages"]

    def test_skill_points_to_format(self):
        assert "CONTEXT-FORMAT.md" in (GLOSSARY / ".apm/skills/glossary/SKILL.md").read_text()


class TestFormat:
    @pytest.mark.parametrize(
        "word",
        ["_使わない_", "_種別_", "_上位_", "_分割_", "_排他な下位_", "_網羅する下位_", "_重なりうる下位_",
         "_網羅_", "_排他_", "_重なりうる_", "_状態_", "_コード_", "_ID_", "CONTEXT-MAP.md",
         "`form`", "`subject`", "`closure`", "`depends`", "`grounds`", "`conditions`", "`domain`", "`merged-into`",
         "`retired`", "`closed`"],
    )
    def test_defines(self, word):
        assert word in FORMAT.read_text()

    @pytest.mark.parametrize("heading", ["## 関係", "## 公理", "## 帰結", "## 事例", "## 未決事項", "## 対象外"])
    def test_has_cross_term_section(self, heading):
        assert heading in FORMAT.read_text()

    def test_english_labels_map_to_the_parser(self):
        # 用語集の言語が英語でも ontology のスクリプトが読めること
        import importlib.util
        import sys

        path = PACKAGES / "ontology/.apm/skills/ontology/scripts/ontology.py"
        spec = importlib.util.spec_from_file_location("ontology_for_glossary_test", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        text = FORMAT.read_text()
        for line in text.splitlines():
            if line.startswith("| `_") and "`_" in line.split("|")[2]:
                ja = line.split("|")[1].strip().strip("`").strip("_")
                en = line.split("|")[2].strip().strip("`").strip("_")
                assert mod.label_key(ja) is not None and mod.label_key(ja) == mod.label_key(en), (ja, en)


def test_format_is_single_source_of_truth():
    copies = sorted(str(p.relative_to(ROOT)) for p in PACKAGES.rglob("CONTEXT-FORMAT.md"))
    assert copies == [str(FORMAT.relative_to(ROOT))], f"CONTEXT-FORMAT.md は glossary にだけ置く: {copies}"


def test_glossary_users_are_detected():
    names = {p.name for p in glossary_users()}
    assert {"grill-with-docs", "grill-spec", "ontology"} <= names


@pytest.mark.parametrize("pkg", glossary_users(), ids=lambda p: p.name)
def test_glossary_users_depend_on_glossary_directly(pkg):
    assert "../glossary" in _deps(pkg), f"{pkg.name} は CONTEXT.md を扱うので ../glossary に直接依存する"


@pytest.mark.parametrize("pkg", glossary_users(), ids=lambda p: p.name)
def test_glossary_users_refer_to_glossary_skill(pkg):
    skill = pkg / ".apm" / "skills" / pkg.name / "SKILL.md"
    assert "`glossary`" in skill.read_text(), "書式は glossary スキルを参照させる"


def test_normative_vocabulary_is_shared_by_writing_rules_format_and_parser():
    """規範文の文型と閉包の語が、clear-writing・用語集の書式・ontology のスクリプトでそろっている。"""
    import importlib.util
    import sys

    path = PACKAGES / "ontology/.apm/skills/ontology/scripts/ontology.py"
    spec = importlib.util.spec_from_file_location("ontology_for_vocab_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    writing = (PACKAGES / "clear-writing/.apm/skills/clear-writing/SKILL.md").read_text()
    fmt = FORMAT.read_text()
    for word in ("定義", "十分条件", "必要条件", "禁止"):
        assert word in mod.FORMS and word in writing and f"`{word}`" in fmt, word
    for word in ("否定", "未決定", "対象外"):
        assert word in mod.CLOSURES and word in writing and f"`{word}`" in fmt, word
    for word in ("しなければならない", "してはならない", "してもよい"):
        assert word in writing
