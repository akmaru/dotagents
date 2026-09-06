# MCP Config Sync Tool

Centrally manage MCP server configuration across Claude Code, VS Code (GitHub Copilot), and GitLab Duo.

## How It Works

```
~/.config/mcp/master-mcp.json        ← ★ Base configuration (personal)
~/.config/mcp/master-mcp.d/*.json    ← ★ Additional configs (work, etc.)
         │
         │  (merged in alphabetical order)
         │
         ├──→ ~/.claude.json                               (Claude Code user config)
         ├──→ ~/Library/.../Claude/claude_desktop_config.json  (Claude Desktop config, macOS only)
         ├──→ ~/Library/.../Code/User/mcp.json             (VS Code user config)
         └──→ ~/.gitlab/duo/mcp.json                       (GitLab Duo user config)
```

Each tool uses a slightly different JSON format. The script handles the conversion automatically:

| Tool              | Root Key     | Config File Location                                 | Platform |
| ----------------- | ------------ | ---------------------------------------------------- | -------- |
| Claude Code       | `mcpServers` | `~/.claude.json`                                     | All      |
| Claude Desktop    | `mcpServers` | `~/Library/.../Claude/claude_desktop_config.json`    | macOS    |
| VS Code / Copilot | `servers`    | `~/Library/.../Code/User/mcp.json`                   | macOS    |
| GitLab Duo        | `mcpServers` | `~/.gitlab/duo/mcp.json`                             | All      |

## Setup

### 1. Prerequisites

```bash
# jq is required
brew install jq        # macOS
# sudo apt install jq  # Ubuntu
```

### 2. Install

```bash
# Place the script
mkdir -p ~/.config/mcp
cp sync-mcp.sh ~/.config/mcp/
chmod +x ~/.config/mcp/sync-mcp.sh

# Optional: add an alias
echo 'alias mcp-sync="~/.config/mcp/sync-mcp.sh"' >> ~/.bashrc
# or ~/.zshrc
```

### 3. Edit the Master Config

```bash
# First run creates a template automatically
~/.config/mcp/sync-mcp.sh

# Edit the master config
$EDITOR ~/.config/mcp/master-mcp.json
```

### 4. (Optional) Add Work-Specific Configs

Create additional configs in `master-mcp.d/`:

```bash
# Create directory
mkdir -p ~/.config/mcp/master-mcp.d

# Add work config (managed by work repo)
# Example: symlink from work dotfiles repo
ln -s ~/work-dotfiles/mcp/work.json ~/.config/mcp/master-mcp.d/work.json

# Or create directly
cat > ~/.config/mcp/master-mcp.d/work.json <<'EOF'
{
  "servers": {
    "work-gitlab": {
      "type": "http",
      "url": "https://gitlab.company.com/api/v4/mcp"
    }
  }
}
EOF
```

### 5. Sync

```bash
# Sync to all tools
mcp-sync all

# Sync individually
mcp-sync claude    # Claude Code only
mcp-sync desktop   # Claude Desktop only (macOS)
mcp-sync vscode    # VS Code only
mcp-sync gitlab    # GitLab Duo only

# Sync to a specific project (generates project-level configs)
mcp-sync project ~/projects/my-app
```

## Master Config Format

### Base Configuration (`master-mcp.json`)

```json
{
  "servers": {
    "GitLab": {
      "type": "http",
      "url": "https://gitlab.com/api/v4/mcp",
      "_comment": "Comments are stripped during sync"
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE": "/Users/you/.config/mcp/shared-memory.json"
      }
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_GITHUB_PAT"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/you/projects"]
    }
  }
}
```

### Include Pattern (SSH Config style)

Similar to SSH Config's `Include` directive, you can split configurations into separate files:

```bash
~/.config/mcp/
├── master-mcp.json          # Personal base config (managed by dotagents)
└── master-mcp.d/            # Additional configs (work, etc.)
    └── work.json            # Work-specific servers (managed by work repo)
```

**Personal config** (`master-mcp.json`):
```json
{
  "servers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"],
      "env": {
        "MEMORY_FILE": "${HOME}/.config/mcp/shared-memory.json"
      },
      "_comment": "No need to specify PATH - it's automatically added during sync"
    },
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp",
      "headers": {
        "Authorization": "Bearer ${GITHUB_TOKEN}"
      }
    }
  }
}
```

Note: The sync script automatically:
- Resolves `npx` to `/Users/you/.local/share/mise/shims/npx`
- Adds `env.PATH` with your shell's PATH from .zshrc/.bashrc

