"""project-layout の layout.json が定める標準構成のうち、無いファイルだけを作る。

既存のファイルは上書きしない。結果は JSON（created / existing / warnings）で標準出力に出す。
テンプレートは ../templates/<layout.json の id> にある（ドットで始まる名前にすると dotagents の中で
.gitignore などとして効いてしまうため、id を名前にしている）。
"""

import argparse
import datetime
import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATES = SKILL_DIR / "templates"
# インストール後、依存の project-layout は同じ skills/ の隣に入る（docs/adr/0025）。
DEFAULT_LAYOUT = SKILL_DIR.parent / "project-layout" / "layout.json"

ADR_FILE = re.compile(r"^\d{4}-.+\.md$")


def plan(layout: dict, adr_dir: str, hosting: str, optional: list[str], target: Path) -> dict[str, str]:
    files = {}
    for entry in layout["baseline"]:
        dest = entry["path"]
        if dest.startswith("{adr_dir}/"):
            existing_adr = target / adr_dir
            if existing_adr.is_dir() and any(ADR_FILE.match(p.name) for p in existing_adr.iterdir()):
                continue  # ADR があるリポジトリに 0001 を足すと採番が衝突する
            dest = dest.format(adr_dir=adr_dir)
        files[dest] = entry["id"]
    for key in optional:
        files[layout["optional"][key]["path"][hosting]] = key
    return files


def render(template_id: str, values: dict[str, str]) -> str:
    text = (TEMPLATES / template_id).read_text()
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default=".")
    parser.add_argument("--layout", default=str(DEFAULT_LAYOUT))
    parser.add_argument("--hosting", choices=["github", "gitlab"], required=True)
    parser.add_argument("--with", dest="optional", default="", help="layout.json の optional のキーをカンマ区切りで")
    parser.add_argument("--adr-dir")
    parser.add_argument("--name", required=True)
    parser.add_argument("--holder", required=True)
    parser.add_argument("--year", default=str(datetime.date.today().year))
    args = parser.parse_args()

    layout_path = Path(args.layout)
    if not layout_path.is_file():
        parser.error(f"layout.json が見つからない: {layout_path}（project-layout を一緒にインストールする）")
    layout = json.loads(layout_path.read_text())

    target = Path(args.target)
    adr_dir = (args.adr_dir or layout["adr"]["default"]).strip("/")
    optional = [k for k in args.optional.split(",") if k]
    unknown = sorted(set(optional) - set(layout["optional"]))
    if unknown:
        parser.error(f"--with に未知のキー: {unknown}")
    values = {
        "name": args.name,
        "holder": args.holder,
        "year": args.year,
        "adr_dir": adr_dir,
        "date": datetime.date.today().isoformat(),
    }

    report = {"created": [], "existing": [], "warnings": []}
    for dest, template_id in plan(layout, adr_dir, args.hosting, optional, target).items():
        path = target / dest
        if path.exists():
            report["existing"].append(dest)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(template_id, values))
        report["created"].append(dest)

    if "AGENTS.md" in report["existing"] and "置き場の規約" not in (target / "AGENTS.md").read_text():
        report["warnings"].append("AGENTS.md に「置き場の規約」節が無い")
    if "CLAUDE.md" in report["existing"] and "@AGENTS.md" not in (target / "CLAUDE.md").read_text():
        report["warnings"].append("CLAUDE.md が @AGENTS.md を読み込んでいない")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
