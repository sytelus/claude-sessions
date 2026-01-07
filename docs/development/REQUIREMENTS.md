# Claude Sessions - Requirements Specification

## Overview

Claude Sessions is a backup and analysis tool for Claude Code conversation sessions. It incrementally backs up sessions from `~/.claude/projects/` and converts them to multiple formats while computing comprehensive statistics.

## Command Line Interface

### Command
- Single entry point: `claude-sessions`

### Arguments

#### `--backup` (default mode)
- Creates incremental backup of Claude sessions
- Default action when no mode is specified

#### `--list`
- Displays available Claude projects and their backup status
- Shows what has been backed up and what will be backed up

#### `--output <path>`
- Specifies the output folder for backups
- Default: Value from `OUT_DIR` environment variable
- If not set and not provided: prompt user interactively

#### `--input <path>`
- Specifies the input folder containing Claude sessions
- Default: `~/.claude/projects/`

#### `--format <formats>`
- Comma-separated list of output formats
- Valid values: `markdown`, `html`, `data`
- Default: `markdown,html,data`

---

## Functional Requirements

### FR-1: Backup Mode (`--backup`)

#### FR-1.1: Project Folder Synchronization
- Create project folders in output that don't yet exist in input
- Preserve input folder structure in output

#### FR-1.2: File Synchronization
- Copy files from input to output that don't exist in output
- Skip files with identical timestamps (no action needed)
- Overwrite files when timestamps differ (regardless of older/newer)
- Preserve original file timestamps in output copies

#### FR-1.3: Format Conversion
- For each `.jsonl` file copied/updated, generate:
  - Markdown version in `<output>/<project>/markdown/`
  - HTML version in `<output>/<project>/html/`
  - Structured data version in `<output>/<project>/data/`
- Only generate formats specified by `--format` argument

#### FR-1.4: Non-Destructive Operation
- Never delete files or folders from output directory
- Output may contain files/folders deleted from input (intentional preservation)

#### FR-1.5: Logging
- Display detailed log of all operations
- Show statistics of processing (files copied, skipped, converted)

### FR-2: List Mode (`--list`)

#### FR-2.1: Project Discovery
- List all projects from `~/.claude/projects/` (or `--input` path)
- Show file count per project in input folder

#### FR-2.2: Backup Status
- Show corresponding projects in output folder
- Show session count in each project in output folder
- Indicate which projects/files will be backed up if `--backup` is run

### FR-3: Statistics Generation

#### FR-3.1: Statistics Files
- Generate `stats.html` at output root (human-readable)
- Generate `stats.json` at output root (machine-readable)

#### FR-3.2: Statistics Scope
- Per-project statistics
- Aggregate statistics across all projects

#### FR-3.3: Statistics Categories

**Conversation Metrics:**
- Number of sessions per project
- Number of turns (exchanges) per session
- Total messages (user + assistant)

**Token Metrics:**
- Total tokens (if available in data)
- Token breakdown by type (input/output/thinking)
- Average tokens per message

**Timing Metrics:**
- Claude response/thinking time
- Longest thinking time
- User response latency (time between Claude response and user's next message)
- Session duration
- Work hour distribution (histogram of when user is active)

**Communication Patterns:**
- Apology detection (Claude saying sorry, mistake, error)
- Correction patterns
- Question frequency

**Productivity Metrics:**
- Git commits made (if detectable)
- Code blocks produced
- Lines of code generated
- Files created/modified (if detectable)

**Trend Analysis:**
- Usage over time (daily/weekly/monthly)
- Token usage trends
- Session length trends

**Statistical Measures:**
- Minimum, Maximum, Average, Standard Deviation
- Distributions/histograms where applicable

### FR-4: Prompts Extraction

#### FR-4.1: Prompts File
- Generate `prompts.yaml` in each project folder
- Contains user-typed prompts from all sessions in that project

#### FR-4.2: Prompts Format
- YAML format for readability
- Organized by session
- Include timestamp for each prompt

---

## Output Folder Structure

```
<output>/
├── stats.html              # Aggregate statistics (human-readable)
├── stats.json              # Aggregate statistics (machine-readable)
├── <project-1>/
│   ├── <session-1>.jsonl   # Original backup (timestamp preserved)
│   ├── <session-2>.jsonl
│   ├── prompts.yaml        # Extracted user prompts
│   ├── markdown/
│   │   ├── <session-1>.md
│   │   └── <session-2>.md
│   ├── html/
│   │   ├── <session-1>.html
│   │   └── <session-2>.html
│   └── data/
│       ├── <session-1>.json
│       └── <session-2>.json
├── <project-2>/
│   └── ...
```

---

## Non-Functional Requirements

### NFR-1: Performance
- Efficient incremental backup (skip unchanged files)
- Handle large session files gracefully

### NFR-2: Robustness
- Handle malformed JSONL files gracefully
- Continue processing other files if one fails
- Report errors clearly without crashing

### NFR-3: User Experience
- Clear progress indication during backup
- Detailed logging of operations
- Summary statistics after completion

### NFR-4: Data Preservation
- Structured data format preserves maximum information from input
- No data loss during conversion

### NFR-5: Maintainability
- Clean, documented code
- Comprehensive test coverage
- Clear separation of concerns

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OUT_DIR` | Default output directory for backups | None (prompt if not set) |

---

## Dependencies

- Python 3.8+
- PyYAML (for prompts.yaml generation)
- Standard library: json, os, shutil, pathlib, datetime, statistics, html
