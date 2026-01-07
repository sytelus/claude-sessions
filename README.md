# Claude Sessions

Backup and analyze Claude Code conversations. Converts JSONL session logs to Markdown, HTML, and structured JSON with usage statistics.

## Installation

```bash
# From PyPI
pip install claude-sessions

# From source
git clone https://github.com/shitalshah/claude-sessions.git
cd claude-sessions
pip install -e .
```

Optional NLP support for semantic search:
```bash
pip install claude-sessions[nlp]
python -m spacy download en_core_web_sm
```

## Usage

```bash
# Backup all sessions (set OUTPUT_DIR or use --output)
export OUTPUT_DIR=~/claude-backup
claude-sessions

# List projects and backup status
claude-sessions --list

# Search conversations
claude-sessions --search -q "authentication bug"
claude-sessions --search -q "def \w+_handler" --mode regex
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--backup` | Run incremental backup | (default mode) |
| `--list` | Show projects and backup status | |
| `--search` | Search conversation content | |
| `--input` | Source directory | `~/.claude/projects/` |
| `--output` | Destination directory | `$OUTPUT_DIR` |
| `--format` | Output formats (comma-separated) | `markdown,html,data` |
| `-q, --query` | Search query string | |
| `-m, --mode` | Search mode: `smart`, `exact`, `regex`, `semantic` | `smart` |
| `--speaker` | Filter by speaker: `human`, `assistant` | |
| `--max-results` | Maximum search results | `20` |
| `--case-sensitive` | Case-sensitive search | `false` |

## How It Works

The tool runs a five-stage pipeline:

1. **Backup**: Incrementally copies JSONL files (timestamp-based, only new/modified)
2. **Convert**: Generates Markdown, HTML, and JSON from each session
3. **Statistics**: Computes usage metrics and generates an HTML dashboard
4. **Prompts**: Extracts user prompts to YAML files
5. **Index**: Generates browsable index page with project/session navigation

Core modules:
- `claude_sessions.py` - CLI entry point
- `backup.py` - Incremental file synchronization
- `parser.py` - JSONL parsing to normalized messages
- `formatters.py` - Markdown/HTML/JSON conversion
- `stats.py` - Statistics computation and dashboard
- `prompts.py` - User prompt extraction
- `html_generator.py` - Shared HTML/CSS and index generation
- `search_conversations.py` - Multi-mode search engine

## Input and Output

### Input

Claude Code stores sessions in `~/.claude/projects/<project-hash>/<session-id>.jsonl`. Each JSONL file contains message entries of types: `user`, `assistant`, `tool_use`, `tool_result`.

### Output

```
<output>/claude-sessions/
├── index.html                # Browsable session navigator (start here)
├── stats.html                # Usage statistics dashboard
├── stats.json                # Statistics (machine-readable)
└── <project>/
    ├── <session>.jsonl       # Original backup
    ├── prompts.yaml          # Extracted user prompts
    ├── markdown/<session>.md # Human-readable conversation
    ├── html/<session>.html   # Styled web view
    └── data/<session>.json   # Structured data with metadata
```

## Credits

Created by **Shital Shah** with **Claude Code** (Anthropic's Opus 4.5).

## License

MIT License - see [LICENSE](LICENSE).

## Contributing

Contributions welcome! Please open an issue or submit a pull request.
