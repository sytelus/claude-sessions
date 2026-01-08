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
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from parser import SessionParser
from utils import iter_project_dirs, parse_timestamp
from html_generator import SHARED_CSS


# Constants
INDENT = 2


def markdown_to_html(text: str) -> str:
    """
    Convert markdown text to HTML.

    Supports code blocks, inline code, bold, italic, headers, links, blockquotes,
    unordered lists, ordered lists, and tables.
    """
    if not text:
        return ""

    # Preserve code blocks with placeholders
    code_blocks = []

    def save_code_block(match):
        lang = match.group(1) or ""
        code = match.group(2)
        idx = len(code_blocks)
        code_blocks.append((lang, code))
        return f"%%CODE_BLOCK_{idx}%%"

    result = re.sub(r"```(\w*)\n?([\s\S]*?)```", save_code_block, text)

    # Preserve tables with placeholders (before HTML escaping)
    tables = []

    def save_table(match):
        table_text = match.group(0)
        idx = len(tables)
        tables.append(table_text)
        return f"%%TABLE_{idx}%%"

    # Match markdown tables: header row, separator row, and data rows
    result = re.sub(
        r'^\|[^\n]+\|\n\|[-:\| ]+\|\n(?:\|[^\n]+\|\n?)+',
        save_table,
        result,
        flags=re.MULTILINE
    )

    # Escape HTML
    result = html.escape(result)

    # Inline code
    result = re.sub(r"`([^`]+)`", r'<code>\1</code>', result)

    # Bold and italic
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)
    result = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", result)

    # Headers
    result = re.sub(r"^### (.+)$", r"<h4>\1</h4>", result, flags=re.MULTILINE)
    result = re.sub(r"^## (.+)$", r"<h3>\1</h3>", result, flags=re.MULTILINE)
    result = re.sub(r"^# (.+)$", r"<h2>\1</h2>", result, flags=re.MULTILINE)

    # Links
    result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank">\1</a>', result)

    # Blockquotes
    result = re.sub(r"^&gt; (.+)$", r"<blockquote>\1</blockquote>", result, flags=re.MULTILINE)

    # Unordered lists (lines starting with - or *)
    result = re.sub(r"^[\-\*] (.+)$", r"<li>\1</li>", result, flags=re.MULTILINE)
    # Wrap consecutive <li> items in <ul>
    result = re.sub(r"((?:<li>.*?</li>\n?)+)", r"<ul>\1</ul>", result)

    # Ordered lists (lines starting with number.)
    result = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", result, flags=re.MULTILINE)

    # Restore tables as HTML
    for idx, table_text in enumerate(tables):
        html_table = _convert_markdown_table(table_text)
        result = result.replace(f"%%TABLE_{idx}%%", html_table)

    # Restore code blocks with syntax highlighting
    for idx, (lang, code) in enumerate(code_blocks):
        lang_class = f' class="language-{lang}"' if lang else ""
        escaped_code = html.escape(code)
        # Apply basic highlighting
        highlighted = syntax_highlight(escaped_code, lang)
        replacement = f'<pre{lang_class}><code>{highlighted}</code></pre>'
        result = result.replace(f"%%CODE_BLOCK_{idx}%%", replacement)

    return result


def _convert_markdown_table(table_text: str) -> str:
    """
    Convert a markdown table to HTML table.

    Args:
        table_text: Raw markdown table text

    Returns:
        HTML table string
    """
    lines = table_text.strip().split('\n')
    if len(lines) < 2:
        return html.escape(table_text)

    # Parse header row
    header_cells = [cell.strip() for cell in lines[0].strip('|').split('|')]

    # Parse alignment from separator row
    separator = lines[1]
    alignments = []
    for cell in separator.strip('|').split('|'):
        cell = cell.strip()
        if cell.startswith(':') and cell.endswith(':'):
            alignments.append('center')
        elif cell.endswith(':'):
            alignments.append('right')
        else:
            alignments.append('left')

    # Build HTML table
    html_parts = ['<table class="md-table">']

    # Header
    html_parts.append('<thead><tr>')
    for i, cell in enumerate(header_cells):
        align = alignments[i] if i < len(alignments) else 'left'
        html_parts.append(f'<th style="text-align:{align}">{html.escape(cell)}</th>')
    html_parts.append('</tr></thead>')

    # Body rows
    html_parts.append('<tbody>')
    for line in lines[2:]:
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        html_parts.append('<tr>')
        for i, cell in enumerate(cells):
            align = alignments[i] if i < len(alignments) else 'left'
            html_parts.append(f'<td style="text-align:{align}">{html.escape(cell)}</td>')
        html_parts.append('</tr>')
    html_parts.append('</tbody>')

    html_parts.append('</table>')
    return ''.join(html_parts)


