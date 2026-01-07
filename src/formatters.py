#!/usr/bin/env python3
"""
Format converters for Claude Sessions.

This module converts JSONL session files to human-readable and machine-processable
formats including Markdown, HTML, and structured JSON. It supports incremental
conversion - only processing files when the source has been modified.

Supported Output Formats:
    - markdown: Human-readable conversation log with collapsible thinking blocks
    - html: Styled single-page document with color-coded message types
    - data: Structured JSON with metadata, statistics, and full message array

Output Directory Structure:
    project_dir/
    ├── session1.jsonl          # Source file
    ├── markdown/
    │   └── session1.md         # Markdown output
    ├── html/
    │   └── session1.html       # HTML output
    └── data/
        └── session1.json       # Structured data output

Incremental Conversion:
    Files are only regenerated when:
    - Output file doesn't exist
    - Output file is older than input JSONL file (by mtime)

For format specifications and examples, see:
    docs/ARCHITECTURE.md (Output Formats section)

For JSONL input format, see:
    docs/JSONL_FORMAT.md

Example:
    >>> from formatters import FormatConverter
    >>> converter = FormatConverter()
    >>> result = converter.convert_all(Path("./output"), ["markdown", "html"])
    >>> print(f"Converted {result['markdown']} files to markdown")

Classes:
    FormatConverter: Handles conversion to all output formats

Constants:
    INDENT: JSON indentation level for pretty-printing (2 spaces)
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, List

from .parser import SessionParser
from .utils import iter_project_dirs, parse_timestamp
from .html_generator import SHARED_CSS


# Constants
INDENT = 2


class FormatConverter:
    """
    Converts Claude session files to various output formats.

    This class handles the transformation of raw JSONL session data into
    formatted outputs suitable for reading (Markdown, HTML) or programmatic
    processing (JSON data files).

    The converter uses SessionParser to read and normalize JSONL data, then
    applies format-specific rendering logic to generate the outputs.

    Supported Formats:
        - markdown: GitHub-flavored markdown with:
            - Session metadata header
            - User/Claude message sections
            - Collapsible <details> for thinking blocks
            - JSON-formatted tool calls in code blocks
            - Truncated tool outputs (2000 char limit)

        - html: Self-contained HTML page with:
            - Inline CSS styling (no external dependencies)
            - Color-coded message types (blue=user, green=assistant, orange=tool)
            - Responsive design for various screen sizes
            - Collapsible thinking sections

        - data: Structured JSON containing:
            - Session metadata (id, source_file, start/end times)
            - Computed statistics (message counts, token usage)
            - Complete message array for programmatic access

    Attributes:
        parser (SessionParser): Parser instance for reading JSONL files

    Example:
        >>> converter = FormatConverter()
        >>> stats = converter.convert_all(Path("./output"), ["markdown", "html", "data"])
        >>> print(f"Markdown: {stats['markdown']}, HTML: {stats['html']}")
        >>> print(f"Skipped {stats['skipped']} unchanged files")
    """

    def __init__(self) -> None:
        """Initialize converter with a SessionParser instance."""
        self.parser = SessionParser()

    def convert_all(self, output_dir: Path, formats: List[str]) -> Dict[str, int]:
        """
        Convert all JSONL files in output directory to specified formats.

        Iterates through all project directories (using iter_project_dirs),
        creating format subdirectories as needed. Each JSONL file is parsed
        once and written to all requested formats.

        Uses incremental conversion - skips files where all output formats
        are newer than the input JSONL file.

        Args:
            output_dir: Root output directory containing project folders.
                        Each project folder should contain *.jsonl files.
            formats: List of formats to generate. Valid values:
                     'markdown', 'html', 'data'

        Returns:
            dict: Conversion statistics with keys:
                - One key per format (int): Number of files converted
                - 'skipped' (int): Number of files skipped (up-to-date)

        Example:
            >>> result = converter.convert_all(Path("./output"), ["markdown", "html"])
            >>> # result = {'markdown': 5, 'html': 5, 'skipped': 10}
        """
        result = {fmt: 0 for fmt in formats}
        result["skipped"] = 0

        for project_dir in iter_project_dirs(output_dir):
            # Create format subdirectories
            for fmt in formats:
                (project_dir / fmt).mkdir(exist_ok=True)

            # Process each JSONL file
            for jsonl_file in project_dir.glob("*.jsonl"):
                session_id = jsonl_file.stem
                input_mtime = jsonl_file.stat().st_mtime

                # Check if conversion is needed (incremental)
                needs_conversion = self._needs_conversion(
                    project_dir, session_id, formats, input_mtime
                )

                if not needs_conversion:
                    result["skipped"] += 1
                    continue

                # Parse the file once
                messages = self.parser.parse_file_as_dicts(jsonl_file)
                if not messages:
                    continue

                if "markdown" in formats:
                    md_path = project_dir / "markdown" / f"{session_id}.md"
                    self._write_markdown(messages, md_path, session_id)
                    result["markdown"] += 1

                if "html" in formats:
                    html_path = project_dir / "html" / f"{session_id}.html"
                    self._write_html(messages, html_path, session_id)
                    result["html"] += 1

                if "data" in formats:
                    data_path = project_dir / "data" / f"{session_id}.json"
                    self._write_data(messages, data_path, session_id, jsonl_file)
                    result["data"] += 1

        return result

    def _needs_conversion(
        self, project_dir: Path, session_id: str, formats: List[str], input_mtime: float
    ) -> bool:
        """
        Check if any output format needs to be regenerated.

        Compares the modification time of each potential output file against
        the input file's mtime. If any output is missing or older, conversion
        is needed.

        Args:
            project_dir: Project directory containing the JSONL file
            session_id: Session ID (JSONL filename without extension)
            formats: List of formats to check
            input_mtime: Modification timestamp of input JSONL file

        Returns:
            True if any output file is missing or older than input,
            False if all outputs are up-to-date
        """
        format_paths = {
            "markdown": project_dir / "markdown" / f"{session_id}.md",
            "html": project_dir / "html" / f"{session_id}.html",
            "data": project_dir / "data" / f"{session_id}.json",
        }

        for fmt in formats:
            output_path = format_paths.get(fmt)
            if output_path:
                if not output_path.exists():
                    return True
                if output_path.stat().st_mtime < input_mtime:
                    return True

        return False

    def _write_markdown(self, messages: List[Dict[str, Any]], output_path: Path, session_id: str) -> None:
        """
        Write messages as GitHub-flavored Markdown file.

        Generates a readable conversation log with:
        - Header with session ID and date
        - ## headings for User and Claude messages
        - Collapsible <details> blocks for Claude's thinking
        - JSON-formatted tool inputs in code blocks
        - Truncated tool outputs (max 2000 chars)
        - --- separators between messages

        Args:
            messages: List of parsed message dictionaries
            output_path: Path for output .md file
            session_id: Session identifier for header
        """
        with open(output_path, "w", encoding="utf-8") as f:
            # Header
            f.write("# Claude Conversation Log\n\n")
            f.write(f"**Session ID:** `{session_id}`\n\n")

            # Get timestamp from first message
            if messages and messages[0].get("timestamp"):
                dt = parse_timestamp(messages[0]["timestamp"])
                if dt:
                    f.write(f"**Date:** {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")

            f.write("---\n\n")

            # Messages
            for msg in messages:
                msg_type = msg.get("type")

                if msg_type == "user":
                    f.write("## User\n\n")
                    f.write(f"{msg.get('content', '')}\n\n")

                elif msg_type == "assistant":
                    f.write("## Claude\n\n")

                    # Include thinking if present
                    thinking = msg.get("thinking")
                    if thinking:
                        f.write("<details>\n<summary>Thinking</summary>\n\n")
                        f.write(f"{thinking}\n\n")
                        f.write("</details>\n\n")

                    f.write(f"{msg.get('content', '')}\n\n")

                    # Tool calls
                    tool_calls = msg.get("tool_calls")
                    if tool_calls:
                        for tool in tool_calls:
                            f.write(f"**Tool:** `{tool.get('name', 'unknown')}`\n\n")
                            f.write("```json\n")
                            f.write(json.dumps(tool.get("input", {}), indent=INDENT, ensure_ascii=False))
                            f.write("\n```\n\n")

                elif msg_type == "tool_use":
                    f.write(f"### Tool: {msg.get('tool_name', 'unknown')}\n\n")
                    f.write("```json\n")
                    f.write(json.dumps(msg.get("tool_input", {}), indent=INDENT, ensure_ascii=False))
                    f.write("\n```\n\n")

                elif msg_type == "tool_result":
                    f.write("### Tool Result\n\n")
                    output = msg.get("output", "")
                    error = msg.get("error")
                    if error:
                        f.write(f"**Error:** {error}\n\n")
                    if output:
                        f.write("```\n")
                        f.write(output[:2000])  # Truncate long outputs
                        if len(output) > 2000:
                            f.write(f"\n... (truncated, {len(output)} chars total)")
                        f.write("\n```\n\n")

                f.write("---\n\n")

    def _write_html(self, messages: List[Dict[str, Any]], output_path: Path, session_id: str) -> None:
        """
        Write messages as self-contained HTML file.

        Generates a styled HTML document with:
        - Navigation bar linking to index and stats pages
        - Shared CSS design system for consistency
        - Color-coded message cards with left border accents
        - Responsive layout (max-width: 900px, centered)
        - Collapsible <details> for thinking blocks
        - Pre-formatted tool inputs/outputs

        Color scheme:
        - User messages: Blue (#3b82f6)
        - Assistant messages: Green (#10b981)
        - Tool operations: Orange (#f59e0b)

        Args:
            messages: List of parsed message dictionaries
            output_path: Path for output .html file
            session_id: Session identifier for page title and header
        """
        # Get metadata
        timestamp_str = ""
        if messages and messages[0].get("timestamp"):
            dt = parse_timestamp(messages[0]["timestamp"])
            if dt:
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        # Session-specific CSS additions
        session_css = """
.messages-container { max-width: 900px; margin: 0 auto; }
.session-header {
    background: var(--card);
    padding: 24px;
    border-radius: var(--radius);
    margin-bottom: 24px;
    box-shadow: var(--shadow);
}
.session-header h1 { font-size: 1.5rem; margin: 0 0 12px 0; }
.session-meta { display: flex; gap: 24px; flex-wrap: wrap; font-size: 0.875rem; color: var(--muted); }
.session-meta span { display: flex; align-items: center; gap: 6px; }
.message {
    background: var(--card);
    padding: 16px 20px;
    margin-bottom: 16px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow);
}
.message.user { border-left: 4px solid var(--user-color); }
.message.assistant { border-left: 4px solid var(--assistant-color); }
.message.tool { border-left: 4px solid var(--tool-color); background: #fffbf5; }
.role {
    font-weight: 600;
    font-size: 0.875rem;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.role-user { color: var(--user-color); }
.role-assistant { color: var(--assistant-color); }
.role-tool { color: var(--tool-color); }
.content { white-space: pre-wrap; word-wrap: break-word; line-height: 1.7; }
.thinking {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    margin-bottom: 12px;
    font-size: 0.9em;
    color: var(--text-secondary);
}
.thinking summary { cursor: pointer; font-weight: 600; }
pre {
    background: var(--bg-alt);
    padding: 12px;
    border-radius: var(--radius-sm);
    overflow-x: auto;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.85em;
    border: 1px solid var(--border);
}
code {
    background: var(--bg-alt);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
}
"""

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Session {html.escape(session_id[:16])} - Claude Sessions</title>
    <style>{SHARED_CSS}{session_css}</style>
</head>
<body>
    <nav class="nav">
        <div class="nav-content">
            <div class="nav-brand">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                </svg>
                Claude Sessions
            </div>
            <div class="nav-links">
                <a href="../../index.html">Browse</a>
                <a href="../../stats.html">Statistics</a>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="session-header">
            <h1>Conversation Log</h1>
            <div class="session-meta">
                <span><strong>Session:</strong> {html.escape(session_id[:24])}...</span>
                <span><strong>Date:</strong> {html.escape(timestamp_str)}</span>
                <span><strong>Messages:</strong> {len(messages)}</span>
            </div>
        </div>

        <div class="messages-container">
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

            for msg in messages:
                msg_type = msg.get("type")
                content = html.escape(msg.get("content", ""))

                if msg_type == "user":
                    f.write('            <div class="message user">\n')
                    f.write('                <div class="role role-user">User</div>\n')
                    f.write(f'                <div class="content">{content}</div>\n')
                    f.write('            </div>\n')

                elif msg_type == "assistant":
                    f.write('            <div class="message assistant">\n')
                    f.write('                <div class="role role-assistant">Claude</div>\n')

                    # Thinking
                    thinking = msg.get("thinking")
                    if thinking:
                        f.write('                <details class="thinking">\n')
                        f.write('                    <summary>Thinking</summary>\n')
                        f.write(f'                    <p>{html.escape(thinking)}</p>\n')
                        f.write('                </details>\n')

                    f.write(f'                <div class="content">{content}</div>\n')
                    f.write('            </div>\n')

                elif msg_type in ["tool_use", "tool_result"]:
                    f.write('            <div class="message tool">\n')
                    if msg_type == "tool_use":
                        tool_name = html.escape(msg.get("tool_name", "unknown"))
                        f.write(f'                <div class="role role-tool">Tool: {tool_name}</div>\n')
                        tool_input = json.dumps(msg.get("tool_input", {}), indent=INDENT, ensure_ascii=False)
                        f.write(f'                <pre>{html.escape(tool_input)}</pre>\n')
                    else:
                        f.write('                <div class="role role-tool">Tool Result</div>\n')
                        output = html.escape(msg.get("output", "")[:2000])
                        f.write(f'                <pre>{output}</pre>\n')
                    f.write('            </div>\n')

            f.write("""        </div>

        <div class="footer">
            <p>Generated by Claude Sessions</p>
        </div>
    </div>
</body>
</html>""")

    def _write_data(self, messages: List[Dict[str, Any]], output_path: Path, session_id: str, source_file: Path) -> None:
        """
        Write messages as structured JSON data file.

        Generates a JSON file with three sections:
        - metadata: Session identification and timing info
        - statistics: Computed message counts and token usage
        - messages: Complete array of parsed messages

        Output structure:
            {
                "metadata": {
                    "session_id": "...",
                    "source_file": "/path/to/source.jsonl",
                    "start_time": "2024-01-15T10:00:00+00:00",
                    "end_time": "2024-01-15T11:00:00+00:00"
                },
                "statistics": {
                    "total_messages": 42,
                    "user_messages": 20,
                    "assistant_messages": 22,
                    "total_input_tokens": 5000,
                    "total_output_tokens": 10000,
                    "total_tokens": 15000
                },
                "messages": [...]
            }

        Args:
            messages: List of parsed message dictionaries
            output_path: Path for output .json file
            session_id: Session identifier
            source_file: Path to original JSONL file (stored in metadata)
        """
        # Get session metadata from first message
        metadata = {}
        if messages:
            first = messages[0]
            metadata = {
                "session_id": first.get("session_id") or session_id,
                "source_file": str(source_file),
            }

            if first.get("timestamp"):
                dt = parse_timestamp(first["timestamp"])
                if dt:
                    metadata["start_time"] = dt.isoformat()

        # Get end time from last message
        if messages and messages[-1].get("timestamp"):
            dt = parse_timestamp(messages[-1]["timestamp"])
            if dt:
                metadata["end_time"] = dt.isoformat()

        # Calculate statistics
        user_messages = [m for m in messages if m.get("type") == "user"]
        assistant_messages = [m for m in messages if m.get("type") == "assistant"]

        total_input_tokens = 0
        total_output_tokens = 0
        for msg in assistant_messages:
            usage = msg.get("usage")
            if usage:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)

        output_data = {
            "metadata": metadata,
            "statistics": {
                "total_messages": len(messages),
                "user_messages": len(user_messages),
                "assistant_messages": len(assistant_messages),
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
            },
            "messages": messages,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=INDENT, ensure_ascii=False)
