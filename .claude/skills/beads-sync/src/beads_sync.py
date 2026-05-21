#!/usr/bin/env python3
"""Sync beads issues to GitHub or GitLab Issues."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY_LABELS = {
    0: "priority:critical",
    1: "priority:high",
    2: "priority:medium",
    3: "priority:low",
    4: "priority:backlog",
}

STATUS_IN_PROGRESS_LABEL = "status:in-progress"

BEADS_ID_PATTERN = re.compile(r"<!--\s*beads-id:\s*(\S+)\s*-->")

CONFIG_FILE = ".beads/sync_config.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=capture, text=True, check=check)


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_repo_root() -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], check=False)
    if result.returncode != 0:
        die("not inside a git repository")
    return Path(result.stdout.strip())


def load_config(root: Path) -> dict:
    path = root / CONFIG_FILE
    if not path.exists():
        die(f"{CONFIG_FILE} not found. Run `beads-sync setup` first.")
    with path.open() as f:
        return yaml.safe_load(f)


def save_config(root: Path, config: dict) -> None:
    path = root / CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def get_remote_url(remote: str = "origin") -> str:
    result = run(["git", "remote", "get-url", remote], check=False)
    if result.returncode != 0:
        die(f"cannot get URL for remote '{remote}'")
    return result.stdout.strip()


def get_glab_hosts() -> list[str]:
    result = run(["glab", "config", "get", "--global", "host"], check=False)
    if result.returncode != 0:
        return []
    return [h.strip() for h in result.stdout.strip().splitlines() if h.strip()]


def detect_platform(url: str, glab_hosts: list[str]) -> str:
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    for host in glab_hosts:
        if host and host in url:
            return "gitlab"
    die(
        f"cannot detect platform from URL: {url}\n"
        "Use --platform github|gitlab to specify explicitly."
    )


def extract_repo_slug(url: str) -> str:
    """Extract owner/repo (or group/project) from a git remote URL."""
    match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    if not match:
        die(f"cannot extract repo slug from URL: {url}")
    return match.group(1)


def beads_marker(beads_id: str) -> str:
    return f"<!-- beads-id: {beads_id} -->"


def build_body(description: str, beads_id: str, deps: list[dict], remote_issues_map: dict) -> str:
    """Build issue body with beads marker and dependency section."""
    body_parts = [description or ""]

    if deps:
        # deps from br show: this issue is blocked by dep["id"]
        blocked_by_ids = [d["id"] for d in deps if d.get("dependency_type") == "blocks"]

        dep_lines = []
        if blocked_by_ids:
            nums = [f"#{remote_issues_map[i]}" for i in blocked_by_ids if i in remote_issues_map]
            if nums:
                dep_lines.append(f"**Blocked by:** {', '.join(nums)}")

        if dep_lines:
            body_parts.append("\n## Dependencies\n" + "\n".join(dep_lines))

    body_parts.append(f"\n{beads_marker(beads_id)}")
    return "\n".join(body_parts)


def get_beads_issues() -> list[dict]:
    result = run(
        ["br", "list", "--json",
         "--status", "open", "--status", "in_progress", "--status", "closed"],
        check=False,
    )
    if result.returncode != 0:
        # also try deleted (tombstone) issues if supported
        result = run(["br", "list", "--json",
                      "--status", "open", "--status", "in_progress", "--status", "closed"],
                     check=False)
    if result.returncode != 0:
        die(f"br list failed: {result.stderr}")
    data = json.loads(result.stdout)
    return data.get("issues", [])


def get_issue_dependencies(beads_id: str) -> list[dict]:
    """Return list of dependency objects for the given issue.

    Each object has: id (the blocking issue), dependency_type.
    Semantics: this issue is blocked by each dep["id"].
    """
    result = run(["br", "show", beads_id, "--json"], check=False)
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
        if isinstance(data, list):
            data = data[0] if data else {}
        return data.get("dependencies", [])
    except (json.JSONDecodeError, IndexError):
        return []


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------


def gh_run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return run(["gh"] + args, **kwargs)


def github_get_all_issues(repo: str) -> list[dict]:
    """Fetch all issues (open + closed) from GitHub with body included."""
    result = gh_run([
        "issue", "list",
        "--repo", repo,
        "--state", "all",
        "--limit", "1000",
        "--json", "number,title,body,state,labels",
    ])
    return json.loads(result.stdout)


def github_ensure_labels(repo: str, labels: list[str], dry_run: bool) -> None:
    existing_result = gh_run(["label", "list", "--repo", repo, "--json", "name", "--limit", "500"])
    existing = {l["name"] for l in json.loads(existing_result.stdout)}
    for label in labels:
        if label not in existing:
            if dry_run:
                print(f"  [dry-run] would create label: {label}")
            else:
                gh_run(["label", "create", "--repo", repo, label, "--color", "ededed"])
                print(f"  created label: {label}")


def github_get_node_id(repo: str, number: int) -> str:
    result = gh_run([
        "api", f"repos/{repo}/issues/{number}",
        "--jq", ".node_id",
    ])
    return result.stdout.strip()


def github_add_blocked_by(issue_node_id: str, blocking_node_id: str) -> None:
    query = """
