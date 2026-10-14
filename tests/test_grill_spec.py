"""
Validate the grill-spec package: its 3 bundled skill files, the glossary format taken
from the glossary package (not a copy), and the package manifest files.

See docs/adr/0022-grill-spec-separate-self-contained-package.md,
docs/adr/0026-glossary-format-package-and-structure-in-glossary.md and
packages/grill-spec/docs/internal/specs/0001-grill-spec.md (AC7).
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
PKG_DIR = ROOT / "packages" / "grill-spec"
SKILL_DIR = PKG_DIR / ".apm" / "skills" / "grill-spec"
GLOSSARY_FORMAT = ROOT / "packages" / "glossary" / ".apm" / "skills" / "glossary" / "CONTEXT-FORMAT.md"


def _frontmatter(skill_md: Path) -> dict:
    content = skill_md.read_text()
    parts = content.split("---", 2)
    assert len(parts) == 3, "SKILL.md must have YAML frontmatter delimited by ---"
    return yaml.safe_load(parts[1]) or {}


class TestPackageFiles:
    def test_apm_yml_exists(self):
        assert (PKG_DIR / "apm.yml").exists()

    def test_readme_exists(self):
        assert (PKG_DIR / "README.md").exists()

    def test_license_exists(self):
        assert (PKG_DIR / "LICENSE").exists()

    def test_apm_yml_required_fields(self):
        data = yaml.safe_load((PKG_DIR / "apm.yml").read_text())
        for field in ("name", "version", "description", "author", "license"):
            assert field in data, f"apm.yml must have '{field}'"
        assert data["name"] == "grill-spec"


class TestBundledSkillFiles:
    @pytest.mark.parametrize("name", ["SKILL.md", "SPEC-FORMAT.md", "REFINEMENT.md"])
    def test_file_exists(self, name):
        assert (SKILL_DIR / name).exists(), f"{name} not found in {SKILL_DIR}/"

    def test_does_not_bundle_glossary_format(self):
        # 用語集の書式は glossary パッケージだけが持つ（ADR 0026）
        assert not (SKILL_DIR / "CONTEXT-FORMAT.md").exists()
        assert GLOSSARY_FORMAT.exists()

    def test_depends_on_glossary(self):
        data = yaml.safe_load((PKG_DIR / "apm.yml").read_text())
        assert data["dependencies"]["apm"] == ["../glossary"]


class TestSkillMdFrontmatter:
    def test_name_is_grill_spec(self):
        fm = _frontmatter(SKILL_DIR / "SKILL.md")
        assert fm.get("name") == "grill-spec"

    def test_description_length_within_limit(self):
        fm = _frontmatter(SKILL_DIR / "SKILL.md")
        desc = str(fm.get("description", ""))
        assert 1 <= len(desc) <= 1024, "description must be 1-1024 characters"


class TestSkillMdReferencesSiblingFiles:
    @pytest.mark.parametrize(
        "name", ["SPEC-FORMAT.md", "REFINEMENT.md", "CONTEXT-FORMAT.md", "`glossary`"]
    )
    def test_references(self, name):
        body = (SKILL_DIR / "SKILL.md").read_text()
        assert name in body, f"SKILL.md must reference {name}"


class TestSpecFormat:
    @classmethod
    @pytest.fixture(scope="class")
    def body(cls):
        return (SKILL_DIR / "SPEC-FORMAT.md").read_text()

    @pytest.mark.parametrize(
        "heading",
        ["課題", "ユーザーストーリー", "ユーザージャーニー", "受け入れ基準", "スコープ外", "制約", "設計上の論点"],
    )
    def test_has_section_heading(self, body, heading):
        assert heading in body

    @pytest.mark.parametrize("prefix", ["P1", "S1", "J1", "AC1", "D1"])
    def test_has_id_prefix(self, body, prefix):
        assert prefix in body

    @pytest.mark.parametrize("status", ["draft", "accepted", "revising"])
    def test_has_status_value(self, body, status):
        assert status in body

    @pytest.mark.parametrize(
        "english_heading",
        [
            "Problems",
            "User Stories",
            "User Journeys",
            "Acceptance Criteria",
            "Out of Scope",
            "Constraints",
            "Open Design Issues",
        ],
    )
    def test_has_english_translation(self, body, english_heading):
        assert english_heading in body


class TestRefinement:
    @classmethod
    @pytest.fixture(scope="class")
    def body(cls):
        return (SKILL_DIR / "REFINEMENT.md").read_text()

    def test_mentions_general_purpose_subagent(self, body):
        assert "general-purpose" in body

    def test_mentions_running_state(self, body):
        assert "running" in body

    def test_mentions_overriding_constraints(self, body):
        assert "覆す" in body

    def test_report_formats_ask_whether_a_finding_overrides_constraints(self, body):
        # 覆す指摘は重要度にかかわらず 1 件ずつ聞くので、両方の観点の報告書式にこの項目が要る（仕様書 AC24・AC25）
        assert body.count("制約の行を覆すか") >= 2

    def test_records_open_findings_before_asking(self, body):
        # 打ち切りが起きてから台帳に書くことはできない。振り分けた時点で open として書く（仕様書 AC27）
        assert "`open`" in body
        assert body.index("`open`") < body.index("1 件ずつ聞くときの選択肢")


@pytest.mark.parametrize("name", ["SKILL.md", "SPEC-FORMAT.md", "REFINEMENT.md"])
def test_bundled_files_do_not_cite_dotagents_internal_spec(name):
    """同梱ファイルは任意のリポジトリで読まれるので、dotagents の中にしか無い grill-spec 自身の
    仕様書（その AC 番号）を根拠として指してはいけない（仕様書 AC8）。"""
    body = (SKILL_DIR / name).read_text()
    assert "仕様書 AC" not in body
    assert "0001-grill-spec" not in body
    # 書式の例（`AC1`、`**AC8**（手順1）`）は許し、AC 番号を根拠として指す書き方だけを禁じる
    assert not re.search(r"AC\d+\s*(参照|の基準|に従)", body)


def test_skill_md_resumes_a_refinement_left_running():
    # リファインメントの途中で止まったら、再開時に保存済みの報告を取り込み、欠けた観点だけ起動し直す（仕様書 J1 手順 9、ADR 0022 の決定の適用）
    body = (SKILL_DIR / "SKILL.md").read_text()
    assert "running" in body


class TestReviewFindings:
    """PR #45 の機械レビューで、テストが見ていなかった指示の漏れが見つかった分（review-v1 の #1〜#9）。"""

    @classmethod
    @pytest.fixture(scope="class")
    def skill(cls):
        return (SKILL_DIR / "SKILL.md").read_text()

    @classmethod
    @pytest.fixture(scope="class")
    def refinement(cls):
        return (SKILL_DIR / "REFINEMENT.md").read_text()

    @classmethod
    @pytest.fixture(scope="class")
    def spec_format(cls):
        return (SKILL_DIR / "SPEC-FORMAT.md").read_text()

    @pytest.mark.parametrize("section", ["この版で触ったファイル", "振り分けた発言", "足した用語", "この版で作った issue"])
    def test_skill_md_writes_each_ledger_section(self, skill, section):
        # 書き込む指示が無いと、セッションをまたいだとき確定のまとめや改訂の中止が空になる
        assert section in skill

    def test_skill_md_writes_version_line(self, skill):
        assert "revising 開始" in skill and "draft 作成" in skill

    def test_judgment_free_fixes_exclude_opposing_findings(self, refinement):
        assert "反対の立場の指摘はすべて判断の要る側" in refinement

    def test_revising_resume_includes_open_change_requests(self, skill):
        assert "「変えたい点」のうち `open`" in skill

    def test_context_map_rules(self, skill):
        assert "常に読む" in skill
        assert "shared" in skill and "common" in skill

    def test_refinement_is_completed_inside_refinement_md(self, skill):
        # 判断の要る指摘を SKILL.md と REFINEMENT.md の両方で聞かない
        assert "その中で" in skill and "聞く" in skill

    def test_minor_findings_are_asked_with_multiselect(self, refinement):
        assert "multiSelect" in refinement

    def test_spec_format_ledger_can_express_withdrawal_spec_changing_count_and_issues(self, spec_format):
        assert "withdrawn" in spec_format
        assert "仕様を変えた採用" in spec_format
        assert "この版で作った issue" in spec_format

    def test_spec_format_forbids_extra_sections_in_spec_body(self, spec_format):
        assert "以外を書かない" in spec_format
