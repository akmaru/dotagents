---
name: beads
description: Beads issue tracking workflow for Claude Code. When this skill is installed, beads is the issue tracker for this project. Always create a beads issue before starting any task, update it during work, and close it on completion.
compatibility: Designed for Claude Code
---

## Workflow

This skill being installed means **beads is the issue tracker for this project**. Follow this workflow for every task:

1. **Task start**: Create a beads issue with `br create --label=beads` before doing any work
2. **In progress**: Update the issue to `in_progress` with `br update <id> --status=in_progress`
3. **Task end**: Close the issue with `br close <id>` and sync with `br sync --flush-only`

Never start implementation without a corresponding beads issue.

## Commands

```bash
# View actionable work
br ready

# Create an issue (always add the "beads" label)
br create --title="..." --description="..." --type=task --priority=2 --label=beads

# Update status
br update <id> --status=in_progress

# Close
br close <id> --reason="..."

# Sync to git
br sync --flush-only
```

## Issue types

`task`, `bug`, `feature`, `epic`, `chore`, `docs`, `question`

## Priority

`0`=critical, `1`=high, `2`=medium, `3`=low, `4`=backlog
