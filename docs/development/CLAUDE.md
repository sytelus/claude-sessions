# Claude Sessions - Project Context

## Project Overview

Claude Sessions is a backup and analysis tool for Claude Code conversations. It extracts
conversations from the undocumented JSONL format in `~/.claude/projects/` and converts
them to multiple formats (Markdown, HTML, structured JSON) with comprehensive statistics.

## Key Goals

- **Professional Quality**: Polished and professional tool
- **Easy Installation**: Available via `pip install claude-sessions`
- **Wide Adoption**: Go-to solution for Claude Code users
- **Comprehensive Analytics**: Statistics dashboard for usage insights

## Repository Structure

```text
claude-sessions/
├── src/
│   ├── __init__.py           # Package exports
│   ├── claude_sessions.py    # Main CLI entry point
│   ├── backup.py             # Incremental backup logic
│   ├── formatters.py         # Format converters (MD, HTML, JSON)
│   ├── stats.py              # Statistics generation
│   └── prompts.py            # User prompts extraction
├── docs/
│   ├── development/
│   │   ├── CLAUDE.md         # This file
│   │   ├── REQUIREMENTS.md   # Detailed specification
│   │   └── INVARIANTS.md     # Validation invariants
│   └── user/
│       └── CHANGELOG.md      # Release history
├── tests/                    # Test suite
├── pyproject.toml            # Modern Python packaging
├── README.md                 # User documentation
├── LICENSE                   # MIT License
└── .gitignore
```

## Development Workflow

1. Always create feature branches for new work
2. Ensure code passes linting
3. Test manually before committing
4. Update version numbers in pyproject.toml for releases
5. Create detailed commit messages
6. Update CHANGELOG.md for user-facing changes

## Current Status (v2.0)

- Single `claude-sessions` command
- Incremental backup with timestamp preservation
- Multiple output formats (Markdown, HTML, structured JSON)
- Statistics dashboard (stats.html)
- User prompts extraction (prompts.yaml)
- Published on PyPI

## Testing Commands

```bash
# Run backup
claude-sessions --output ~/backup

# List projects
claude-sessions --list

# Test from source
PYTHONPATH=src python -c "from claude_sessions import main; main()"

# Install for development
pip install -e ".[dev]"

# Run tests
pytest
```

## Architecture

### Components

1. **BackupManager** (`backup.py`): Handles incremental file synchronization
2. **FormatConverter** (`formatters.py`): Converts JSONL to MD/HTML/JSON
3. **StatisticsGenerator** (`stats.py`): Computes and renders statistics
4. **PromptsExtractor** (`prompts.py`): Extracts user prompts to YAML

### Data Flow

```
~/.claude/projects/     ──┐
                          │  BackupManager
                          ├──────────────────►  output/*.jsonl
                          │
                          │  FormatConverter
                          ├──────────────────►  output/markdown/*.md
                          │                     output/html/*.html
                          │                     output/data/*.json
                          │
                          │  StatisticsGenerator
                          ├──────────────────►  output/stats.html
                          │                     output/stats.json
                          │
                          │  PromptsExtractor
                          └──────────────────►  output/*/prompts.yaml
```

## Important Notes

- Requires PyYAML for prompts extraction
- Supports Python 3.8+
- Cross-platform (Windows, macOS, Linux)
- Read-only access to Claude's conversation files
- Never deletes files from output (preserves history)

## Version History

See [CHANGELOG.md](../user/CHANGELOG.md) for detailed release history.