def syntax_highlight(code: str, lang: str) -> str:
    """Apply basic syntax highlighting to code."""
    if not lang:
        return code

    lang_lower = lang.lower()
    if lang_lower in ['js', 'jsx']:
        lang_lower = 'javascript'
    elif lang_lower in ['ts', 'tsx']:
        lang_lower = 'typescript'
    elif lang_lower == 'py':
        lang_lower = 'python'

    keywords = {
        'python': ['def', 'class', 'import', 'from', 'return', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'with', 'as', 'in', 'not', 'and', 'or', 'True', 'False', 'None', 'async', 'await'],
        'javascript': ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'class', 'import', 'export', 'async', 'await', 'true', 'false', 'null'],
        'typescript': ['function', 'const', 'let', 'var', 'return', 'if', 'else', 'for', 'while', 'class', 'import', 'export', 'async', 'await', 'true', 'false', 'null', 'interface', 'type'],
    }

    kws = keywords.get(lang_lower, [])
    result = code

    # Highlight comments
    result = re.sub(r'(#[^\n]*)', r'<span class="comment">\1</span>', result)
    result = re.sub(r'(//[^\n]*)', r'<span class="comment">\1</span>', result)

    # Highlight strings
    result = re.sub(r'(&quot;[^&]*&quot;)', r'<span class="string">\1</span>', result)

    # Highlight keywords
    for kw in kws:
        result = re.sub(rf'\b({kw})\b', r'<span class="keyword">\1</span>', result)

    # Highlight numbers
    result = re.sub(r'\b(\d+\.?\d*)\b', r'<span class="number">\1</span>', result)

    return result


def render_diff(content: str) -> str:
    """Render diff content with proper styling."""
    lines = content.split('\n')
    result = []
    for line in lines:
        escaped = html.escape(line)
        if line.startswith('+') and not line.startswith('+++'):
            result.append(f'<span class="diff-add">{escaped}</span>')
        elif line.startswith('-') and not line.startswith('---'):
            result.append(f'<span class="diff-del">{escaped}</span>')
        elif line.startswith('@@'):
            result.append(f'<span class="diff-info">{escaped}</span>')
        else:
            result.append(escaped)
    return '\n'.join(result)


def is_diff_content(content: str) -> bool:
    """Check if content looks like a diff."""
    if not content:
        return False
    lines = content.split('\n')[:20]
    diff_patterns = sum(1 for line in lines if (
        line.startswith('diff --git') or line.startswith('--- ') or
        line.startswith('+++ ') or (line.startswith('@@') and '@@' in line[2:])
    ))
    return diff_patterns >= 2


def format_duration_human(minutes: Optional[float]) -> str:
    """Format duration in human-readable format."""
    if minutes is None:
        return ""
    if minutes < 1:
        return "<1 min"
    if minutes < 60:
        return f"{int(minutes)} min"
    if minutes < 1440:
        hours = minutes / 60
        return f"{hours:.1f} hrs"
    days = minutes / 1440
    return f"{days:.1f} days"


