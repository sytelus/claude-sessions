#!/usr/bin/env python3
"""
Format converters for Claude Sessions.

Converts JSONL session files to markdown, HTML, and structured data formats.
"""

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Constants
INDENT = 2


class FormatConverter:
    """Converts Claude session files to various output formats."""

    def convert_all(self, output_dir: Path, formats: List[str]) -> Dict:
        """
        Convert all JSONL files in output directory to specified formats.

        Args:
            output_dir: Output directory containing project folders
            formats: List of formats to generate ('markdown', 'html', 'data')

        Returns:
            Dict with counts per format
        """
        result = {fmt: 0 for fmt in formats}

        for project_dir in output_dir.iterdir():
            if not project_dir.is_dir():
                continue

            # Skip stats files and format subdirectories
            if project_dir.name in ["markdown", "html", "data"]:
                continue

            # Create format subdirectories
            for fmt in formats:
                (project_dir / fmt).mkdir(exist_ok=True)

            # Process each JSONL file
            for jsonl_file in project_dir.glob("*.jsonl"):
                messages = self._parse_jsonl(jsonl_file)
                if not messages:
                    continue

                session_id = jsonl_file.stem

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

    def _parse_jsonl(self, jsonl_path: Path) -> List[Dict]:
        """Parse JSONL file and extract messages."""
        messages = []

        try:
            with open(jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        parsed = self._parse_entry(entry)
                        if parsed:
                            messages.append(parsed)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

        return messages

    def _parse_entry(self, entry: Dict) -> Optional[Dict]:
        """Parse a single JSONL entry into a normalized message."""
        entry_type = entry.get("type")

        if entry_type == "user":
            return self._parse_user_message(entry)
        elif entry_type == "assistant":
            return self._parse_assistant_message(entry)
        elif entry_type == "tool_use":
            return self._parse_tool_use(entry)
        elif entry_type == "tool_result":
            return self._parse_tool_result(entry)

        return None

    def _parse_user_message(self, entry: Dict) -> Optional[Dict]:
        """Parse user message entry."""
        message = entry.get("message", {})
        content = message.get("content", "")

        text = self._extract_text(content)
        if not text:
            return None

        return {
            "type": "user",
            "role": "user",
            "content": text,
            "timestamp": entry.get("timestamp"),
            "uuid": entry.get("uuid"),
            "session_id": entry.get("sessionId"),
        }

    def _parse_assistant_message(self, entry: Dict) -> Optional[Dict]:
        """Parse assistant message entry."""
        message = entry.get("message", {})
        content = message.get("content", [])

        text_parts = []
        thinking = None
        tool_calls = []

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    elif item.get("type") == "thinking":
                        thinking = item.get("thinking", "")
                    elif item.get("type") == "tool_use":
                        tool_calls.append({
                            "id": item.get("id"),
                            "name": item.get("name"),
                            "input": item.get("input", {}),
                        })
        elif isinstance(content, str):
            text_parts.append(content)

        text = "\n".join(text_parts).strip()
        if not text and not thinking and not tool_calls:
            return None

        # Extract usage data
        usage = message.get("usage", {})

        return {
            "type": "assistant",
            "role": "assistant",
            "content": text,
            "thinking": thinking,
            "tool_calls": tool_calls if tool_calls else None,
            "timestamp": entry.get("timestamp"),
            "uuid": entry.get("uuid"),
            "session_id": entry.get("sessionId"),
            "model": message.get("model"),
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            } if usage else None,
            "stop_reason": message.get("stop_reason"),
        }

    def _parse_tool_use(self, entry: Dict) -> Optional[Dict]:
        """Parse tool use entry."""
        tool = entry.get("tool", {})

        return {
            "type": "tool_use",
            "role": "tool",
            "tool_name": tool.get("name", "unknown"),
            "tool_input": tool.get("input", {}),
            "timestamp": entry.get("timestamp"),
            "uuid": entry.get("uuid"),
        }

    def _parse_tool_result(self, entry: Dict) -> Optional[Dict]:
        """Parse tool result entry."""
        result = entry.get("result", {})

        return {
            "type": "tool_result",
            "role": "tool",
            "output": result.get("output", ""),
            "error": result.get("error"),
            "timestamp": entry.get("timestamp"),
            "uuid": entry.get("uuid"),
        }

    def _extract_text(self, content) -> str:
        """Extract text from various content formats."""
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

    def _write_markdown(self, messages: List[Dict], output_path: Path, session_id: str):
        """Write messages as markdown file."""
        with open(output_path, "w", encoding="utf-8") as f:
            # Header
            f.write("# Claude Conversation Log\n\n")
            f.write(f"**Session ID:** `{session_id}`\n\n")

            # Get timestamp from first message
            if messages and messages[0].get("timestamp"):
                try:
                    dt = datetime.fromisoformat(
                        messages[0]["timestamp"].replace("Z", "+00:00")
                    )
                    f.write(f"**Date:** {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
                except Exception:
                    pass

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

    def _write_html(self, messages: List[Dict], output_path: Path, session_id: str):
        """Write messages as HTML file."""
        # Get metadata
        timestamp_str = ""
        if messages and messages[0].get("timestamp"):
            try:
                dt = datetime.fromisoformat(
                    messages[0]["timestamp"].replace("Z", "+00:00")
                )
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                pass

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Session - {html.escape(session_id[:16])}</title>
    <style>
        :root {{
            --user-color: #3498db;
            --assistant-color: #2ecc71;
            --tool-color: #f39c12;
            --bg-color: #f5f5f5;
            --card-bg: white;
            --text-color: #333;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            background: var(--bg-color);
        }}
        .header {{
            background: var(--card-bg);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{ color: #2c3e50; margin: 0 0 10px 0; }}
        .metadata {{ color: #666; font-size: 0.9em; }}
        .message {{
            background: var(--card-bg);
            padding: 15px 20px;
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .user {{ border-left: 4px solid var(--user-color); }}
        .assistant {{ border-left: 4px solid var(--assistant-color); }}
        .tool {{ border-left: 4px solid var(--tool-color); background: #fffbf0; }}
        .role {{
            font-weight: bold;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .role-user {{ color: var(--user-color); }}
        .role-assistant {{ color: var(--assistant-color); }}
        .role-tool {{ color: var(--tool-color); }}
        .content {{
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        .thinking {{
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 4px;
            padding: 10px;
            margin-bottom: 10px;
            font-size: 0.9em;
            color: #666;
        }}
        .thinking summary {{
            cursor: pointer;
            font-weight: bold;
        }}
        pre {{
            background: #f4f4f4;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        code {{
            background: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Claude Conversation Log</h1>
        <div class="metadata">
            <p><strong>Session:</strong> {html.escape(session_id)}</p>
            <p><strong>Date:</strong> {html.escape(timestamp_str)}</p>
            <p><strong>Messages:</strong> {len(messages)}</p>
        </div>
    </div>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

            for msg in messages:
                msg_type = msg.get("type")
                content = html.escape(msg.get("content", ""))

                if msg_type == "user":
                    f.write('    <div class="message user">\n')
                    f.write('        <div class="role role-user">User</div>\n')
                    f.write(f'        <div class="content">{content}</div>\n')
                    f.write('    </div>\n')

                elif msg_type == "assistant":
                    f.write('    <div class="message assistant">\n')
                    f.write('        <div class="role role-assistant">Claude</div>\n')

                    # Thinking
                    thinking = msg.get("thinking")
                    if thinking:
                        f.write('        <details class="thinking">\n')
                        f.write('            <summary>Thinking</summary>\n')
                        f.write(f'            <p>{html.escape(thinking)}</p>\n')
                        f.write('        </details>\n')

                    f.write(f'        <div class="content">{content}</div>\n')
                    f.write('    </div>\n')

                elif msg_type in ["tool_use", "tool_result"]:
                    f.write('    <div class="message tool">\n')
                    if msg_type == "tool_use":
                        tool_name = html.escape(msg.get("tool_name", "unknown"))
                        f.write(f'        <div class="role role-tool">Tool: {tool_name}</div>\n')
                        tool_input = json.dumps(msg.get("tool_input", {}), indent=INDENT, ensure_ascii=False)
                        f.write(f'        <pre>{html.escape(tool_input)}</pre>\n')
                    else:
                        f.write('        <div class="role role-tool">Tool Result</div>\n')
                        output = html.escape(msg.get("output", "")[:2000])
                        f.write(f'        <pre>{output}</pre>\n')
                    f.write('    </div>\n')

            f.write("\n</body>\n</html>")

    def _write_data(self, messages: List[Dict], output_path: Path, session_id: str, source_file: Path):
        """Write messages as structured JSON data file."""
        # Get session metadata from first message
        metadata = {}
        if messages:
            first = messages[0]
            metadata = {
                "session_id": first.get("session_id") or session_id,
                "source_file": str(source_file),
            }

            if first.get("timestamp"):
                try:
                    dt = datetime.fromisoformat(
                        first["timestamp"].replace("Z", "+00:00")
                    )
                    metadata["start_time"] = dt.isoformat()
                except Exception:
                    pass

        # Get end time from last message
        if messages and messages[-1].get("timestamp"):
            try:
                dt = datetime.fromisoformat(
                    messages[-1]["timestamp"].replace("Z", "+00:00")
                )
                metadata["end_time"] = dt.isoformat()
            except Exception:
                pass

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
