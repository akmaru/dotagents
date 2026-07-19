# dotagents

Personal AI agent skills managed as an [APM](https://github.com/microsoft/apm) marketplace.

## Skills

| Skill | Description |
|-------|-------------|
| [grill-me](packages/grill-me/.apm/skills/grill-me/SKILL.md) | Interview the user relentlessly about a plan or design until reaching shared understanding |
| [beads](packages/beads/.apm/skills/beads/SKILL.md) | Beads issue tracking workflow — create/update/close issues around every task |
| [rust](packages/rust/.apm/skills/rust/SKILL.md) | Rust development workflow with rust-analyzer LSP integration |
| [skill-creator](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator) | Create new skills, improve existing skills, and measure skill performance |

## Usage

### Install via APM marketplace

```bash
apm marketplace add akmaru/dotagents
apm install grill-me@dotagents
```

### User scope (全プロジェクトで使用)

```bash
apm install -g grill-me@dotagents
```

### Project scope (特定プロジェクトのみ)

```bash
apm install grill-me@dotagents
```

## User-level agent config (`user/`)

`user/` holds personal user-scope config shared across agents (Claude Code / OpenCode). It is **not** an
APM package and is not listed in the marketplace — it is distributed by native symlink instead of `apm compile`
(see [docs/adr/0004](docs/adr/0004-user-config-distribution-symlink-import.md)).

```
user/
├── AGENTS.md      # canonical cross-agent global prompt
├── CLAUDE.md      # @import AGENTS.md + Claude-specific additions (work import)
├── settings.json  # Claude Code settings
├── rules/         # Claude-only, path-scoped rules (recursive, paths: frontmatter)
└── install.sh     # symlinks the above into ~/.claude and ~/.config/opencode
```

- `AGENTS.md` is the single source of truth. `CLAUDE.md` imports it so Claude and OpenCode read the same
  content without duplication ([docs/adr/0005](docs/adr/0005-agents-md-canonical.md)).
- `paths:`-scoped rules are Claude-only; OpenCode has no equivalent mechanism
  ([docs/adr/0006](docs/adr/0006-file-scoped-rules-claude-only.md)).

Install:

```bash
user/install.sh
```

## Adding a skill

1. Create the package under `packages/<name>/` with the skill at `.apm/skills/<name>/SKILL.md`,
   following the [agentskills.io spec](https://agentskills.io/specification):

```markdown
---
name: <name>
description: <what it does and when to use it, max 1024 chars>
---

## Instructions
...
```

2. Add a package manifest `packages/<name>/apm.yml`:

```yaml
name: <name>
version: 0.1.0
description: <short description>
author: akmaru
license: MIT
includes: auto
dependencies:
  apm: []
  mcp: []
```

3. Register the package in the root `apm.yml` `marketplace.packages` block:

```yaml
marketplace:
  packages:
    - name: <name>
      source: ./packages/<name>
```

4. Regenerate the marketplace index, then add the skill to the tables in this README and `CLAUDE.md`:

```bash
apm pack
```

## Development

Dev tools (pytest / pyyaml / pre-commit) are managed by [uv](https://docs.astral.sh/uv/) and stay
project-local — no global installs required.

```bash
uv sync                    # provision dev tools into .venv
uv run pre-commit install  # enable the pre-commit hooks
uv run pytest tests/ -v
```

The pre-commit hook runs `apm pack --check-clean` to verify the checked-in
`.claude-plugin/marketplace.json` matches `apm.yml` (see [docs/adr/0003](docs/adr/0003-marketplace-source-of-truth.md)),
so it requires `apm` on `PATH`. Tests run automatically on push and pull requests via GitHub Actions.