mutation($issueId: ID!, $blockingIssueId: ID!) {
  addBlockedBy(input: {issueId: $issueId, blockingIssueId: $blockingIssueId}) {
    issue { number }
  }
}
"""
    gh_run([
        "api", "graphql",
        "-f", f"query={query}",
        "-f", f"issueId={issue_node_id}",
        "-f", f"blockingIssueId={blocking_node_id}",
    ], check=False)


def github_remove_blocked_by(issue_node_id: str, blocking_node_id: str) -> None:
    query = """
mutation($issueId: ID!, $blockingIssueId: ID!) {
  removeBlockedBy(input: {issueId: $issueId, blockingIssueId: $blockingIssueId}) {
    issue { number }
  }
}
"""
    gh_run([
        "api", "graphql",
        "-f", f"query={query}",
        "-f", f"issueId={issue_node_id}",
        "-f", f"blockingIssueId={blocking_node_id}",
    ], check=False)


def sync_to_github(issues: list[dict], repo: str, dry_run: bool) -> None:
    print(f"Syncing {len(issues)} issues to GitHub ({repo})...")

    remote_issues = github_get_all_issues(repo)
    # beads_id → {number, state}
    remote_map: dict[str, dict] = {}
    for ri in remote_issues:
        m = BEADS_ID_PATTERN.search(ri.get("body") or "")
        if m:
            remote_map[m.group(1)] = {"number": ri["number"], "state": ri["state"].lower()}

    # Collect all labels needed
    all_labels: set[str] = set()
    for issue in issues:
        p = issue.get("priority")
        if p is not None and p in PRIORITY_LABELS:
            all_labels.add(PRIORITY_LABELS[p])
        t = issue.get("issue_type")
        if t:
            all_labels.add(f"type:{t}")
        if issue.get("status") == "in_progress":
            all_labels.add(STATUS_IN_PROGRESS_LABEL)

    if not dry_run:
        github_ensure_labels(repo, sorted(all_labels), dry_run=False)
    else:
        for label in sorted(all_labels):
            print(f"  [dry-run] would ensure label: {label}")

    # First pass: create/update issues (no dep links yet)
    beads_to_remote_number: dict[str, int] = {
        bid: info["number"] for bid, info in remote_map.items()
    }

    for issue in issues:
        bid = issue["id"]
        title = issue["title"]
        status = issue.get("status", "open")
        labels = []
        p = issue.get("priority")
        if p is not None and p in PRIORITY_LABELS:
            labels.append(PRIORITY_LABELS[p])
        t = issue.get("issue_type")
        if t:
            labels.append(f"type:{t}")
        if status == "in_progress":
            labels.append(STATUS_IN_PROGRESS_LABEL)

        deps = get_issue_dependencies(bid)
        body = build_body(issue.get("description", ""), bid, deps, beads_to_remote_number)

        if bid not in remote_map:
            if dry_run:
                print(f"  [dry-run] would create: {title!r}")
            else:
                create_args = [
                    "issue", "create",
                    "--repo", repo,
                    "--title", title,
                    "--body", body,
                ]
                for label in labels:
                    create_args += ["--label", label]
                result = gh_run(create_args)
                # extract issue number from URL
                url = result.stdout.strip()
                number = int(url.rstrip("/").split("/")[-1])
                beads_to_remote_number[bid] = number
                remote_map[bid] = {"number": number, "state": "open"}
                print(f"  created #{number}: {title!r}")
        else:
            info = remote_map[bid]
            number = info["number"]
            current_state = info["state"]
            should_be_closed = status in ("closed", "deleted")

            if dry_run:
                print(f"  [dry-run] would update #{number}: {title!r}")
                if should_be_closed and current_state == "open":
                    print(f"  [dry-run] would close #{number}")
            else:
                edit_args = [
                    "issue", "edit", str(number),
                    "--repo", repo,
                    "--title", title,
                    "--body", body,
                ]
                # Replace labels entirely
                edit_args += ["--add-label", ",".join(labels)] if labels else []
                gh_run(edit_args)
                print(f"  updated #{number}: {title!r}")

                if should_be_closed and current_state == "open":
                    gh_run(["issue", "close", str(number), "--repo", repo])
                    print(f"  closed #{number}")
                elif not should_be_closed and current_state == "closed":
                    gh_run(["issue", "reopen", str(number), "--repo", repo])
                    print(f"  reopened #{number}")

    # Second pass: sync dependency links
    if not dry_run:
        for issue in issues:
            bid = issue["id"]
            if bid not in beads_to_remote_number:
                continue
            issue_number = beads_to_remote_number[bid]
            issue_node_id = github_get_node_id(repo, issue_number)

            deps = get_issue_dependencies(bid)
            for dep in deps:
                # dep["id"] is the issue that blocks this issue
                dep_bid = dep["id"]
                if dep_bid not in beads_to_remote_number:
                    continue
                dep_number = beads_to_remote_number[dep_bid]
                dep_node_id = github_get_node_id(repo, dep_number)
                # this issue is blocked by dep
                github_add_blocked_by(issue_node_id, dep_node_id)
                print(f"  linked: #{issue_number} blocked by #{dep_number}")

    print("GitHub sync complete.")


# ---------------------------------------------------------------------------
# GitLab helpers
# ---------------------------------------------------------------------------


_gitlab_hostname: str = "gitlab.com"


def set_gitlab_hostname(hostname: str) -> None:
    global _gitlab_hostname
    _gitlab_hostname = hostname


def glab_run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    return run(["glab", "--hostname", _gitlab_hostname] + args, **kwargs)


def gitlab_get_all_issues(repo: str) -> list[dict]:
    """Fetch all issues from GitLab project."""
    encoded = repo.replace("/", "%2F")
    all_issues: list[dict] = []
    page = 1
    while True:
        result = glab_run([
            "api", f"projects/{encoded}/issues?state=all&per_page=100&page={page}",
        ])
        batch = json.loads(result.stdout)
        if not batch:
            break
        all_issues.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return all_issues


def gitlab_ensure_labels(repo: str, labels: list[str], dry_run: bool) -> None:
    encoded = repo.replace("/", "%2F")
    result = glab_run(["api", f"projects/{encoded}/labels?per_page=100"])
    existing = {l["name"] for l in json.loads(result.stdout)}
    for label in labels:
        if label not in existing:
            if dry_run:
                print(f"  [dry-run] would create label: {label}")
            else:
                glab_run([
                    "api", "--method", "POST",
                    f"projects/{encoded}/labels",
                    "-f", f"name={label}",
                    "-f", "color=#ededed",
                ])
                print(f"  created label: {label}")


def sync_to_gitlab(issues: list[dict], repo: str, dry_run: bool) -> None:
    print(f"Syncing {len(issues)} issues to GitLab ({repo})...")

    remote_issues = gitlab_get_all_issues(repo)
    remote_map: dict[str, dict] = {}
    for ri in remote_issues:
        body = ri.get("description") or ""
        m = BEADS_ID_PATTERN.search(body)
        if m:
            remote_map[m.group(1)] = {"iid": ri["iid"], "state": ri["state"]}

    # Collect all labels needed
    all_labels: set[str] = set()
    for issue in issues:
        p = issue.get("priority")
        if p is not None and p in PRIORITY_LABELS:
            all_labels.add(PRIORITY_LABELS[p])
        t = issue.get("issue_type")
        if t:
            all_labels.add(f"type:{t}")

    if not dry_run:
        gitlab_ensure_labels(repo, sorted(all_labels), dry_run=False)
    else:
        for label in sorted(all_labels):
            print(f"  [dry-run] would ensure label: {label}")

    beads_to_remote_iid: dict[str, int] = {
        bid: info["iid"] for bid, info in remote_map.items()
    }
    encoded_repo = repo.replace("/", "%2F")

    for issue in issues:
        bid = issue["id"]
        title = issue["title"]
        status = issue.get("status", "open")
        labels = []
        p = issue.get("priority")
        if p is not None and p in PRIORITY_LABELS:
            labels.append(PRIORITY_LABELS[p])
        t = issue.get("issue_type")
        if t:
            labels.append(f"type:{t}")

        deps = get_issue_dependencies(bid)
        body = build_body(issue.get("description", ""), bid, deps, {
            b: str(i) for b, i in beads_to_remote_iid.items()
        })

        if bid not in remote_map:
            if dry_run:
                print(f"  [dry-run] would create: {title!r}")
            else:
                create_fields = [
                    "-f", f"title={title}",
                    "-f", f"description={body}",
                ]
                if labels:
                    create_fields += ["-f", f"labels={','.join(labels)}"]
                result = glab_run([
                    "api", "--method", "POST",
                    f"projects/{encoded_repo}/issues",
                ] + create_fields)
                created = json.loads(result.stdout)
                iid = created["iid"]
                beads_to_remote_iid[bid] = iid
                remote_map[bid] = {"iid": iid, "state": "opened"}
                print(f"  created !{iid}: {title!r}")
        else:
            info = remote_map[bid]
            iid = info["iid"]
            current_state = info["state"]
            should_be_closed = status in ("closed", "deleted")

            if dry_run:
                print(f"  [dry-run] would update !{iid}: {title!r}")
                if should_be_closed and current_state == "opened":
                    print(f"  [dry-run] would close !{iid}")
            else:
                update_fields = [
                    "-f", f"title={title}",
                    "-f", f"description={body}",
                ]
                if labels:
                    update_fields += ["-f", f"labels={','.join(labels)}"]
                # Set issue_status for in_progress
                if status == "in_progress":
                    update_fields += ["-f", "issue_status=in_progress"]
                elif status == "open":
                    update_fields += ["-f", "issue_status=open"]

                glab_run([
                    "api", "--method", "PUT",
                    f"projects/{encoded_repo}/issues/{iid}",
                ] + update_fields)
                print(f"  updated !{iid}: {title!r}")

                if should_be_closed and current_state == "opened":
                    glab_run([
                        "api", "--method", "PUT",
                        f"projects/{encoded_repo}/issues/{iid}",
                        "-f", "state_event=close",
                    ])
                    print(f"  closed !{iid}")
                elif not should_be_closed and current_state == "closed":
                    glab_run([
                        "api", "--method", "PUT",
                        f"projects/{encoded_repo}/issues/{iid}",
                        "-f", "state_event=reopen",
                    ])
                    print(f"  reopened !{iid}")

    # Second pass: sync dependency links
    if not dry_run:
        # Get project ID for target_project_id field
        proj_result = glab_run(["api", f"projects/{encoded_repo}"])
        project_id = json.loads(proj_result.stdout)["id"]

        for issue in issues:
            bid = issue["id"]
            if bid not in beads_to_remote_iid:
                continue
            iid = beads_to_remote_iid[bid]
            deps = get_issue_dependencies(bid)
            for dep in deps:
                dep_bid = dep["id"]
                if dep_bid not in beads_to_remote_iid:
                    continue
                dep_iid = beads_to_remote_iid[dep_bid]
                # Try is_blocked_by first (Premium+), fall back to relates_to (Free)
                for link_type in ("is_blocked_by", "relates_to"):
                    result = glab_run([
                        "api", "--method", "POST",
                        f"projects/{encoded_repo}/issues/{iid}/links",
                        "-f", f"target_project_id={project_id}",
                        "-f", f"target_issue_iid={dep_iid}",
                        "-f", f"link_type={link_type}",
                    ], check=False)
                    if result.returncode == 0:
                        print(f"  linked: !{iid} {link_type} !{dep_iid}")
                        break

    print("GitLab sync complete.")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_setup(args: argparse.Namespace) -> None:
    root = find_repo_root()

    # Determine remote URL
    remote_url = args.remote_url or get_remote_url()

    # Determine platform
    if args.platform:
        platform = args.platform
    else:
        platform = detect_platform(remote_url, get_glab_hosts())

    # Extract repo slug
    repo = extract_repo_slug(remote_url)

    print(f"Platform : {platform}")
    print(f"Repo     : {repo}")
    print(f"Remote   : {remote_url}")

    # Verify auth
    if platform == "github":
        result = run(["gh", "auth", "status"], check=False)
        if result.returncode != 0:
            die("gh auth check failed. Run `gh auth login` first.")
        print("GitHub auth: OK")
    else:
        # Extract hostname from URL for targeted auth check
        import urllib.parse
        parsed = urllib.parse.urlparse(remote_url if "://" in remote_url else f"https://{remote_url}")
        hostname = parsed.hostname or "gitlab.com"
        result = run(["glab", "auth", "status", "--hostname", hostname], check=False)
        if result.returncode != 0:
            die(f"glab auth check failed for {hostname}. Run `glab auth login --hostname {hostname}` first.")
        print(f"GitLab auth ({hostname}): OK")

    config = {"platform": platform, "repo": repo, "remote_url": remote_url}
    save_config(root, config)
    print(f"Config saved to {CONFIG_FILE}")


def _hostname_from_url(url: str) -> str:
    import urllib.parse
    parsed = urllib.parse.urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or "gitlab.com"


def cmd_sync(args: argparse.Namespace) -> None:
    root = find_repo_root()
    config = load_config(root)

    platform = config["platform"]
    repo = config["repo"]
    dry_run = args.dry_run

    if platform == "gitlab":
        set_gitlab_hostname(_hostname_from_url(config.get("remote_url", "")))

    if dry_run:
        print("[dry-run mode] no changes will be made")

    issues = get_beads_issues()
    if not issues:
        print("No beads issues found.")
        return

    if platform == "github":
        sync_to_github(issues, repo, dry_run)
    elif platform == "gitlab":
        sync_to_gitlab(issues, repo, dry_run)
    else:
        die(f"Unknown platform: {platform}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="beads-sync",
        description="Sync beads issues to GitHub or GitLab Issues",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # setup
    p_setup = sub.add_parser("setup", help="Configure and verify connection (run once per repo)")
    p_setup.add_argument("--platform", choices=["github", "gitlab"],
                         help="Force platform (overrides auto-detection)")
    p_setup.add_argument("--remote-url", help="Override git remote URL for platform detection")

    # sync
    p_sync = sub.add_parser("sync", help="Sync beads issues to the configured platform")
    p_sync.add_argument("--dry-run", action="store_true",
                        help="Show what would change without making any changes")
    p_sync.add_argument("--quiet", action="store_true", help="Suppress non-error output")

    args = parser.parse_args()

    if args.command == "setup":
        cmd_setup(args)
    elif args.command == "sync":
        if getattr(args, "quiet", False):
            sys.stdout = open("/dev/null", "w")
        cmd_sync(args)


if __name__ == "__main__":
    main()
