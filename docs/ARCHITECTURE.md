# Claude Sessions Architecture

This document provides a comprehensive overview of the Claude Sessions codebase architecture, data flows, and design decisions.

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Module Reference](#module-reference)
4. [Data Flow](#data-flow)
5. [File Formats](#file-formats)
6. [Configuration](#configuration)
7. [Extension Points](#extension-points)

---

## Overview

Claude Sessions is a Python tool for backing up, converting, and analyzing Claude Code conversation sessions. It processes JSONL log files created by Claude Code and provides:

- **Incremental backup** with timestamp preservation
- **Format conversion** to Markdown, HTML, and structured JSON
- **Statistics generation** with HTML dashboards
- **Prompt extraction** to YAML format
- **Full-text search** with multiple search modes

### Design Principles

1. **Incremental Processing**: Only process files that have changed
2. **Modular Architecture**: Each component handles a specific responsibility
3. **Shared Utilities**: Common functionality in `utils.py` to avoid duplication
4. **Graceful Degradation**: Optional dependencies (spaCy) don't break core functionality
5. **Minimal Dependencies**: Core features work with Python standard library only

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      CLI Entry Point                             │
│                    (claude_sessions.py)                          │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   --backup    │     │   --search    │     │    --list     │
│  (default)    │     │               │     │               │
└───────────────┘     └───────────────┘     └───────────────┘
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│ BackupManager │     │ Conversation  │     │  (inline)     │
│               │     │   Searcher    │     │               │
├───────────────┤     └───────────────┘     └───────────────┘
│ FormatConvert │
├───────────────┤
│ Statistics    │
│   Generator   │
├───────────────┤
│ Prompts       │
│   Extractor   │
└───────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│                    Shared Components                           │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐  │
│  │  utils.py  │  │ parser.py  │  │  Python Standard Lib   │  │
│  │            │  │            │  │  (json, pathlib, etc)  │  │
│  └────────────┘  └────────────┘  └────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Module Reference

### Core Modules

| Module | Class/Functions | Purpose |
|--------|-----------------|---------|
| `claude_sessions.py` | `main()`, `cmd_*()` | CLI entry point and command dispatch |
| `backup.py` | `BackupManager` | Incremental file synchronization |
| `formatters.py` | `FormatConverter` | Convert JSONL to MD/HTML/JSON |
| `stats.py` | `StatisticsGenerator` | Compute and render statistics |
| `prompts.py` | `PromptsExtractor` | Extract user prompts to YAML |
| `html_generator.py` | `HtmlGenerator` | Shared HTML/CSS and index generation |
| `search_conversations.py` | `ConversationSearcher` | Multi-mode search engine |

### Support Modules

| Module | Purpose |
|--------|---------|
| `parser.py` | Unified JSONL parsing for all components |
| `utils.py` | Shared utilities (text extraction, timestamps, iteration) |

### Module Dependencies

```
claude_sessions.py
    ├── backup.py
    ├── formatters.py ────────────┐
    │       ├── parser.py         │
    │       ├── utils.py          │
    │       └── html_generator.py │
    ├── stats.py ─────────────────┤
    │       ├── parser.py         │
    │       ├── utils.py          │
    │       └── html_generator.py │
    ├── prompts.py ───────────────┤
    │       ├── parser.py         │
    │       └── utils.py          │
    ├── html_generator.py ────────┤
    │       ├── parser.py         │
    │       └── utils.py          │
    └── search_conversations.py
            └── utils.py
```

---

## Data Flow

### Backup Pipeline

```
~/.claude/projects/           (1) Incremental Copy
       │                      ────────────────────►
       │                                            output_dir/claude-sessions/
       │                                                 │
       │                      (2) Parse & Convert        │
       │                      ────────────────────►      ├── <project>/
       │                                                 │   ├── *.jsonl
       │                                                 │   ├── markdown/*.md
       │                                                 │   ├── html/*.html
       │                      (3) Statistics             │   ├── data/*.json
       │                      ────────────────────►      │   └── prompts.yaml
       │                                                 │
       │                      (4) Prompts                ├── index.html  (browse here)
       │                      ────────────────────►      ├── stats.html
       │                                                 └── stats.json
       │                      (5) Index Page
       │                      ────────────────────►
```

All outputs are created in a `claude-sessions` subfolder under the user-specified output directory.
This keeps the backup isolated and avoids polluting the user's output directory with multiple files.
The `index.html` serves as the main entry point for browsing all sessions.

### Search Flow

```
Query ──► ConversationSearcher
               │
               ├── mode=smart ──► Token matching + Proximity + Exact
               ├── mode=exact ──► Simple string matching
               ├── mode=regex ──► Regex pattern matching
               └── mode=semantic ──► spaCy NLP (if available)
                       │
                       ▼
               List[SearchResult]
                       │
                       ▼
               Sorted by relevance_score
```

### JSONL Parsing Flow

```
JSONL File
    │
    ▼
SessionParser.parse_file()
    │
    ├── type="user" ──────► _parse_user_message()
    ├── type="assistant" ─► _parse_assistant_message()
    ├── type="tool_use" ──► _parse_tool_use()
    └── type="tool_result"► _parse_tool_result()
            │
            ▼
    List[ParsedMessage]
```

---

## File Formats

### Input: Claude Code JSONL

Location: `~/.claude/projects/<project-hash>/<session-id>.jsonl`

Each line is a JSON object with one of these types:

#### User Message
```json
{
  "type": "user",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "uuid": "abc123",
  "sessionId": "session-456",
  "message": {
    "content": "Hello, Claude!"
  }
}
```

Note: `content` can be a string or an array of content blocks:
```json
{
  "content": [
    {"type": "text", "text": "Look at this image"},
    {"type": "image", "source": {...}}
  ]
}
```

#### Assistant Message
```json
{
  "type": "assistant",
  "timestamp": "2024-01-15T10:30:05.000Z",
  "uuid": "def456",
  "message": {
    "model": "claude-3-opus-20240229",
    "content": [
      {"type": "thinking", "thinking": "Let me consider..."},
      {"type": "text", "text": "Here's my response..."},
      {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {...}}
    ],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 200,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 100
    },
    "stop_reason": "end_turn"
  }
}
```

#### Tool Use
```json
{
  "type": "tool_use",
  "timestamp": "2024-01-15T10:30:10.000Z",
  "uuid": "ghi789",
  "tool": {
    "name": "Read",
    "input": {"file_path": "/path/to/file"}
  }
}
```

#### Tool Result
```json
{
  "type": "tool_result",
  "timestamp": "2024-01-15T10:30:11.000Z",
  "uuid": "jkl012",
  "result": {
    "output": "File contents here...",
    "error": null
  }
}
```

### Output Formats

#### Markdown (*.md)
Human-readable conversation log with:
- Session metadata header
- User/Claude message sections
- Collapsible thinking blocks
- Tool call details with JSON formatting

#### HTML (*.html)
Styled single-page document with:
- Color-coded message types (blue=user, green=assistant, orange=tool)
- Responsive design
- Collapsible thinking sections

#### Data JSON (*.json)
Structured data with:
```json
{
  "metadata": {
    "session_id": "...",
    "source_file": "...",
    "start_time": "...",
    "end_time": "..."
  },
  "statistics": {
    "total_messages": 42,
    "user_messages": 20,
    "assistant_messages": 22,
    "total_tokens": 15000
  },
  "messages": [...]
}
```

#### Prompts YAML (prompts.yaml)
```yaml
project: project-name
sessions:
  - session_id: abc123
    date: "2024-01-15"
    prompts:
      - prompt: "First user message"
        timestamp: "2024-01-15T10:30:00.000Z"
      - prompt: |
          Multiline
          prompt text
        timestamp: "2024-01-15T10:35:00.000Z"
```

#### Statistics JSON (stats.json)
```json
{
  "generated_at": "2024-01-15T12:00:00",
  "aggregate": {
    "total_sessions": 100,
    "total_messages": 5000,
    "total_tokens": 1500000,
    "work_hours": {"9": 50, "10": 80, ...},
    "models_used": {"claude-3-opus": 60, ...}
  },
  "projects": [...]
}
```

---

## Configuration

### SearchConfig Dataclass

The search module uses a frozen dataclass for configuration:

```python
@dataclass(frozen=True)
class SearchConfig:
    # Display settings
    major_separator_width: int = 60
    default_max_results: int = 20
    max_content_length: int = 200
    default_context_size: int = 150

    # Relevance scoring
    relevance_threshold: float = 0.1
    match_bonus: float = 0.5
    # ... see search_conversations.py for full list
```

### Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OUTPUT_DIR` | Base output directory for backups | (none, prompts user) |

Note: The actual backup is created in `$OUTPUT_DIR/claude-sessions/`, not directly in `$OUTPUT_DIR`.

### Skip Directories

The `utils.SKIP_DIRS` set defines directories to skip when iterating:
```python
SKIP_DIRS = {"markdown", "html", "data"}
```

---

## Extension Points

### Adding a New Output Format

1. Add format handler in `formatters.py`:
```python
def _write_custom(self, messages: List[Dict], output_path: Path, session_id: str) -> None:
    """Write messages as custom format."""
    # Implementation here
```

2. Update `convert_all()` to call the new handler
3. Add format to `_needs_conversion()` format_paths dict
4. Add to valid_formats in `claude_sessions.py`

### Adding a New Search Mode

1. Add method in `ConversationSearcher`:
```python
def _search_custom(self, jsonl_file: Path, query: str, ...) -> List[SearchResult]:
    """Custom search implementation."""
```

2. Add mode handling in `search()` method
3. Add to CLI choices in `claude_sessions.py`

### Adding New Statistics

1. Add counters to `generate()` aggregate dict in `stats.py`
2. Update `_analyze_session()` to collect the data
3. Update `_compute_project_stats()` to aggregate
4. Update `save_html()` to display the new stats

### Custom JSONL Entry Types

1. Add handler in `parser.py`:
```python
def _parse_custom_type(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
    """Parse custom entry type."""
```

2. Add condition in `_parse_entry()` to call the handler

---

## Performance Considerations

### Incremental Processing

- **Backup**: Uses file modification timestamps (1-second tolerance)
- **Format Conversion**: Compares input/output mtimes
- **Statistics**: Regenerated on each run (could be cached)

### Memory Usage

- Files are processed line-by-line (streaming)
- Large tool outputs are truncated (2000 chars in MD/HTML)
- Statistics accumulate in memory (suitable for typical session counts)

### Search Optimization

- Files are filtered by date before content search
- Results are sorted and truncated to max_results early
- spaCy NLP is optional and loaded lazily

---

## Error Handling

### Graceful Degradation

| Scenario | Behavior |
|----------|----------|
| spaCy not installed | Semantic search falls back to smart mode |
| PyYAML not installed | Uses manual YAML generation |
| Invalid JSONL line | Line is skipped, processing continues |
| Permission error | Error logged, file skipped |
| Missing input directory | Error message, exit code 1 |

### Logging

Currently uses `print()` for user-facing messages. Future enhancement: structured logging.

---

## Testing

### Test Structure

```
tests/
├── test_backup.py
├── test_formatters.py
├── test_parser.py
├── test_prompts.py
├── test_search.py
├── test_stats.py
└── test_utils.py
```

### Running Tests

```bash
# All tests
pytest tests/

# Specific module
pytest tests/test_parser.py

# With coverage
pytest tests/ --cov=src
```

---

## Future Enhancements

See [REQUIREMENTS.md](development/REQUIREMENTS.md) for the full roadmap.

Potential improvements:
- SQLite index for faster repeated searches
- Streaming HTML generation for very large sessions
- Watch mode for automatic backup on file changes
- Export to other formats (PDF, EPUB)
- Web UI for browsing conversations
