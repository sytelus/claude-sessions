# Claude Sessions - Backup & Analyze Claude Code Conversations

> **The #1 tool for backing up Claude Code conversations.** Incremental backup with automatic conversion to Markdown, HTML, and structured data plus comprehensive usage statistics.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/claude-sessions.svg)](https://badge.fury.io/py/claude-sessions)
[![Downloads](https://pepy.tech/badge/claude-sessions)](https://pepy.tech/project/claude-sessions)

**Claude Code has no export button.** Your conversations are trapped in `~/.claude/projects/` as undocumented JSONL files. Claude Sessions backs them up automatically.

## What's New in v2.0

- **Single command**: `claude-sessions` replaces multiple CLI tools
- **Incremental backup**: Only backs up new/changed files
- **Multiple formats**: Markdown, HTML, and structured JSON - all at once
- **Statistics dashboard**: Beautiful HTML dashboard with usage analytics
- **Prompts extraction**: `prompts.yaml` with all your user prompts per project

## Quick Start

```bash
# Install
pipx install claude-sessions

# Set output directory (one-time setup)
export OUTPUT_DIR=~/claude-backup

# Run backup
claude-sessions
```

That's it! Your conversations are backed up with:
- Original JSONL files preserved
- Markdown, HTML, and JSON conversions
- Statistics dashboard (`stats.html`)
- User prompts extraction (`prompts.yaml`)

## Commands

### `claude-sessions` (default: --backup)

Perform incremental backup of all Claude Code sessions:

```bash
# Basic backup (uses OUTPUT_DIR env var)
claude-sessions

# Specify output directory
claude-sessions --output ~/my-backups

# Specify input (if not default ~/.claude/projects)
claude-sessions --input /path/to/projects

# Generate only specific formats
claude-sessions --format markdown,html
```

### `claude-sessions --list`

Show projects and backup status:

```bash
claude-sessions --list
```

Output:
```
PROJECT                                            INPUT   BACKUP     STATUS
-home-user-projects-myapp                             12        8    PENDING
-home-user-projects-webapp                             5        5         OK
```

## Output Structure

```
<output>/
├── stats.html              # Statistics dashboard
├── stats.json              # Statistics data (machine-readable)
├── <project>/
│   ├── <session>.jsonl     # Original backup (timestamp preserved)
│   ├── prompts.yaml        # User prompts from all sessions
│   ├── markdown/
│   │   └── <session>.md    # Human-readable conversation
│   ├── html/
│   │   └── <session>.html  # Web-viewable with styling
│   └── data/
│       └── <session>.json  # Structured data with metadata
```

## Statistics Dashboard

The generated `stats.html` includes:

- **Total sessions, messages, and tokens**
- **Work hours distribution** (when you use Claude)
- **Models used** (Claude 3, 4, etc.)
- **Session duration statistics**
- **Code blocks generated**
- **Per-project breakdown**

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OUTPUT_DIR` | Default backup destination |

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--backup` | Perform incremental backup | (default mode) |
| `--list` | Show projects and status | - |
| `--search` | Search conversations | - |
| `--mode` | Search mode (smart/exact/regex/semantic) | `smart` |
| `--input` | Source directory | `~/.claude/projects/` |
| `--output` | Destination directory | `$OUTPUT_DIR` |
| `--format` | Output formats | `markdown,html,data` |

## Installation

### Quick Install (Recommended)

```bash
# Using pipx (isolated environment)
pipx install claude-sessions

# OR using pip
pip install claude-sessions
```

### Platform-Specific

<details>
<summary>macOS</summary>

```bash
brew install pipx
pipx ensurepath
pipx install claude-sessions
```
</details>

<details>
<summary>Windows</summary>

```bash
py -m pip install --user pipx
py -m pipx ensurepath
# Restart terminal
pipx install claude-sessions
```
</details>

<details>
<summary>Linux</summary>

```bash
sudo apt install pipx  # or equivalent
pipx ensurepath
pipx install claude-sessions
```
</details>

### `claude-sessions --search`

Search through your backed-up conversations:

```bash
# Smart search (default) - handles typos, fuzzy matching
claude-sessions --search "authentication bug"

# Exact phrase matching
claude-sessions --search "exact phrase" --mode exact

# Regex pattern matching
claude-sessions --search "def \w+_handler" --mode regex

# Semantic search (requires spaCy)
claude-sessions --search "error handling patterns" --mode semantic
```

Search options:
- `--mode`: Search mode (`smart`, `exact`, `regex`, `semantic`)
- `--context`: Lines of context around matches (default: 150 chars)
- `--max-results`: Maximum results to show (default: 20)

## Where Are Claude Code Logs?

Claude Code stores conversations in:
- **macOS/Linux**: `~/.claude/projects/`
- **Windows**: `%USERPROFILE%\.claude\projects\`

Each project folder contains JSONL files with undocumented format. Claude Sessions handles parsing automatically.

## Privacy & Security

- **100% Local**: Never sends data anywhere
- **No Internet**: Works completely offline
- **No Tracking**: Zero telemetry
- **Read-Only**: Never modifies source files
- **Open Source**: Audit the code yourself

## Requirements

- Python 3.8+
- Claude Code with existing conversations
- PyYAML (installed automatically)

### Optional: Advanced Search

```bash
pip install claude-sessions[nlp]
python -m spacy download en_core_web_sm
```

## FAQ

### How does incremental backup work?

Claude Sessions compares timestamps between source and backup. Only new or modified files are copied. Files with identical timestamps are skipped.

### Can I backup to cloud storage?

Yes! Set `--output` to any path, including mounted cloud drives (Dropbox, Google Drive, OneDrive, etc.).

### What's in `prompts.yaml`?

A readable YAML file with all your user prompts, organized by session. Useful for:
- Reviewing what you've asked Claude
- Creating prompt libraries
- Documenting your workflow

### How do I update to v2.0?

```bash
pipx upgrade claude-sessions
# or
pip install --upgrade claude-sessions
```

The new `claude-sessions` command is added alongside existing commands.

## Development

```bash
git clone https://github.com/ZeroSumQuant/claude-sessions.git
cd claude-sessions
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Contributing

See [CONTRIBUTING.md](docs/development/CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE).

## Support

- Star this repo to help others find it
- Report issues on [GitHub Issues](https://github.com/ZeroSumQuant/claude-sessions/issues)
- Share with other Claude Code users

---

**Keywords**: backup claude code, export claude conversations, claude code export tool, claude jsonl to markdown, ~/.claude/projects, claude sessions backup, claude code statistics, extract claude logs

**Note**: Independent open-source tool. Not affiliated with Anthropic.