**Work config** (`master-mcp.d/work.json`):
```json
{
  "servers": {
    "work-gitlab": {
      "type": "http",
      "url": "https://gitlab.company.com/api/v4/mcp"
    },
    "work-jira": {
      "command": "npx",
      "args": ["-y", "@company/mcp-jira"],
      "env": {
        "JIRA_URL": "https://company.atlassian.net",
        "JIRA_TOKEN": "${JIRA_TOKEN}"
      }
    }
  }
}
```

**Merge behavior:**
- Files in `master-mcp.d/` are processed in **alphabetical order**
- **Complete replacement**: When a server name appears in multiple configs, the later config **completely replaces** the earlier one (not shallow merge)
- Example: If `master-mcp.json` defines `GitLab` with `type: "http"`, and `master-mcp.d/work.json` defines `GitLab` with `command: "npx"`, the final result will **only** have `command: "npx"` (no leftover `type` or `url` fields)
- Personal repo manages `master-mcp.json`, work repo manages `master-mcp.d/work.json`
- Add `master-mcp.d/` to personal repo's `.gitignore` to keep work configs separate

### Server Definition Formats

**HTTP transport (remote servers):**
```json
{
  "type": "http",
  "url": "https://example.com/mcp",
  "headers": { "Authorization": "Bearer TOKEN" }
}
```

**stdio transport (local servers):**
```json
{
  "command": "npx",
  "args": ["-y", "package-name"],
  "env": { "API_KEY": "value" }
}
```

## Automatic Path Resolution and PATH Injection

The sync script automatically:
1. **Resolves command paths**: `"command": "npx"` → `/Users/you/.local/share/mise/shims/npx`
2. **Adds PATH to all servers**: Injects your shell's PATH (from .zshrc/.bashrc) into `env.PATH`

This means you can write simple configs in `master-mcp.json`:

```json
{
  "servers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

And it automatically becomes:

```json
{
  "memory": {
    "command": "/Users/you/.local/share/mise/shims/npx",
    "args": ["-y", "@modelcontextprotocol/server-memory"],
    "env": {
      "PATH": "/Users/you/.local/share/mise/shims:/usr/local/bin:/usr/bin:/bin:..."
    }
  }
}
```

**Path resolution priority:**
1. If `command` is already an absolute path, it's used as-is
2. Check mise shims directory (`~/.local/share/mise/shims/`)
3. Search in shell PATH (from .zshrc/.bashrc)
4. Fallback to original command if not found

## Testing

Run the test suite to verify the sync script works correctly:

```bash
./test/test_mcp_sync.sh
```

Tests include:
- Basic sync functionality (Claude Code, VS Code, GitLab Duo)
- Command path resolution (`npx` → `/bin/echo`)
- PATH injection to all servers
- Include pattern (`master-mcp.d/*.json`)
- Complete replacement (not shallow merge)
- Preservation of existing env fields
- Tool-specific key names (`mcpServers` vs `servers`)
- Sync to all tools at once

The test suite creates an isolated environment and does not modify your actual config files.

Tests are automatically run on GitHub Actions for Ubuntu 24.04 and 26.04.

## Notes

- **Backups**: Existing config files are automatically backed up before overwriting (`.bak.TIMESTAMP`)
- **Merge behavior**: For Claude Code's `~/.claude.json` and Claude Desktop's `claude_desktop_config.json`, only the `mcpServers` key is overwritten; other keys (preferences, theme, etc.) are preserved
- **Claude Desktop**: Currently only supported on macOS. The app must be restarted after syncing for changes to take effect
- **Authentication**: GitLab MCP Server triggers OAuth in the browser on first connection. This is required once per tool.
- **Restart required**: Restart each tool after syncing for changes to take effect
- **VS Code paths**: Paths differ between Linux/macOS/Windows. The script auto-detects macOS and Linux. For WSL, adjust `VSCODE_MCP_CONFIG` in the script.

## Project-Level Sync and .gitignore

When syncing to a project, be careful not to commit configs containing secrets:

```gitignore
# MCP configs (may contain secrets)
.mcp.json
.vscode/mcp.json
.gitlab/duo/mcp.json
```

To share configs with your team without exposing secrets, use environment variables:

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp",
      "headers": {
        "Authorization": "Bearer ${GITHUB_TOKEN}"
      }
    }
  }
}
```

> **Note**: Environment variable expansion (`${VAR}`) is supported by Claude Code and VS Code.
> Support in GitLab Duo may vary — check the latest docs.
