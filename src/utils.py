#!/usr/bin/env python3
"""
Shared utilities for Claude Sessions.

This module provides common functions used across multiple modules to avoid
code duplication and ensure consistent behavior. It includes:

- Text extraction from Claude API content formats
- Timestamp parsing for ISO 8601 format with UTC timezone
- Project directory iteration with format subdirectory filtering

For the complete Claude JSONL format specification, see:
    docs/JSONL_FORMAT.md

For architecture overview, see:
    docs/ARCHITECTURE.md

Example:
    >>> from utils import extract_text, parse_timestamp, iter_project_dirs
    >>> text = extract_text([{"type": "text", "text": "Hello"}])
    >>> dt = parse_timestamp("2024-01-15T10:00:00.000Z")
    >>> for project in iter_project_dirs(Path("/output")):
    ...     print(project.name)
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Generator, List, Optional, Union


# Directories to skip when iterating over project folders.
# These are format subdirectories created by FormatConverter,
# not actual project directories.
SKIP_DIRS = {"markdown", "html", "data"}


def extract_text(content: Union[str, List[Any], Any]) -> str:
    """
    Extract text from various Claude API content formats.

    Claude Code stores message content in different formats depending on
    the message type and content. This function normalizes all formats
    to a plain text string.

    Supported formats:
        - Plain string: Returned as-is
        - Array of content blocks: Text extracted from blocks with type="text"
        - Other types: Returns empty string

    The array format is used when messages contain mixed content (text + images,
    text + tool calls, etc.). Each block in the array has a "type" field.

    Args:
        content: Message content in any supported format:
            - str: Plain text message
            - list: Array of content blocks [{"type": "text", "text": "..."}]
            - Any: Other types return empty string

    Returns:
        Extracted text as a single string. Multiple text blocks are joined
        with newlines. Returns empty string if no text content found.

    Example:
        >>> extract_text("Hello")
        'Hello'
        >>> extract_text([{"type": "text", "text": "Hello"}, {"type": "image", ...}])
        'Hello'
        >>> extract_text([{"type": "text", "text": "Line 1"}, {"type": "text", "text": "Line 2"}])
        'Line 1\\nLine 2'

    See Also:
        docs/JSONL_FORMAT.md for complete content format specification
    """
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
            elif isinstance(item, str):
                text_parts.append(item)
        return "\n".join(text_parts)
    return ""


def parse_timestamp(timestamp_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO 8601 timestamp string to datetime object.

    Claude Code uses ISO 8601 timestamps with UTC timezone, indicated by
    the 'Z' suffix. This function converts the 'Z' to '+00:00' for
    compatibility with Python's fromisoformat().

    Args:
        timestamp_str: ISO 8601 timestamp string with 'Z' suffix, or None.
            Expected format: "YYYY-MM-DDTHH:mm:ss.sssZ"
            Example: "2024-01-15T10:30:00.000Z"

    Returns:
        datetime: Timezone-aware datetime object in UTC, or
        None: If timestamp_str is None, empty, or cannot be parsed

    Example:
        >>> dt = parse_timestamp("2024-01-15T10:30:00.000Z")
        >>> dt.isoformat()
        '2024-01-15T10:30:00+00:00'
        >>> parse_timestamp(None)
        None
        >>> parse_timestamp("invalid")
        None

    Note:
        The function silently returns None on parse errors rather than
        raising exceptions, allowing callers to handle missing/invalid
        timestamps gracefully.
    """
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return None


def iter_project_dirs(output_dir: Path) -> Generator[Path, None, None]:
    """
    Iterate over project directories in the output folder.

    This generator yields project directories while skipping:
    - Non-directory entries (files)
    - Format subdirectories (markdown, html, data) created by FormatConverter
    - The output directory itself if it doesn't exist

    The output directory structure is:
        output_dir/
        ├── stats.html           # (skipped - not a directory)
        ├── stats.json           # (skipped - not a directory)
        ├── project-hash-1/      # (yielded)
        │   ├── session.jsonl
        │   ├── markdown/        # (NOT yielded when iterating project-hash-1)
        │   ├── html/
        │   └── data/
        └── project-hash-2/      # (yielded)

    Args:
        output_dir: Output directory containing project folders.
            Typically the backup destination directory.

    Yields:
        Path: Each project directory as a Path object.
            Directories are yielded in filesystem order (not sorted).

    Example:
        >>> for project in iter_project_dirs(Path("/backups")):
        ...     jsonl_files = list(project.glob("*.jsonl"))
        ...     print(f"{project.name}: {len(jsonl_files)} sessions")

    Note:
        This function is used by FormatConverter, StatisticsGenerator,
        and PromptsExtractor to process all projects consistently.
        Modification of SKIP_DIRS affects all these modules.
    """
    if not output_dir.exists():
        return

    for project_dir in output_dir.iterdir():
        if not project_dir.is_dir():
            continue
        if project_dir.name in SKIP_DIRS:
            continue
        yield project_dir