def _is_lightweight_assistant_msg(msg: Dict[str, Any]) -> bool:
    """
    Check if an assistant message is "lightweight" and should be grouped.

    A lightweight message has one of:
    - Only thinking (no content or tool calls)
    - Only tool calls (no content)
    - Very short content (<100 chars) that looks like a transition phrase

    Args:
        msg: Assistant message dictionary

    Returns:
        True if message should be grouped with neighbors
    """
    if msg.get("type") != "assistant":
        return False

    content = msg.get("content", "").strip()
    thinking = msg.get("thinking")
    tool_calls = msg.get("tool_calls")

    # Only thinking block
    if thinking and not content and not tool_calls:
        return True

    # Only tool calls
    if tool_calls and not content:
        return True

    # Short transitional content
    if len(content) < 100 and not thinking:
        # Check for common transitional phrases
        transitional = [
            "let me", "i'll", "i will", "now", "next",
            "looking at", "checking", "reading", "searching",
            "the file", "here's", "here is", "done"
        ]
        content_lower = content.lower()
        if any(phrase in content_lower for phrase in transitional):
            return True

    return False


def _get_tool_detail(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Extract a brief description of what a tool is doing.

    Args:
        tool_name: Name of the tool
        tool_input: Tool input parameters

    Returns:
        Short description string
    """
    if tool_name in ("Read", "Edit", "Write"):
        return tool_input.get("file_path", "")[:50]
    elif tool_name == "Bash":
        return tool_input.get("command", "")[:60]
    elif tool_name == "Grep":
        return f"pattern: {tool_input.get('pattern', '')[:30]}"
    elif tool_name == "Glob":
        return tool_input.get("pattern", "")[:40]
    elif tool_name == "Task":
        return tool_input.get("description", "")[:40]
    else:
        return str(tool_input)[:50]


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

    def convert_all(self, output_dir: Path, formats: List[str], force: bool = False) -> Dict[str, int]:
        """
        Convert all JSONL files in output directory to specified formats.

        Iterates through all project directories (using iter_project_dirs),
        creating format subdirectories as needed. Each JSONL file is parsed
        once and written to all requested formats.

        Uses incremental conversion - skips files where all output formats
        are newer than the input JSONL file (unless force=True).

        Args:
            output_dir: Root output directory containing project folders.
                        Each project folder should contain *.jsonl files.
            formats: List of formats to generate. Valid values:
                     'markdown', 'html', 'data'
            force: If True, regenerate all files regardless of timestamps.
                   Default is False (incremental conversion).

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

                # Check if conversion is needed (incremental), skip check if force=True
                if not force:
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
        - Grouped consecutive tool calls for compact display
        - Markdown-to-HTML conversion for content
        - Diff rendering with syntax highlighting
        - Extended session statistics in header

        Args:
            messages: List of parsed message dictionaries
            output_path: Path for output .html file
            session_id: Session identifier for page title and header
        """
        # Calculate session statistics
        timestamps = [parse_timestamp(m.get("timestamp", "")) for m in messages if m.get("timestamp")]
        timestamps = [t for t in timestamps if t is not None]

        timestamp_str = ""
        duration_str = ""
        end_time_str = ""
        if timestamps:
            timestamp_str = min(timestamps).strftime("%Y-%m-%d %H:%M UTC")
            end_time_str = max(timestamps).strftime("%H:%M UTC")
            duration_mins = (max(timestamps) - min(timestamps)).total_seconds() / 60
            duration_str = format_duration_human(duration_mins)

        # Count message types and tokens
        user_msgs = sum(1 for m in messages if m.get("type") == "user")
        assistant_msgs = sum(1 for m in messages if m.get("type") == "assistant")
        tool_uses = sum(1 for m in messages if m.get("type") == "tool_use")
        tool_results = sum(1 for m in messages if m.get("type") == "tool_result")

        total_input_tokens = 0
        total_output_tokens = 0
        for msg in messages:
            usage = msg.get("usage")
            if usage:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)
        total_tokens = total_input_tokens + total_output_tokens

        # Count unique tools used
        tools_used = set()
        for m in messages:
            if m.get("type") == "tool_use":
                tools_used.add(m.get("tool_name", ""))
            if m.get("tool_calls"):
                for tc in m.get("tool_calls"):
                    tools_used.add(tc.get("name", ""))

        # Session-specific CSS with improved styling
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
.session-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.8rem; color: var(--muted); }
.session-meta span { display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: var(--bg-alt); border-radius: 4px; }
.session-meta strong { color: var(--text); }
.session-stats { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.stat-badge { font-size: 0.7rem; padding: 3px 8px; border-radius: 12px; background: var(--primary-light); color: var(--primary); }
.message {
    background: var(--card);
    padding: 16px 20px;
    margin-bottom: 12px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow);
    position: relative;
}
.message.user { border-left: 4px solid var(--user-color); }
.message.assistant { border-left: 4px solid var(--assistant-color); }
.message.tool { border-left: 4px solid var(--tool-color); background: #fffbf5; }
.message.tool-group { padding: 12px 16px; }
.role {
    font-weight: 600;
    font-size: 0.8rem;
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.role-user { color: var(--user-color); }
.role-user::before { content: '❯ '; }
.role-assistant { color: var(--assistant-color); }
.role-assistant::before { content: '◆ '; }
.role-tool { color: var(--tool-color); }
.role-tool::before { content: '⚙ '; }
.content {
    line-height: 1.7;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}
.content h2, .content h3, .content h4 { margin: 16px 0 8px 0; }
.content blockquote { border-left: 3px solid var(--border); padding-left: 12px; color: var(--muted); margin: 8px 0; }
/* Code styling */
pre {
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px;
    border-radius: var(--radius-sm);
    overflow-x: auto;
    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Courier New', monospace;
    font-size: 0.85em;
    border: 1px solid #333;
    margin: 8px 0;
}
pre code { background: none; padding: 0; }
code {
    background: var(--bg-alt);
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, 'Cascadia Code', 'Courier New', monospace;
    font-size: 0.9em;
}
.keyword { color: #c586c0; }
.string { color: #ce9178; }
.comment { color: #6a9955; }
.number { color: #b5cea8; }
/* Diff styling */
.diff-add { background: #22863a20; color: #22863a; display: block; }
.diff-del { background: #cb253720; color: #cb2537; display: block; }
.diff-info { color: #0366d6; font-weight: bold; display: block; }
[data-theme="dark"] .diff-add { background: #23863a30; color: #85e89d; }
[data-theme="dark"] .diff-del { background: #cb253730; color: #f97583; }
[data-theme="dark"] .diff-info { color: #79b8ff; }
/* Thinking */
.thinking {
    background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
    border: 1px solid #c4b5fd;
    border-radius: var(--radius-sm);
    padding: 12px;
    margin-bottom: 12px;
    font-size: 0.85em;
    color: #6b21a8;
}
[data-theme="dark"] .thinking {
    background: linear-gradient(135deg, #2e1065 0%, #1e1b4b 100%);
    border-color: #4c1d95;
    color: #c4b5fd;
}
.thinking summary { cursor: pointer; font-weight: 600; }
.thinking summary::before { content: '🧠 '; }
/* Tool calls */
.tool-call {
    background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
    color: #92400e;
    padding: 8px 12px;
    border-radius: var(--radius-sm);
    margin-top: 8px;
    font-size: 0.8rem;
    font-family: 'SF Mono', Monaco, monospace;
    border: 1px solid #f59e0b;
}
.tool-call::before { content: '⚡ '; }
[data-theme="dark"] .tool-call {
    background: linear-gradient(135deg, #451a03 0%, #78350f 100%);
    color: #fde68a;
    border-color: #b45309;
}
[data-theme="dark"] .message.tool { background: #2d2006; }
/* Tool group compact */
.tool-group-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.tool-group-badge {
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: var(--tool-color);
    color: white;
}
.tool-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.8rem;
}
.tool-item:last-child { border-bottom: none; }
.tool-item-name { font-weight: 600; color: var(--tool-color); min-width: 80px; }
.tool-item-detail { color: var(--muted); font-family: monospace; font-size: 0.75rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-item-status { margin-left: auto; font-size: 0.7rem; }
.tool-item-status.success { color: #22c55e; }
.tool-item-status.error { color: #ef4444; }
/* Collapsible details */
details.tool-details { margin-top: 8px; }
details.tool-details summary { cursor: pointer; font-size: 0.75rem; color: var(--muted); }
details.tool-details pre { margin-top: 8px; font-size: 0.75em; max-height: 200px; overflow-y: auto; }
/* Markdown tables */
.md-table {
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: 0.9em;
}
.md-table th, .md-table td {
    border: 1px solid var(--border);
    padding: 8px 12px;
}
.md-table th {
    background: var(--bg-alt);
    font-weight: 600;
}
.md-table tr:nth-child(even) {
    background: var(--bg-alt);
}
[data-theme="dark"] .md-table th {
    background: #2d2d2d;
}
[data-theme="dark"] .md-table tr:nth-child(even) {
    background: #1e1e1e;
}
/* Message anchors and links */
.message { scroll-margin-top: 80px; }
.message-anchor {
    color: var(--muted);
    text-decoration: none;
    opacity: 0;
    margin-left: 8px;
    font-size: 0.8em;
    transition: opacity 0.2s;
}
.message:hover .message-anchor { opacity: 0.5; }
.message-anchor:hover { opacity: 1 !important; color: var(--primary); }
/* Grouped assistant messages */
.message-group {
    background: var(--card);
    border-radius: var(--radius-sm);
    margin-bottom: 12px;
    box-shadow: var(--shadow);
    border-left: 4px solid var(--assistant-color);
}
.message-group-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    cursor: pointer;
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
}
[data-theme="dark"] .message-group-header {
    background: linear-gradient(135deg, #14532d 0%, #166534 100%);
}
.message-group-header:hover { filter: brightness(0.98); }
.message-group-badge {
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    background: var(--assistant-color);
    color: white;
}
.message-group-expand {
    margin-left: auto;
    font-size: 0.8rem;
    color: var(--muted);
    transition: transform 0.2s;
}
.message-group.expanded .message-group-expand { transform: rotate(90deg); }
.message-group-content {
    display: none;
    padding: 12px 16px;
    border-top: 1px solid var(--border);
}
.message-group.expanded .message-group-content { display: block; }
.grouped-item {
    padding: 8px 0;
    border-bottom: 1px solid var(--border);
}
.grouped-item:last-child { border-bottom: none; }
.grouped-item-label {
    font-size: 0.75rem;
    color: var(--muted);
    margin-bottom: 4px;
}
.grouped-thinking {
    font-size: 0.85em;
    color: #6b21a8;
    background: #f5f3ff;
    padding: 8px;
    border-radius: 4px;
    max-height: 150px;
    overflow-y: auto;
}
[data-theme="dark"] .grouped-thinking {
    background: #2e1065;
    color: #c4b5fd;
}
.grouped-content {
    font-size: 0.9em;
    color: var(--text);
}
.grouped-tools {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
}
.grouped-tool-chip {
    font-size: 0.75rem;
    padding: 2px 8px;
    border-radius: 4px;
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #f59e0b;
}
[data-theme="dark"] .grouped-tool-chip {
    background: #451a03;
    color: #fde68a;
    border-color: #b45309;
}
.timestamp {
    font-size: 0.7rem;
    color: var(--muted);
    position: absolute;
    top: 8px;
    right: 12px;
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
                <span><strong>Session:</strong> {html.escape(session_id[:20])}...</span>
                <span><strong>Date:</strong> {html.escape(timestamp_str)}</span>
                {f'<span><strong>Duration:</strong> {html.escape(duration_str)}</span>' if duration_str else ''}
            </div>
            <div class="session-stats">
                <span class="stat-badge">👤 {user_msgs} user</span>
                <span class="stat-badge">🤖 {assistant_msgs} assistant</span>
                <span class="stat-badge">🔧 {tool_uses} tool calls</span>
                <span class="stat-badge">📊 {total_tokens:,} tokens</span>
                {f'<span class="stat-badge">🛠️ {len(tools_used)} tools</span>' if tools_used else ''}
            </div>
        </div>

        <div class="messages-container">
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

            msg_counter = 0  # For generating unique message IDs
            group_counter = 0  # For generating unique group IDs
            i = 0

            while i < len(messages):
                msg = messages[i]
                msg_type = msg.get("type")

                # User message - always its own card with anchor
                if msg_type == "user":
                    msg_counter += 1
                    msg_id = f"msg-{msg_counter}"
                    content = markdown_to_html(msg.get("content", ""))
                    f.write(f'            <div class="message user" id="{msg_id}">\n')
                    f.write(f'                <div class="role role-user">User <a href="#{msg_id}" class="message-anchor">#</a></div>\n')
                    f.write(f'                <div class="content">{content}</div>\n')
                    f.write('            </div>\n')
                    i += 1

                # Check if we should group consecutive lightweight messages
                elif msg_type == "assistant" or msg_type in ["tool_use", "tool_result"]:
                    # Collect consecutive groupable items
                    group_items = []
                    start_i = i

                    while i < len(messages):
                        curr = messages[i]
                        curr_type = curr.get("type")

                        if curr_type == "user":
                            break  # User message ends the group

                        if curr_type == "assistant":
                            if _is_lightweight_assistant_msg(curr):
                                group_items.append(curr)
                                i += 1
                            else:
                                # Substantial assistant message
                                if group_items:
                                    break  # End group before this message
                                else:
                                    # Render as standalone
                                    break

                        elif curr_type in ["tool_use", "tool_result"]:
                            group_items.append(curr)
                            i += 1

                        else:
                            i += 1  # Skip unknown types

                    # If we collected a group, render it
                    if len(group_items) >= 2:
                        group_counter += 1
                        group_id = f"group-{group_counter}"
                        msg_counter += 1
                        msg_id = f"msg-{msg_counter}"

                        # Count items in group
                        thinking_count = sum(1 for g in group_items if g.get("type") == "assistant" and g.get("thinking"))
                        tool_count = sum(1 for g in group_items if g.get("type") == "tool_use")
                        text_count = sum(1 for g in group_items if g.get("type") == "assistant" and g.get("content", "").strip())

                        summary_parts = []
                        if thinking_count:
                            summary_parts.append(f"{thinking_count} thinking")
                        if tool_count:
                            summary_parts.append(f"{tool_count} tools")
                        if text_count:
                            summary_parts.append(f"{text_count} responses")
                        summary = ", ".join(summary_parts) or "Claude activity"

                        f.write(f'            <div class="message-group" id="{group_id}">\n')
                        f.write(f'                <div class="message-group-header" onclick="toggleMessageGroup(\'{group_id}\')">\n')
                        f.write(f'                    <span class="role role-assistant">Claude <a href="#{msg_id}" class="message-anchor" onclick="event.stopPropagation()">#</a></span>\n')
                        f.write(f'                    <span class="message-group-badge">{summary}</span>\n')
                        f.write(f'                    <span class="message-group-expand">▶</span>\n')
                        f.write('                </div>\n')
                        f.write('                <div class="message-group-content">\n')

                        for item in group_items:
                            item_type = item.get("type")
                            if item_type == "assistant":
                                thinking = item.get("thinking")
                                content = item.get("content", "").strip()
                                tool_calls = item.get("tool_calls")

                                if thinking:
                                    f.write('                    <div class="grouped-item">\n')
                                    f.write('                        <div class="grouped-item-label">Thinking</div>\n')
                                    truncated = thinking[:500] + ("..." if len(thinking) > 500 else "")
                                    f.write(f'                        <div class="grouped-thinking">{html.escape(truncated)}</div>\n')
                                    f.write('                    </div>\n')

                                if content:
                                    f.write('                    <div class="grouped-item">\n')
                                    f.write('                        <div class="grouped-item-label">Response</div>\n')
                                    f.write(f'                        <div class="grouped-content">{markdown_to_html(content)}</div>\n')
                                    f.write('                    </div>\n')

                                if tool_calls:
                                    f.write('                    <div class="grouped-item">\n')
                                    f.write('                        <div class="grouped-item-label">Tool Calls</div>\n')
                                    f.write('                        <div class="grouped-tools">\n')
                                    for tc in tool_calls:
                                        tool_name = html.escape(tc.get("name", "unknown"))
                                        f.write(f'                            <span class="grouped-tool-chip">{tool_name}</span>\n')
                                    f.write('                        </div>\n')
                                    f.write('                    </div>\n')

                            elif item_type == "tool_use":
                                tool_name = html.escape(item.get("tool_name", "unknown"))
                                tool_input = item.get("tool_input", {})
                                detail = _get_tool_detail(tool_name, tool_input)
                                f.write('                    <div class="grouped-item">\n')
                                f.write(f'                        <div class="grouped-item-label">Tool: {tool_name}</div>\n')
                                f.write(f'                        <div class="grouped-content" style="font-family:monospace;font-size:0.8em">{html.escape(detail)}</div>\n')
                                f.write('                    </div>\n')

                        f.write('                </div>\n')
                        f.write('            </div>\n')

                    elif i == start_i:
                        # No grouping happened, render the single message
                        if msg_type == "assistant":
                            thinking = msg.get("thinking")
                            tool_calls = msg.get("tool_calls")
                            content = msg.get("content", "")

                            if not content and not thinking and not tool_calls:
                                i += 1
                                continue

                            msg_counter += 1
                            msg_id = f"msg-{msg_counter}"
                            f.write(f'            <div class="message assistant" id="{msg_id}">\n')
                            f.write(f'                <div class="role role-assistant">Claude <a href="#{msg_id}" class="message-anchor">#</a></div>\n')

                            if thinking:
                                f.write('                <details class="thinking">\n')
                                f.write('                    <summary>Thinking</summary>\n')
                                f.write(f'                    <div>{html.escape(thinking[:3000])}{"..." if len(thinking) > 3000 else ""}</div>\n')
                                f.write('                </details>\n')

                            if content:
                                rendered = markdown_to_html(content)
                                f.write(f'                <div class="content">{rendered}</div>\n')

                            if tool_calls:
                                for tc in tool_calls:
                                    tool_name = html.escape(tc.get("name", "unknown"))
                                    f.write(f'                <div class="tool-call"><strong>{tool_name}</strong></div>\n')

                            f.write('            </div>\n')
                            i += 1

                        elif msg_type in ["tool_use", "tool_result"]:
                            # Single tool message - render compactly
                            msg_counter += 1
                            msg_id = f"msg-{msg_counter}"
                            if msg_type == "tool_use":
                                tool_name = html.escape(msg.get("tool_name", "unknown"))
                                tool_input = msg.get("tool_input", {})
                                detail = _get_tool_detail(tool_name, tool_input)
                                f.write(f'            <div class="message tool" id="{msg_id}">\n')
                                f.write(f'                <div class="role role-tool">Tool: {tool_name} <a href="#{msg_id}" class="message-anchor">#</a></div>\n')
                                f.write(f'                <div class="content" style="font-family:monospace;font-size:0.85em">{html.escape(detail)}</div>\n')
                                f.write('            </div>\n')
                            i += 1

                else:
                    i += 1  # Skip unknown message types

            f.write("""        </div>

        <div class="footer">
            <p>Generated by Claude Sessions</p>
        </div>
    </div>
    <script>
    function toggleMessageGroup(groupId) {
        const group = document.getElementById(groupId);
        if (group) {
            group.classList.toggle('expanded');
        }
    }
    </script>
</body>
</html>""")

    def _write_data(self, messages: List[Dict[str, Any]], output_path: Path, session_id: str, source_file: Path) -> None:
        """
        Write messages as structured JSON data file.

        Generates a comprehensive JSON file that serves as the source of truth
        for HTML rendering. Contains all computed statistics and metadata needed
        to regenerate HTML without re-processing the original JSONL.

        Output structure:
            {
                "metadata": {
                    "session_id": "...",
                    "source_file": "/path/to/source.jsonl",
                    "start_time": "2024-01-15T10:00:00+00:00",
                    "end_time": "2024-01-15T11:00:00+00:00",
                    "duration_minutes": 60.0
                },
                "statistics": {
                    "total_messages": 42,
                    "user_messages": 20,
                    "assistant_messages": 22,
                    "tool_uses": 15,
                    "tool_results": 15,
                    "total_input_tokens": 5000,
                    "total_output_tokens": 10000,
                    "total_tokens": 15000,
                    "cache_read_tokens": 1000,
                    "tools_used": ["Read", "Write", "Bash"]
                },
                "messages": [...]
            }

        Args:
            messages: List of parsed message dictionaries
            output_path: Path for output .json file
            session_id: Session identifier
            source_file: Path to original JSONL file (stored in metadata)
        """
        # Parse all timestamps for duration calculation
        timestamps = []
        for m in messages:
            if m.get("timestamp"):
                dt = parse_timestamp(m["timestamp"])
                if dt:
                    timestamps.append(dt)

        # Build metadata
        metadata = {
            "session_id": session_id,
            "source_file": str(source_file),
        }

        if messages:
            first = messages[0]
            if first.get("session_id"):
                metadata["session_id"] = first["session_id"]

        if timestamps:
            metadata["start_time"] = min(timestamps).isoformat()
            metadata["end_time"] = max(timestamps).isoformat()
            duration_mins = (max(timestamps) - min(timestamps)).total_seconds() / 60
            metadata["duration_minutes"] = round(duration_mins, 1)

        # Calculate comprehensive statistics
        user_messages = [m for m in messages if m.get("type") == "user"]
        assistant_messages = [m for m in messages if m.get("type") == "assistant"]
        tool_uses = [m for m in messages if m.get("type") == "tool_use"]
        tool_results = [m for m in messages if m.get("type") == "tool_result"]

        total_input_tokens = 0
        total_output_tokens = 0
        cache_read_tokens = 0
        for msg in messages:
            usage = msg.get("usage")
            if usage:
                total_input_tokens += usage.get("input_tokens", 0)
                total_output_tokens += usage.get("output_tokens", 0)
                cache_read_tokens += usage.get("cache_read_input_tokens", 0)

        # Collect unique tools used
        tools_used = set()
        for m in messages:
            if m.get("type") == "tool_use":
                tool_name = m.get("tool_name")
                if tool_name:
                    tools_used.add(tool_name)
            if m.get("tool_calls"):
                for tc in m.get("tool_calls"):
                    tool_name = tc.get("name")
                    if tool_name:
                        tools_used.add(tool_name)

        # Count tool errors
        tool_errors = sum(1 for m in tool_results if m.get("is_error"))

        output_data = {
            "metadata": metadata,
            "statistics": {
                "total_messages": len(messages),
                "user_messages": len(user_messages),
                "assistant_messages": len(assistant_messages),
                "tool_uses": len(tool_uses),
                "tool_results": len(tool_results),
                "tool_errors": tool_errors,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "total_tokens": total_input_tokens + total_output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "tools_used": sorted(list(tools_used)),
            },
            "messages": messages,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=INDENT, ensure_ascii=False)

    def regenerate_html_from_json(self, json_path: Path, html_path: Path) -> bool:
        """
        Regenerate HTML from an existing JSON data file.

        This enables the JSON + HTML renderer pattern where JSON is the
        source of truth and HTML can be regenerated without re-parsing JSONL.

        Args:
            json_path: Path to the JSON data file
            html_path: Path for the output HTML file

        Returns:
            True if HTML was successfully generated, False otherwise
        """
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            messages = data.get("messages", [])
            metadata = data.get("metadata", {})
            session_id = metadata.get("session_id", json_path.stem)

            self._write_html(messages, html_path, session_id)
            return True
        except Exception as e:
            print(f"  Error regenerating HTML from {json_path}: {e}")
            return False

    def regenerate_all_html(self, output_dir: Path) -> Dict[str, int]:
        """
        Regenerate all HTML files from existing JSON data files.

        Walks through the output directory and regenerates HTML for each
        project that has JSON data files. This is useful when HTML styling
        changes and you want to regenerate without re-processing JSONL.

        Args:
            output_dir: Root output directory containing project subdirectories

        Returns:
            Dictionary with counts: {"regenerated": N, "errors": M}
        """
        result = {"regenerated": 0, "errors": 0}

        for project_dir in output_dir.iterdir():
            if not project_dir.is_dir():
                continue

            data_dir = project_dir / "data"
            html_dir = project_dir / "html"

            if not data_dir.exists():
                continue

            html_dir.mkdir(parents=True, exist_ok=True)

            for json_file in data_dir.glob("*.json"):
                html_file = html_dir / f"{json_file.stem}.html"
                if self.regenerate_html_from_json(json_file, html_file):
                    result["regenerated"] += 1
                else:
                    result["errors"] += 1

        return result
