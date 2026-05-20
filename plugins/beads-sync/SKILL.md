---
name: beads-sync
description: Sync beads issues to GitHub or GitLab Issues for human-readable visibility. Run `beads-sync setup` once per repository, then `beads-sync sync` to push all beads issues to the configured platform. Automatically triggered after br update/close/create via PostToolUse hook.
compatibility: Designed for Claude Code
---

## Prerequisite: CLI install

Before using this skill, verify `beads-sync` is available:

```bash
beads-sync --version
```

If the command is not found, install it. Find the installed package path and run:

```bash
uv tool install <path-to-beads-sync>
# e.g. uv tool install ~/.apm/packages/akmaru/dotagents/beads-sync
# or from this repo:  uv tool install ./plugins/beads-sync
```

Alternatively, if installed via APM:

```bash
apm run install  # runs: uv tool install . from the package directory
```

## Setup (run once per repository)

```bash
beads-sync setup                                    # auto-detect from git remote
beads-sync setup --platform gitlab                  # force GitLab
beads-sync setup --remote-url https://host/org/repo # specify URL explicitly
```

This detects the platform (GitHub or GitLab) from the git remote URL, verifies CLI auth, and saves `.beads/sync_config.yaml`.

## Sync

```bash
beads-sync sync           # sync all beads issues to GitHub/GitLab
beads-sync sync --dry-run # preview changes without writing
```

## When to run

- After `beads-sync setup` (initial population)
- After any `br update`, `br close`, `br create`, or `br reopen` (automated via hook)
- At session end alongside `br sync --flush-only`

## Field mapping

| beads | GitHub | GitLab |
|---|---|---|
| title | title | title |
| description | body | description |
| status: open | open | opened |
| status: in_progress | open + label `status:in-progress` | open + issue_status: in_progress |
| status: closed/deleted | closed | closed |
| priority (0-4) | label `priority:critical/high/medium/low/backlog` | same |
| issue_type | label `type:<value>` | same |
| dependencies | GraphQL addBlockedBy (or body text) | relates_to link (is_blocked_by requires Premium) |

## Notes

- beads is single source of truth — do not edit GitHub/GitLab issues directly
- Labels are auto-created on first sync
- The `<!-- beads-id: <id> -->` marker in issue body tracks correspondence
