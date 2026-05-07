# dotagents

Personal AI agent skills managed as an [APM](https://github.com/microsoft/apm) marketplace.

## Skills

| Skill | Description |
|-------|-------------|
| [grill-me](skills/grill-me/SKILL.md) | Interview the user relentlessly about a plan or design until reaching shared understanding |

## Usage

### Install via APM marketplace

```bash
apm marketplace add akmaru/dotagents
apm install grill-me@dotagents
```

### Add as APM dependency

```yaml
# apm.yml
dependencies:
  apm:
    - akmaru/dotagents/skills/grill-me
```

## Adding a skill

1. Create `skills/<name>/SKILL.md` following the [agentskills.io spec](https://agentskills.io/specification):

```markdown
---
name: <name>
description: <what it does and when to use it, max 1024 chars>
---

## Instructions
...
```

2. Add an entry to the `marketplace.plugins` block in `apm.yml`:

```yaml
marketplace:
  plugins:
    - name: <name>
      source: ./skills/<name>
      description: <short description>
```

3. Update `.claude-plugin/marketplace.json` to match (or run `apm pack` if you have the CLI).

4. Add the skill to the table in this README and in `CLAUDE.md`.

## Development

```bash
pip install pyyaml pytest
pytest tests/ -v
```

Tests run automatically on push and pull requests via GitHub Actions.
