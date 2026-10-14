"""
Validate the ontology package: manifest files, bundled reference files, and
scripts/ontology.py (parse, lint, scan, Alloy generation and Alloy verification)
on the glossary format of the glossary package (structure lives in CONTEXT.md, ADR 0026).

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
EXAMPLE = SKILL_DIR / "examples" / "order" / "CONTEXT.md"
BEFORE = SKILL_DIR / "examples" / "order-before" / "CONTEXT.md"

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
    """例の用語集を一時ディレクトリに写し、書き換えて読み直す関数を返す。"""
    path = tmp_path / "CONTEXT.md"
    shutil.copy(EXAMPLE, path)

    def edit(*pairs):
        text = path.read_text()
        for old, new in pairs:
            assert old in text, f"fixture text not found: {old!r}"
            text = text.replace(old, new, 1)
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
        assert data["dependencies"]["apm"] == ["../project-layout", "../glossary"]

    def test_listed_in_marketplace(self):
        data = yaml.safe_load((ROOT / "apm.yml").read_text())
        assert {"name": "ontology", "source": "./packages/ontology"} in data["marketplace"]["packages"]

    @pytest.mark.parametrize("name", ["GRILL.md", "ALLOY.md", "scripts/ontology.py", "examples/order/CONTEXT.md",
                                      "examples/order-before/CONTEXT.md"])
    def test_skill_references_bundled_file(self, name):
        assert (SKILL_DIR / name).exists()
        assert name in (SKILL_DIR / "SKILL.md").read_text()

    def test_no_separate_ontology_file(self):
        assert not list(PKG_DIR.rglob("ONTOLOGY.md")), "構造は用語集に書く（ADR 0026）"
        assert not (SKILL_DIR / "FORMAT.md").exists(), "書式は glossary パッケージだけが持つ"


class TestParse:
    def test_terms_definitions_and_structure(self):
        g = onto.parse(EXAMPLE)
        assert g.mode == "alloy" and g.scope == 4
        t = {x.name: x for x in g.terms}
        assert t["顧客"].aliases == ["Customer"]
        assert t["顧客"].definition == "当事者のうち、注文を 1 件以上出したもの。"
        assert t["顧客"].avoid == ["購入者", "クライアント"]
        assert t["顧客"].kind == "role" and t["顧客"].lst("is-a") == ["当事者"]
        assert t["注文"].groups("partition") == [["下書きの注文", "確定した注文", "取り消した注文"]]
        assert len(g.relations) == 2 and [a.ident for a in g.section("axioms")] == ["AX1", "AX2", "AX3", "AX4"]
        assert [r.closure for r in g.relations] == ["closed", "closed"]
        ax = {a.ident: a for a in g.section("axioms")}
        assert ax["AX2"].form == "necessary" and ax["AX2"].closure == "negated"
        assert ax["AX3"].form == "definition" and ax["AX3"].lst("depends") == ["注文", "AX2"]
        assert [r[0] for r in ax["AX3"].table] == ["注文", "下書きの注文", "確定した注文", "取り消した注文"]
        assert ax["AX4"].status == "retired" and ax["AX4"].get("merged-into") == "AX3"

    def test_english_labels(self, tmp_path):
        p = tmp_path / "CONTEXT.md"
        p.write_text("# Ordering\n\n## Language\n\n**Customer**:\nA party that has placed at least one order.\n"
                     "_Avoid_: buyer, client\n_Kind_: role\n_Is-a_: Party\n\n**Party**:\nA person or organization.\n_Kind_: kind\n")
        g = onto.parse(p)
        c = g.terms[0]
        assert c.avoid == ["buyer", "client"] and c.kind == "role" and c.lst("is-a") == ["Party"]

    def test_repo_glossary_parses(self):
        # dotagents 自身の用語集（構造の行を持たない定義だけの用語集）が読めること
        g = onto.parse(ROOT / "CONTEXT.md")
        spec = next(t for t in g.terms if t.name == "仕様書")
        assert spec.aliases == ["Spec"] and spec.avoid == ["要件定義書", "PRD"] and not spec.structured
        assert codes(onto.lint(g), "error") == []

    def test_avoid_notes_are_stripped(self):
        g = onto.parse(ROOT / "CONTEXT.md")
        issue = next(t for t in g.terms if t.name == "設計上の論点")
        assert issue.avoid == ["TODO", "課題"]
        assert "課題" not in onto.Index(g).avoid, "別の語として定義されている語は使わない語として扱わない"


class TestLint:
    def test_example_is_clean(self):
        findings = onto.lint(onto.parse(EXAMPLE))
        assert codes(findings, "error") == [] and codes(findings, "warning") == [], findings

    def test_markdown_verify_exits_zero(self, capsys):
        assert onto.main(["verify", str(EXAMPLE), "--mode", "markdown"]) == 0

    def test_unstated_sibling_relation(self, example):
        g = example(("_重なりうる_: 個人、法人\n", ""))
        msgs = [f.msg for f in onto.lint(g) if f.code == "UNSTATED"]
        assert any("個人 と 顧客" in m for m in msgs) and any("法人 と 顧客" in m for m in msgs)

    def test_unstated_coverage(self, example):
        g = example(("_分割_: 個人、法人\n", "_排他な下位_: 個人、法人\n"))
        assert any("網羅" in f.msg for f in onto.lint(g) if f.code == "UNSTATED")

    def test_disjoint_and_overlapping_is_contradiction(self, example):
        g = example(("_分割_: 個人、法人\n", "_分割_: 個人、法人\n_排他な下位_: 個人、顧客\n"))
        assert "CONTRA" in codes(onto.lint(g), "error")

    def test_disjoint_with_ancestor_is_contradiction(self, example):
        g = example(("_重なりうる_: 個人、法人\n", "_重なりうる_: 個人、法人\n_排他_: 当事者\n"))
        assert "CONTRA" in codes(onto.lint(g), "error")

    def test_isa_cycle(self, example):
        g = example(("_種別_: kind\n_分割_: 個人、法人\n", "_種別_: kind\n_上位_: 個人\n_分割_: 個人、法人\n"))
        assert "CYCLE" in codes(onto.lint(g), "error")

    def test_genset_member_must_be_child(self, example):
        g = example(("_分割_: 個人、法人\n", "_分割_: 個人、法人、注文\n"))
        assert "GENSET" in codes(onto.lint(g), "error")

    def test_definition_drifts_from_parent(self, example):
        g = example(("当事者のうち、注文を 1 件以上出したもの。", "注文を 1 件以上出したもの。"))
        assert "GENUS" in codes(onto.lint(g), "warning")

    def test_structure_without_kind(self, example):
        g = example(("_種別_: event\n_コード_: Shipment\n", "_コード_: Shipment\n"))
        assert "KIND" in codes(onto.lint(g), "error")

    def test_reference_to_unstructured_term(self, example):
        g = example(("_種別_: subkind\n_上位_: 当事者\n\n**法人", "_上位_: 当事者\n\n**法人"))
        errs = codes(onto.lint(g), "error")
        assert "KIND" in errs and "UNSTRUCTURED-REF" in errs

    def test_avoided_word_in_statement(self, example):
        g = example(("[[注文]] が [[発送]] の対象であるのは", "[[購入]] が [[発送]] の対象であるのは"))
        assert codes(onto.lint(g), "error") == ["AVOID"]

    def test_avoided_word_as_parent(self, example):
        g = example(("_種別_: role\n_上位_: 当事者\n", "_種別_: role\n_上位_: 購入者\n"))
        assert any("使わない語" in f.msg for f in onto.lint(g) if f.code == "REF")

    def test_undefined_reference(self, example):
        g = example(("[[注文]] が [[発送]] の対象であるのは", "[[配送業者]] が [[発送]] の対象であるのは"))
        assert "REF" in codes(onto.lint(g), "error")

    def test_role_needs_parent(self, example):
        g = example(("_種別_: role\n_上位_: 当事者\n", "_種別_: role\n"))
        assert "ISA" in codes(onto.lint(g), "error")

    def test_open_term_needs_question(self, example):
        g = example(("_種別_: role\n_上位_: 当事者\n", "_種別_: role\n_上位_: 当事者\n_状態_: assumed\n"))
        assert "OPENQ" in codes(onto.lint(g), "warning")

    def test_case_needs_expect(self, example):
        g = example(("- expect: possible\n", ""))
        assert "EXPECT" in codes(onto.lint(g), "error")

    def test_unknown_label(self, example):
        g = example(("_コード_: Shipment\n", "_コード_: Shipment\n_所有者_: 倉庫\n"))
        assert "LABEL" in codes(onto.lint(g), "warning")

    def test_definition_only_glossary_reports_unstructured(self, tmp_path):
        p = tmp_path / "CONTEXT.md"
        p.write_text("# X\n\n## 用語\n\n**注文（Order）**:\n顧客の申し込み。\n")
        f = onto.lint(onto.parse(p))
        assert codes(f, "error") == [] and codes(f, "warning") == [] and "UNSTRUCTURED" in codes(f)


class TestNormativeAxioms:
    """公理の文型・主語・閉包・場合分け・依存（C1〜C4）の静的な検査。"""

    def test_before_example_findings(self):
        f = onto.lint(onto.parse(BEFORE))
        errs = [x for x in f if x.level == "error"]
        c1 = [x.msg for x in errs if x.code == "C1"]
        assert any("AX4" in m and "AX3" in m for m in c1) and any("AX5" in m and "AX3" in m for m in c1)
        assert any("取り消した注文" in x.msg for x in errs if x.code == "C2")
        assert {m for x in errs if x.code == "C3" for m in ("AX2", "AX5") if m in x.msg} == {"AX2", "AX5"}
        assert sum(1 for x in f if x.code == "C3" and x.level == "warning") == 2  # R1・R2 の closure
        assert any("できる" in x.msg for x in f if x.code == "MODAL")
        assert not any(x.code in onto.BLOCKING for x in errs), "C1〜C4 は Alloy の検証を止めない"

    def test_form_is_required(self, example):
        g = example(("- form: 定義\n- subject: 顧客\n", "- subject: 顧客\n"))
        assert "FORM" in codes(onto.lint(g), "error")

    def test_statement_must_follow_form(self, example):
        g = example(("その当事者が [[注文]] を 1 件以上出している場合であり、かつその場合に限る",
                     "その当事者が [[注文]] を 1 件以上出している場合"))
        assert "FORM-TEXT" in codes(onto.lint(g), "warning")

    def test_sufficient_with_negated_closure_is_a_definition(self, example):
        g = example(("- form: 必要条件\n- subject: 発送\n- statement: [[注文]] が [[発送]] の対象であるのは、[[確定した注文]] の場合に限る",
                     "- form: 十分条件\n- subject: 発送\n- statement: [[注文]] が [[確定した注文]] ならば、[[発送]] の対象である"))
        assert any("定義と同じ" in x.msg for x in onto.lint(g) if x.code == "FORM")

    def test_undecided_closure_needs_question(self, example):
        g = example(("- closure: 否定\n", "- closure: 未決定\n"))
        assert any("未決事項" in x.msg for x in onto.lint(g) if x.code == "C3")

    def test_subject_must_exist(self, example):
        g = example(("- subject: 顧客\n", "- subject: 会員\n"))
        assert "SUBJECT" in codes(onto.lint(g), "error")

    def test_rule_added_to_definition(self, example):
        g = example(("## 帰結", "### AX5: 法人は顧客でない\n- form: 禁止\n- subject: 顧客\n"
                                "- statement: [[法人]] は [[顧客]] であってはならない\n- alloy: `no Organization & Customer`\n\n## 帰結"))
        assert any("AX5" in x.msg and "AX1" in x.msg for x in onto.lint(g) if x.code == "C1")

    def test_rule_referenced_from_definition_is_not_c1(self, example):
        g = example(("## 帰結", "### AX5: 法人は顧客でない\n- form: 禁止\n- subject: 顧客\n"
                                "- statement: [[法人]] は [[顧客]] であってはならない\n\n## 帰結"),
                    ("- alloy: `Customer = places.Order`\n", "- depends: AX5\n- alloy: `Customer = places.Order`\n"))
        assert "C1" not in codes(onto.lint(g))

    def test_scattered_rules_without_definition(self, example):
        g = example(("## 帰結", "### AX5: 発送はひとつ\n- form: 禁止\n- subject: 発送\n"
                                "- statement: [[下書きの注文]] は [[発送]] の対象であってはならない\n\n## 帰結"))
        assert "SCATTERED" in codes(onto.lint(g), "warning")

    def test_case_table_must_match_partition(self, example):
        g = example(("| 取り消した注文 | なし |\n", ""))
        assert any("取り消した注文" in x.msg for x in onto.lint(g) if x.code == "C2")

    def test_case_table_domain_narrows_rows(self, example):
        g = example(("| 取り消した注文 | なし |\n", ""),
                    ("- depends: 注文、AX2\n", "- depends: 注文、AX2\n- domain: 下書きの注文、確定した注文\n"))
        assert "C2" not in codes(onto.lint(g))

    def test_case_table_key_must_be_exhaustive(self, example):
        g = example(("_分割_: 下書きの注文、確定した注文、取り消した注文\n", "_排他な下位_: 下書きの注文、確定した注文、取り消した注文\n"))
        assert any("網羅を宣言していない" in x.msg for x in onto.lint(g) if x.code == "C2")

    def test_grounds_must_exist(self, example):
        g = example(("- grounds: AX1\n", "- grounds: AX9\n"))
        assert "C4-REF" in codes(onto.lint(g), "error")

    def test_grounds_label_must_exist(self, example):
        g = example(("- grounds: AX1\n", "- grounds: AX1(b)\n"),
                    ("- alloy: `Customer = places.Order`\n", "- conditions:\n  - (a) 注文を 1 件以上出している\n- alloy: `Customer = places.Order`\n"))
        msgs = [x.msg for x in onto.lint(g) if x.code == "C4-REF"]
        assert len(msgs) == 1 and "(b)" in msgs[0]
        assert [c[0] for c in next(a for a in g.section("axioms") if a.ident == "AX1").conditions] == ["a"]

    def test_grounds_must_not_point_to_retired(self, example):
        g = example(("- grounds: AX3、AX2\n- alloy: `no CancellableOrder", "- grounds: AX4\n- alloy: `no CancellableOrder"))
        assert any("retired" in x.msg for x in onto.lint(g) if x.code == "C4-REF")

    def test_retired_needs_existing_target(self, example):
        g = example(("- merged-into: AX3\n", "- merged-into: AX9\n"))
        assert "RETIRED" in codes(onto.lint(g), "error")

    def test_depends_cycle(self, example):
        g = example(("- form: 必要条件\n- subject: 発送\n", "- form: 必要条件\n- subject: 発送\n- depends: AX3\n"))
        assert "C4-CYCLE" in codes(onto.lint(g), "error")

    def test_unused_axiom(self, example):
        g = example(("- grounds: AX1\n", ""))
        assert any("AX1" in x.msg for x in onto.lint(g) if x.code == "C4-UNUSED")

    def test_relation_closure_value(self, example):
        g = example(("| set | one | closed |", "| set | one | sometimes |"))
        assert "FIELD" in codes(onto.lint(g), "error")


class TestScan:
    def test_finds_drift(self, tmp_path):
        (tmp_path / "spec.md").write_text("購入者は **ウィッシュリスト** に入れてから注文を出す。\n")
        (tmp_path / "model.py").write_text("class Customer:\n    pass\nclass Wishlist:\n    pass\n")
        findings = onto.scan(onto.parse(EXAMPLE), [str(tmp_path)])
        msgs = {}
        for f in findings:
            msgs.setdefault(f.code, []).append(f.msg)
        assert any("購入者" in m for m in msgs["AVOID-USE"])
        assert any("'Order'" in m for m in msgs["CODE-DRIFT"])
        assert not any("'Customer'" in m for m in msgs["CODE-DRIFT"])
        assert {"ウィッシュリスト", "Wishlist"} <= {m.split("'")[1] for m in msgs["CANDIDATE"]}


class TestAlloyGeneration:
    def test_translation(self):
        src, cmds, labels, _ = onto.generate_alloy(onto.parse(EXAMPLE))
        assert "sig Party { places: set Order }" in src
        assert "sig Customer in Party {}" in src
        assert "no Person & Organization" in src
        assert "Order = DraftOrder + PlacedOrder + CancelledOrder" in src
        assert "all y: Order | one places.y" in src
        assert {"AX_AX1", "AX_AX2", "inv_R1", "mult_R2"} <= set(labels)
        names = {c.name for c in cmds}
        assert {"consistency", "check_CHK1", "case_SC2", "overlap_Organization_Customer"} <= names

    def test_open_terms_are_not_constraints(self, example):
        g = example(("_種別_: event\n_コード_: Shipment\n", "_種別_: event\n_状態_: open\n_コード_: Shipment\n"))
        assert "sig Shipment" not in onto.generate_alloy(g)[0]

    def test_exclude_comments_out_fact(self):
        src, *_ = onto.generate_alloy(onto.parse(EXAMPLE), exclude={"AX_AX2"})
        assert "fact AX_AX2" not in src


@needs_alloy
class TestAlloyVerify:
    def test_example_passes(self):
        findings, _ = onto.verify_alloy(onto.parse(EXAMPLE))
        assert codes(findings, "error") == [] and codes(findings, "warning") == []
        assert codes(findings).count("OK") >= 23

    def test_missing_axiom_gives_counterexample(self, example):
        g = example(("- alloy: `Shipment.target in PlacedOrder`\n", ""))
        errs = [f for f in onto.verify_alloy(g)[0] if f.level == "error"]
        assert set(codes(errs)) == {"CHECK-FAIL", "TOO-LOOSE"}
        assert any("CancelledOrder" in f.msg for f in errs if f.code == "CHECK-FAIL")

    def test_conflict_reports_minimal_core(self, example):
        g = example(("## 帰結", "### AX3: 顧客は個人に限る\n- status: assumed\n- statement: [[顧客]] は [[個人]]\n"
                               "- alloy: `Customer in Person`\n\n## 帰結"))
        errs = [f for f in onto.verify_alloy(g)[0] if f.level == "error"]
        assert errs and all(f.code == "UNSAT" for f in errs)
        for f in errs:
            assert "AX_AX3" in f.msg and "partition1_disj_Party" in f.msg
            assert "AX_AX1" not in f.msg  # 極小の組だけを出す

    def test_before_example_conflict_is_shown_by_alloy(self):
        findings, _ = onto.verify_alloy(onto.parse(BEFORE))
        c1 = [x for x in findings if x.code == "C1-ALLOY"]
        bad = next(x for x in c1 if x.level == "error")
        assert "AX4" in bad.msg and "CancellableOrder" in bad.msg  # 発送された確定した注文が、AX3 では取り消せる
        assert any(x.level == "info" and "AX5" in x.msg for x in c1)  # AX5 は AX3 から導かれる（重複）
        # AX3 と AX4 を合わせると、発送そのものが起こりえなくなる
        assert any(x.code == "UNSAT" and "発送" in x.msg and "AX_AX4" in x.msg for x in findings)

    def test_verify_runs_alloy_despite_c1_errors(self, capsys):
        assert onto.main(["verify", str(BEFORE)]) == 1
        assert "C1-ALLOY" in capsys.readouterr().out

    def test_bad_formula_is_reported(self, example):
        g = example(("`Shipment.target in PlacedOrder`", "`Shipment.target in Placed`"))
        assert codes(onto.verify_alloy(g)[0]) == ["ALLOY-SYNTAX"]
