#!/usr/bin/env python3
"""
Claude Sessions - Backup and analyze Claude Code conversation sessions.

This is the main entry point for the claude-sessions CLI tool.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

try:
    from backup import BackupManager
    from formatters import FormatConverter
    from stats import StatisticsGenerator
    from prompts import PromptsExtractor
except ImportError:
    from .backup import BackupManager
    from .formatters import FormatConverter
    from .stats import StatisticsGenerator
    from .prompts import PromptsExtractor


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


def parse_formats(format_str: str) -> list:
    """Parse comma-separated format string into list."""
    valid_formats = {"markdown", "html", "data"}
    formats = [f.strip().lower() for f in format_str.split(",")]

    invalid = set(formats) - valid_formats
    if invalid:
        print(f"Warning: Invalid formats ignored: {invalid}")
        formats = [f for f in formats if f in valid_formats]

    return formats if formats else list(valid_formats)


def cmd_backup(args):
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


def cmd_list(args):
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
            if project_dir.is_dir() and project_dir.name not in ["stats.html", "stats.json"]:
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


def main():
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

Environment Variables:
  OUTPUT_DIR    Default output directory for backups

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

    args = parser.parse_args()

    # Execute appropriate command
    if args.list:
        cmd_list(args)
    else:
        cmd_backup(args)


if __name__ == "__main__":
    main()
