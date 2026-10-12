"""
Validate the ontology package: manifest files, the bundled reference files, and
scripts/ontology.py (lint, scan, init, Alloy generation and Alloy verification).

Alloy tests run only when `java` is on PATH and an Alloy jar is available
(ALLOY_JAR, or the cache that `ontology.py setup-alloy` fills).
"""

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
PKG_DIR = ROOT / "packages" / "ontology"
SKILL_DIR = PKG_DIR / ".apm" / "skills" / "ontology"
EXAMPLE = SKILL_DIR / "examples" / "order"

_spec = importlib.util.spec_from_file_location("ontology_tool", SKILL_DIR / "scripts" / "ontology.py")
onto = importlib.util.module_from_spec(_spec)
sys.modules["ontology_tool"] = onto  # dataclass が自分のモジュールを引けるように
_spec.loader.exec_module(onto)


def _alloy_available():
    if not shutil.which("java"):
        return False
    try:
        return onto.find_jar(download=False) is not None
    except onto.AlloyError:
        return False


needs_alloy = pytest.mark.skipif(not _alloy_available(), reason="java or Alloy jar not available")


@pytest.fixture
def example(tmp_path):
    """examples/order を一時ディレクトリに写し、ONTOLOGY.md を書き換える関数を返す。"""
    for f in EXAMPLE.iterdir():
        shutil.copy(f, tmp_path / f.name)
    path = tmp_path / "ONTOLOGY.md"

    def edit(*pairs):
        text = path.read_text()
        for old, new in pairs:
            assert old in text, f"fixture text not found: {old!r}"
            text = text.replace(old, new)
        path.write_text(text)
        return onto.parse(path)

    edit.path = path
    return edit


def codes(findings, level=None):
    return [f.code for f in findings if level is None or f.level == level]


class TestPackageFiles:
    @pytest.mark.parametrize("name", ["apm.yml", "README.md", "LICENSE"])
    def test_exists(self, name):
        assert (PKG_DIR / name).exists()

    def test_apm_yml(self):
        data = yaml.safe_load((PKG_DIR / "apm.yml").read_text())
        for field in ("name", "version", "description", "author", "license"):
            assert field in data
        assert data["name"] == "ontology"
        assert "../project-layout" in data["dependencies"]["apm"]

    def test_listed_in_marketplace(self):
        data = yaml.safe_load((ROOT / "apm.yml").read_text())
        assert {"name": "ontology", "source": "./packages/ontology"} in data["marketplace"]["packages"]

    @pytest.mark.parametrize("name", ["FORMAT.md", "GRILL.md", "ALLOY.md", "scripts/ontology.py"])
    def test_skill_references_bundled_file(self, name):
        assert (SKILL_DIR / name).exists()
        assert name in (SKILL_DIR / "SKILL.md").read_text()


class TestExample:
    def test_lint_is_clean(self):
        findings = onto.lint(onto.parse(EXAMPLE / "ONTOLOGY.md"))
        assert codes(findings, "error") == [] and codes(findings, "warning") == [], findings

    def test_reads_glossary(self):
        o = onto.parse(EXAMPLE / "ONTOLOGY.md")
        names = {g.name for g in o.glossary}
        assert {"顧客", "注文", "発送"} <= names
        customer = next(g for g in o.glossary if g.name == "顧客")
        assert customer.aliases == ["Customer"] and "購入者" in customer.avoid

    def test_markdown_verify_exits_zero(self, capsys):
        assert onto.main(["verify", str(EXAMPLE / "ONTOLOGY.md"), "--mode", "markdown"]) == 0

    def test_repo_glossary_parses(self):
        # dotagents 自身の CONTEXT.md（grill-with-docs の書式）が読めること
        terms = onto.parse_glossary(ROOT / "CONTEXT.md")
        assert any(t.name == "仕様書" and "Spec" in t.aliases for t in terms)


class TestLint:
    def test_unstated_sibling_relation(self, example):
        o = example(("- overlaps: 個人, 法人\n", ""))
        msgs = [f.msg for f in onto.lint(o) if f.code == "UNSTATED"]
        assert any("個人 と 顧客" in m or "顧客 と 個人" in m for m in msgs)

    def test_unstated_coverage(self, example):
        o = example(("- partition: 個人, 法人\n", "- disjoint-children: 個人, 法人\n"))
        assert any("網羅" in f.msg for f in onto.lint(o) if f.code == "UNSTATED")

    def test_disjoint_and_overlapping_is_contradiction(self, example):
        o = example(("- partition: 個人, 法人\n", "- partition: 個人, 法人\n- disjoint-children: 個人, 顧客\n"))
        assert "CONTRA" in codes(onto.lint(o), "error")

    def test_disjoint_with_ancestor_is_contradiction(self, example):
        o = example(("- overlaps: 個人, 法人\n", "- overlaps: 個人, 法人\n- disjoint: 当事者\n"))
        assert "CONTRA" in codes(onto.lint(o), "error")

    def test_isa_cycle(self, example):
        o = example(("### 当事者（Party）\n- kind: kind\n", "### 当事者（Party）\n- kind: kind\n- is-a: 個人\n"))
        assert "CYCLE" in codes(onto.lint(o), "error")

    def test_genset_member_must_be_child(self, example):
        o = example(("- partition: 個人, 法人\n", "- partition: 個人, 法人, 注文\n"))
        assert "GENSET" in codes(onto.lint(o), "error")

    def test_term_missing_from_glossary(self, example):
        o = example(("## 関係", "### 返品（Return）\n- kind: event\n- status: confirmed\n\n## 関係"))
        assert "GLOSSARY" in codes(onto.lint(o), "error")

    def test_avoided_word_in_statement(self, example):
        o = example(("[[発送]] の対象は必ず", "[[購入]] の対象は必ず"))
        errs = [f for f in onto.lint(o) if f.level == "error"]
        assert codes(errs) == ["AVOID"]

    def test_undefined_reference(self, example):
        o = example(("[[発送]] の対象は必ず", "[[配送業者]] の対象は必ず"))
        assert "REF" in codes(onto.lint(o), "error")

    def test_role_needs_parent(self, example):
        o = example(("- kind: role\n- is-a: 当事者\n", "- kind: role\n"))
        assert "ISA" in codes(onto.lint(o), "error")

    def test_open_term_needs_question(self, example):
        o = example(("- kind: role\n- is-a: 当事者\n- status: confirmed\n", "- kind: role\n- is-a: 当事者\n- status: assumed\n"))
        assert "OPENQ" in codes(onto.lint(o), "warning")

    def test_scenario_needs_expect(self, example):
        o = example(("- expect: possible\n", ""))
        assert "EXPECT" in codes(onto.lint(o), "error")


