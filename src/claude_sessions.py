#!/usr/bin/env python3
"""
Claude Sessions - Backup and analyze Claude Code conversation sessions.

This is the main entry point for the claude-sessions CLI tool. It provides
commands for backing up, converting, and searching Claude Code session logs.

Commands:
    --backup (default): Perform incremental backup with format conversion
    --list: Show projects and their backup status
    --search: Search conversation content across sessions

Backup Pipeline:
    1. Incremental backup: Copy new/modified JSONL files to output directory
    2. Format conversion: Generate Markdown, HTML, and JSON formats
    3. Statistics generation: Compute usage statistics and HTML dashboard
    4. Prompt extraction: Extract user prompts to YAML files

Configuration:
    - Input directory: Default ~/.claude/projects (where Claude Code stores logs)
    - Output directory: Via --output flag or OUTPUT_DIR environment variable
    - Formats: Customizable via --format flag (markdown,html,data)

For architecture details and data flows, see:
    docs/ARCHITECTURE.md

For JSONL format specification, see:
    docs/JSONL_FORMAT.md

Usage Examples:
    # Run default backup
    claude-sessions --output ~/claude-backups

    # List projects without backing up
    claude-sessions --list

    # Search for specific terms
    claude-sessions --search -q "authentication" --mode smart

    # Generate only markdown format
    claude-sessions --format markdown --output ~/backups

Functions:
    main(): CLI entry point
    cmd_backup(): Execute backup pipeline
    cmd_search(): Execute search command
    cmd_list(): Show project list and status
    get_output_dir(): Resolve output directory from args/env/prompt
    parse_formats(): Parse format string into list

Module Constants:
    DEFAULT_INPUT_DIR: Default Claude Code projects directory
    DEFAULT_FORMATS: Default output formats (markdown,html,data)
    ENV_OUTPUT_DIR: Environment variable name for output directory
    OUTPUT_SUBFOLDER: Subfolder name for all outputs ("claude-sessions")
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from .backup import BackupManager
from .formatters import FormatConverter
from .stats import StatisticsGenerator
from .prompts import PromptsExtractor
from .search_conversations import ConversationSearcher


# Constants
DEFAULT_INPUT_DIR = Path.home() / ".claude" / "projects"
DEFAULT_FORMATS = "markdown,html,data"
ENV_OUTPUT_DIR = "OUTPUT_DIR"
OUTPUT_SUBFOLDER = "claude-sessions"


def get_output_dir(args_output: Optional[str]) -> Path:
    """
    Get output directory from args, env var, or prompt user.

    Resolution priority:
        1. Command line --output argument
        2. OUTPUT_DIR environment variable
        3. Interactive user prompt

    Args:
        args_output: Output path from command line arguments (may be None)

    Returns:
        Path object for the resolved output directory

    Raises:
        SystemExit: If user cancels prompt or no directory provided
    """
    # Priority 1: Command line argument
    if args_output:
        return Path(args_output).expanduser()

    # Priority 2: Environment variable
    env_output = os.environ.get(ENV_OUTPUT_DIR)
    if env_output:
        return Path(env_output).expanduser()

    # Priority 3: Prompt user
    print("No output directory specified.")
    print("You can set it via:")
    print("  1. --output <path> argument")
    print(f"  2. {ENV_OUTPUT_DIR} environment variable")
    print()

    try:
        user_input = input("Enter output directory path: ").strip()
        if user_input:
            return Path(user_input).expanduser()
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(1)

    print("Error: Output directory is required.")
    sys.exit(1)


def parse_formats(format_str: str) -> List[str]:
    """
    Parse comma-separated format string into list of valid formats.

    Valid formats are: markdown, html, data

    Args:
        format_str: Comma-separated format names (e.g., "markdown,html")

    Returns:
        List of valid format names. Invalid formats are logged and skipped.
        Returns all valid formats if input has no valid formats.
    """
    valid_formats = {"markdown", "html", "data"}
    formats = [f.strip().lower() for f in format_str.split(",")]

    invalid = set(formats) - valid_formats
    if invalid:
        print(f"Warning: Invalid formats ignored: {invalid}")
        formats = [f for f in formats if f in valid_formats]

    return formats if formats else list(valid_formats)


def cmd_backup(args: argparse.Namespace) -> None:
    """
    Execute the backup command.

    Runs the full backup pipeline:
        1. Incremental file backup (BackupManager)
        2. Format conversion (FormatConverter)
        3. Statistics generation (StatisticsGenerator)
        4. Prompt extraction (PromptsExtractor)

    Progress is printed to stdout throughout the process.

    Args:
        args: Parsed command line arguments containing:
            - input: Input directory path
            - output: Output directory path (may be None)
            - format: Format string (e.g., "markdown,html,data")

    Raises:
        SystemExit: If input directory doesn't exist
    """
    input_dir = Path(args.input).expanduser()
    base_output_dir = get_output_dir(args.output)
    output_dir = base_output_dir / OUTPUT_SUBFOLDER
    formats = parse_formats(args.format)

    print("=" * 60)
    print("CLAUDE SESSIONS BACKUP")
    print("=" * 60)
    print(f"Input:   {input_dir}")
    print(f"Output:  {output_dir}")
    print(f"Formats: {', '.join(formats)}")
    print("=" * 60)
    print()

    # Validate input directory
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)

    # Create output directory if needed (including claude-sessions subfolder)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize components
    backup_mgr = BackupManager(input_dir, output_dir)
    formatter = FormatConverter()
    stats_gen = StatisticsGenerator()
    prompts_ext = PromptsExtractor()

    # Step 1: Perform incremental backup
    print("[1/4] Backing up session files...")
    backup_result = backup_mgr.backup()

    print(f"  - Projects found: {backup_result['projects_found']}")
    print(f"  - Files copied: {backup_result['files_copied']}")
    print(f"  - Files skipped (unchanged): {backup_result['files_skipped']}")
    print(f"  - Files updated: {backup_result['files_updated']}")
    print()

    # Step 2: Convert to requested formats
    print("[2/4] Converting to output formats...")
    convert_result = formatter.convert_all(output_dir, formats)

    print(f"  - Markdown files: {convert_result.get('markdown', 0)}")
    print(f"  - HTML files: {convert_result.get('html', 0)}")
    print(f"  - Data files: {convert_result.get('data', 0)}")
    print(f"  - Skipped (unchanged): {convert_result.get('skipped', 0)}")
    print()

    # Step 3: Generate statistics
    print("[3/4] Computing statistics...")
    stats = stats_gen.generate(output_dir)
    stats_gen.save_html(stats, output_dir / "stats.html")
    stats_gen.save_json(stats, output_dir / "stats.json")

    print(f"  - Total sessions: {stats['aggregate']['total_sessions']}")
    print(f"  - Total messages: {stats['aggregate']['total_messages']}")
    print(f"  - Total tokens: {stats['aggregate']['total_tokens']:,}")
    print()

    # Step 4: Extract prompts
    print("[4/4] Extracting user prompts...")
    prompts_result = prompts_ext.extract_all(output_dir)

    print(f"  - Projects processed: {prompts_result['projects']}")
    print(f"  - Prompts extracted: {prompts_result['prompts']}")
    print()

    # Summary
    print("=" * 60)
    print("BACKUP COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print(f"Statistics: {output_dir / 'stats.html'}")
    print("=" * 60)


def cmd_search(args: argparse.Namespace) -> None:
    """
    Execute the search command.

    Searches through Claude Code session logs for matching content.
    Results are grouped by session file and displayed with relevance scores.

    If no query is provided via --query/-q, prompts the user interactively.

    Args:
        args: Parsed command line arguments containing:
            - input: Directory to search
            - query: Search query string (may be None for interactive)
            - mode: Search mode (smart, exact, regex, semantic)
            - speaker: Optional speaker filter (human/assistant)
            - max_results: Maximum number of results to return
            - case_sensitive: Whether search is case-sensitive

    Raises:
        SystemExit: If input directory doesn't exist or user cancels
    """
    input_dir = Path(args.input).expanduser()

    print("=" * 60)
    print("CLAUDE SESSIONS - SEARCH")
    print("=" * 60)
    print()

    # Validate input directory
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)

    # Get search query
    query = args.query
    if not query:
        try:
            query = input("Enter search term: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            sys.exit(1)

    if not query:
        print("Error: No search term provided.")
        sys.exit(1)

    print(f"Searching for: '{query}'")
    print(f"Directory: {input_dir}")
    print(f"Mode: {args.mode}")
    print()

    # Initialize searcher
    searcher = ConversationSearcher()

    # Perform search
    results = searcher.search(
        query=query,
        search_dir=input_dir,
        mode=args.mode,
        speaker_filter=args.speaker,
        max_results=args.max_results,
        case_sensitive=args.case_sensitive,
    )

    if not results:
        print(f"No matches found for '{query}'")
        print()
        print("Tips:")
        print("  - Try a more general search term")
        print("  - Search is case-insensitive by default")
        print("  - Use --mode regex for pattern matching")
        return

    print(f"Found {len(results)} results:")
    print("-" * 60)

    # Group by file
    by_file = {}
    for result in results:
        fname = result.file_path.name
        if fname not in by_file:
            by_file[fname] = []
        by_file[fname].append(result)

    # Display results
    for i, (fname, file_results) in enumerate(by_file.items(), 1):
        session_id = fname.replace('.jsonl', '')
        print(f"\n{i}. Session: {session_id[:16]}... ({len(file_results)} matches)")

        # Show first match preview
        first = file_results[0]
        preview = first.matched_content[:120].replace('\n', ' ')
        speaker = first.speaker.title()
        relevance = f"{first.relevance_score:.0%}"
        print(f"   [{speaker}] (relevance: {relevance})")
        print(f"   {preview}...")

    print()
    print("-" * 60)
    print(f"Total: {len(results)} matches in {len(by_file)} sessions")


def cmd_list(args: argparse.Namespace) -> None:
    """
    Execute the list command.

    Displays a table showing all projects in the input directory and their
    backup status. Compares file counts between input and output directories
    to determine status.

    Status values:
        - OK: All files backed up
        - PENDING: Some files not yet backed up
        - ARCHIVED: Files exist only in backup (removed from source)

    Args:
        args: Parsed command line arguments containing:
            - input: Input directory path
            - output: Output directory path (may be None, falls back to env var)

    Raises:
        SystemExit: If input directory doesn't exist
    """
    input_dir = Path(args.input).expanduser()
    base_output_dir = Path(args.output).expanduser() if args.output else None

    if not base_output_dir:
        env_output = os.environ.get(ENV_OUTPUT_DIR)
        if env_output:
            base_output_dir = Path(env_output).expanduser()

    # Append claude-sessions subfolder if base output dir is set
    output_dir = base_output_dir / OUTPUT_SUBFOLDER if base_output_dir else None

    print("=" * 60)
    print("CLAUDE SESSIONS - PROJECT LIST")
    print("=" * 60)
    print()

    # Validate input directory
    if not input_dir.exists():
        print(f"Error: Input directory does not exist: {input_dir}")
        sys.exit(1)

    # Find all projects in input
    input_projects = {}
    for project_dir in sorted(input_dir.iterdir()):
        if project_dir.is_dir():
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if jsonl_files:
                input_projects[project_dir.name] = len(jsonl_files)

    # Find all projects in output (if available)
    output_projects = {}
    if output_dir and output_dir.exists():
        for project_dir in sorted(output_dir.iterdir()):
            if project_dir.is_dir():
                jsonl_files = list(project_dir.glob("*.jsonl"))
                if jsonl_files:
                    output_projects[project_dir.name] = len(jsonl_files)

    # Display results
    all_projects = sorted(set(input_projects.keys()) | set(output_projects.keys()))

    if not all_projects:
        print("No projects found.")
        return

    print(f"{'PROJECT':<50} {'INPUT':>8} {'BACKUP':>8} {'STATUS':>10}")
    print("-" * 80)

    total_input = 0
    total_output = 0
    needs_backup = 0

    for project in all_projects:
        input_count = input_projects.get(project, 0)
        output_count = output_projects.get(project, 0)
        total_input += input_count
        total_output += output_count

        # Determine status
        if input_count > output_count:
            status = "PENDING"
            needs_backup += input_count - output_count
        elif input_count == output_count and input_count > 0:
            status = "OK"
        elif output_count > 0 and input_count == 0:
            status = "ARCHIVED"
        else:
            status = "-"

        # Truncate long project names
        display_name = project[:47] + "..." if len(project) > 50 else project

        print(f"{display_name:<50} {input_count:>8} {output_count:>8} {status:>10}")

    print("-" * 80)
    print(f"{'TOTAL':<50} {total_input:>8} {total_output:>8}")
    print()

    if needs_backup > 0:
        print(f"Files pending backup: {needs_backup}")
        print("Run 'claude-sessions --backup' to backup new files.")
    else:
        print("All files are backed up.")


def main() -> None:
    """
    Main entry point for the claude-sessions CLI.

    Parses command line arguments and dispatches to the appropriate command
    handler (cmd_backup, cmd_search, or cmd_list).

    Commands are mutually exclusive:
        --backup (default): Run the full backup pipeline
        --search: Search conversation content
        --list: Show project list and backup status

    The argument parser is configured with detailed help text and examples
    in the epilog.
    """
    parser = argparse.ArgumentParser(
        prog="claude-sessions",
        description="Backup and analyze Claude Code conversation sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  claude-sessions                           # Default: run backup
  claude-sessions --backup                  # Explicitly run backup
  claude-sessions --list                    # List projects and backup status
  claude-sessions --output ~/backup         # Specify output directory
  claude-sessions --format markdown,html    # Only generate specific formats
  claude-sessions --search -q "python"      # Search for "python"
  claude-sessions --search --mode regex -q "import\\s+\\w+"  # Regex search

Environment Variables:
  OUTPUT_DIR    Default output directory for backups

Search Modes:
  smart     Combines exact matching, token overlap, and proximity (default)
  exact     Exact string matching
  regex     Regular expression pattern matching
  semantic  NLP-based semantic search (requires spacy)

Output Structure:
  <output>/claude-sessions/
  ├── stats.html              # Statistics dashboard
  ├── stats.json              # Statistics data
  └── <project>/
      ├── <session>.jsonl     # Original backup
      ├── prompts.yaml        # Extracted user prompts
      ├── markdown/           # Markdown conversions
      ├── html/               # HTML conversions
      └── data/               # Structured data
        """,
    )

    # Mode arguments (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--backup",
        action="store_true",
        default=True,
        help="Perform incremental backup (default)"
    )
    mode_group.add_argument(
        "--list",
        action="store_true",
        help="List projects and backup status"
    )
    mode_group.add_argument(
        "--search",
        action="store_true",
        help="Search conversations"
    )

    # Path arguments
    parser.add_argument(
        "--input",
        type=str,
        default=str(DEFAULT_INPUT_DIR),
        help=f"Input directory (default: {DEFAULT_INPUT_DIR})"
    )
    parser.add_argument(
        "--output",
        type=str,
        help=f"Output directory (default: ${ENV_OUTPUT_DIR} env var)"
    )

    # Format arguments
    parser.add_argument(
        "--format",
        type=str,
        default=DEFAULT_FORMATS,
        help=f"Output formats, comma-separated (default: {DEFAULT_FORMATS})"
    )

    # Search arguments
    parser.add_argument(
        "--query", "-q",
        type=str,
        help="Search query (for --search mode)"
    )
    parser.add_argument(
        "--mode", "-m",
        type=str,
        choices=["smart", "exact", "regex", "semantic"],
        default="smart",
        help="Search mode (default: smart)"
    )
    parser.add_argument(
        "--speaker",
        type=str,
        choices=["human", "assistant"],
        help="Filter by speaker"
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=20,
        help="Maximum search results (default: 20)"
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Case-sensitive search"
    )

    args = parser.parse_args()

    # Execute appropriate command
    if args.list:
        cmd_list(args)
    elif args.search:
        cmd_search(args)
    else:
        cmd_backup(args)


if __name__ == "__main__":
    main()
