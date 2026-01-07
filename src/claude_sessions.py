#!/usr/bin/env python3
"""
Claude Sessions - Backup and analyze Claude Code conversation sessions.

This is the main entry point for the claude-sessions CLI tool.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

try:
    from backup import BackupManager
    from formatters import FormatConverter
    from stats import StatisticsGenerator
    from prompts import PromptsExtractor
    from search_conversations import ConversationSearcher
except ImportError:
    from .backup import BackupManager
    from .formatters import FormatConverter
    from .stats import StatisticsGenerator
    from .prompts import PromptsExtractor
    from .search_conversations import ConversationSearcher


# Constants
DEFAULT_INPUT_DIR = Path.home() / ".claude" / "projects"
DEFAULT_FORMATS = "markdown,html,data"
ENV_OUTPUT_DIR = "OUTPUT_DIR"


def get_output_dir(args_output: Optional[str]) -> Path:
    """Get output directory from args, env var, or prompt user."""
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
    """Parse comma-separated format string into list."""
    valid_formats = {"markdown", "html", "data"}
    formats = [f.strip().lower() for f in format_str.split(",")]

    invalid = set(formats) - valid_formats
    if invalid:
        print(f"Warning: Invalid formats ignored: {invalid}")
        formats = [f for f in formats if f in valid_formats]

    return formats if formats else list(valid_formats)


def cmd_backup(args: argparse.Namespace) -> None:
    """Execute backup command."""
    input_dir = Path(args.input).expanduser()
    output_dir = get_output_dir(args.output)
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

    # Create output directory if needed
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
    """Execute search command."""
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
    """Execute list command."""
    input_dir = Path(args.input).expanduser()
    output_dir = Path(args.output).expanduser() if args.output else None

    if not output_dir:
        env_output = os.environ.get(ENV_OUTPUT_DIR)
        if env_output:
            output_dir = Path(env_output).expanduser()

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
    """Main entry point."""
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
  <output>/
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