class TestScan:
    def test_finds_drift(self, tmp_path):
        (tmp_path / "spec.md").write_text("購入者は **ウィッシュリスト** に入れてから注文を出す。\n")
        (tmp_path / "model.py").write_text("class Customer:\n    pass\nclass Wishlist:\n    pass\n")
        findings = onto.scan(onto.parse(EXAMPLE / "ONTOLOGY.md"), [str(tmp_path)])
        msgs = {f.code: [] for f in findings}
        for f in findings:
            msgs[f.code].append(f.msg)
        assert any("購入者" in m for m in msgs["AVOID-USE"])
        assert any("'Order'" in m for m in msgs["CODE-DRIFT"])
        assert not any("'Customer'" in m for m in msgs["CODE-DRIFT"])
        assert {"ウィッシュリスト", "Wishlist"} <= {m.split("'")[1] for m in msgs["CANDIDATE"]}


class TestInit:
    def test_creates_stub_from_glossary(self, tmp_path):
        shutil.copy(EXAMPLE / "CONTEXT.md", tmp_path / "CONTEXT.md")
        out = tmp_path / "ONTOLOGY.md"
        assert onto.init(tmp_path / "CONTEXT.md", "alloy", out) == 0
        o = onto.parse(out)
        assert o.mode == "alloy"
        assert len(o.section("terms")) == len(o.glossary) == 9
        assert codes(onto.lint(o), "error") == []  # 未決の雛形は warning だけ

    def test_does_not_overwrite(self, tmp_path):
        out = tmp_path / "ONTOLOGY.md"
        out.write_text("keep")
        assert onto.init(EXAMPLE / "CONTEXT.md", "markdown", out) == 1
        assert out.read_text() == "keep"


class TestAlloyGeneration:
    def test_translation(self):
        src, cmds, labels, _ = onto.generate_alloy(onto.parse(EXAMPLE / "ONTOLOGY.md"))
        assert "sig Customer in Party { places: set Order }" not in src  # field は from の sig に付く
        assert "sig Party { places: set Order }" in src
        assert "sig Customer in Party {}" in src
        assert "no Person & Organization" in src
        assert "Order = DraftOrder + PlacedOrder + CancelledOrder" in src
        assert "all y: Order | one places.y" in src
        assert {"AX_AX1", "AX_AX2", "inv_R1", "mult_R2"} <= set(labels)
        names = {c.name for c in cmds}
        assert {"consistency", "check_CHK1", "scenario_SC2", "overlap_Organization_Customer"} <= names

    def test_exclude_comments_out_fact(self):
        src, *_ = onto.generate_alloy(onto.parse(EXAMPLE / "ONTOLOGY.md"), exclude={"AX_AX2"})
        assert "fact AX_AX2" not in src


@needs_alloy
class TestAlloyVerify:
    def test_example_passes(self):
        findings, _ = onto.verify_alloy(onto.parse(EXAMPLE / "ONTOLOGY.md"))
        assert codes(findings, "error") == [] and codes(findings, "warning") == []
        assert codes(findings).count("OK") >= 18

    def test_missing_axiom_gives_counterexample(self, example):
        o = example(("- alloy: `Shipment.target in PlacedOrder`\n", ""))
        errs = [f for f in onto.verify_alloy(o)[0] if f.level == "error"]
        assert sorted(codes(errs)) == ["CHECK-FAIL", "TOO-LOOSE"]
        assert "CancelledOrder" in next(f.msg for f in errs if f.code == "CHECK-FAIL")

    def test_conflict_reports_minimal_core(self, example):
        o = example(("## 帰結", "### AX3: 顧客は個人に限る\n- status: assumed\n- statement: [[顧客]] は [[個人]]\n"
                               "- alloy: `Customer in Person`\n\n## 帰結"))
        errs = [f for f in onto.verify_alloy(o)[0] if f.level == "error"]
        assert errs and all(f.code == "UNSAT" for f in errs)
        for f in errs:
            assert "AX_AX3" in f.msg and "partition1_disj_Party" in f.msg
            assert "AX_AX1" not in f.msg  # 極小の組だけを出す

    def test_bad_formula_is_reported(self, example):
        o = example(("`Shipment.target in PlacedOrder`", "`Shipment.target in Placed`"))
        assert codes(onto.verify_alloy(o)[0]) == ["ALLOY-SYNTAX"]
