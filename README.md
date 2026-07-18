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

```bash
pip install pyyaml pytest
pytest tests/ -v
```

Tests run automatically on push and pull requests via GitHub Actions.
