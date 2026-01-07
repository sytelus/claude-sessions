#!/usr/bin/env python3
"""
Session parser for Claude Sessions.

This module provides unified JSONL parsing logic for all Claude Code session
files. It normalizes the various message types into a consistent structure
that can be used by formatters, statistics, and other modules.

The parser handles four message types:
    - user: Messages from the user
    - assistant: Claude's responses (including thinking and tool calls)
    - tool_use: Tool invocation records
    - tool_result: Results from tool execution

For the complete JSONL format specification, see:
    docs/JSONL_FORMAT.md

For architecture overview, see:
    docs/ARCHITECTURE.md

Example:
    >>> from parser import SessionParser
    >>> parser = SessionParser()
    >>> messages = parser.parse_file(Path("session.jsonl"))
    >>> for msg in messages:
    ...     print(f"{msg.type}: {msg.content[:50]}...")

Classes:
    ParsedMessage: Data container for a parsed message
    SessionParser: JSONL file parser
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import extract_text, parse_timestamp


@dataclass
class ParsedMessage:
    """
    Data container for a parsed message from a Claude session.

    This dataclass normalizes messages from different JSONL entry types into
    a consistent structure. Not all fields are populated for all message
    types - unused fields remain None.

    Attributes:
        type: Message type - "user", "assistant", "tool_use", or "tool_result"
        role: Speaker role - "user", "assistant", or "tool"
        content: Text content of the message (extracted from various formats)
        timestamp: Original ISO timestamp string from the JSONL
        timestamp_dt: Parsed datetime object (timezone-aware, UTC)
        uuid: Unique message identifier
        session_id: Session identifier (from sessionId field)
        model: Model ID for assistant messages (e.g., "claude-3-opus-20240229")
        thinking: Claude's internal reasoning (from thinking blocks)
        tool_calls: Tool calls made by assistant [{id, name, input}, ...]
        tool_name: Name of tool for tool_use entries
        tool_input: Input parameters for tool_use entries
        output: Output text for tool_result entries
        error: Error message for failed tool_result entries
        usage: Token usage statistics for assistant messages
        stop_reason: Why generation stopped (e.g., "end_turn", "tool_use")

    Example:
        >>> msg = ParsedMessage(type="user", content="Hello")
        >>> msg.type
        'user'
        >>> msg.to_dict()
        {'type': 'user', 'content': 'Hello'}
    """

    type: Optional[str] = None
    role: Optional[str] = None
    content: str = ""
    timestamp: Optional[str] = None
    timestamp_dt: Optional[datetime] = field(default=None, repr=False)
    uuid: Optional[str] = None
    session_id: Optional[str] = None
    model: Optional[str] = None
    thinking: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    error: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    stop_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert message to dictionary, excluding None values.

        Returns a clean dictionary representation suitable for JSON
        serialization. The timestamp_dt field is excluded since it's
        a datetime object (the original timestamp string is preserved).

        Returns:
            dict: Dictionary with all non-None attributes except timestamp_dt

        Example:
            >>> msg = ParsedMessage(type="user", content="Hi")
            >>> msg.to_dict()
            {'type': 'user', 'content': 'Hi'}
        """
        result = {}
        for key, value in asdict(self).items():
            if value is not None and key != "timestamp_dt":
                result[key] = value
        return result


class SessionParser:
    """
    Parser for Claude Code session JSONL files.

    This class reads JSONL files line by line and converts each entry
    into a normalized ParsedMessage object. It handles all four message
    types (user, assistant, tool_use, tool_result).

    The parser is stateless and can be reused across multiple files.
    Each method call is independent.

    Error Handling:
        - Invalid JSON lines are skipped with a warning
        - Unknown message types are skipped (for forward compatibility)
        - File read errors are raised to the caller
        - Missing fields use sensible defaults

    Example:
        >>> parser = SessionParser()
        >>>
        >>> # Parse to ParsedMessage objects
        >>> messages = parser.parse_file(Path("session.jsonl"))
        >>> for msg in messages:
        ...     if msg.type == "assistant":
        ...         print(msg.content)
        >>>
        >>> # Parse to dictionaries
        >>> dicts = parser.parse_file_as_dicts(Path("session.jsonl"))
        >>> print(json.dumps(dicts, indent=2))

    See Also:
        docs/JSONL_FORMAT.md for complete format specification
    """

    def parse_file(self, jsonl_path: Path) -> List[ParsedMessage]:
        """
        Parse a JSONL file and return list of parsed messages.

        Args:
            jsonl_path: Path to JSONL file

        Returns:
            List of ParsedMessage objects

        Raises:
            FileNotFoundError: If the file doesn't exist
            PermissionError: If the file can't be read
            IOError: For other file access errors
        """
        messages = []

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    parsed = self._parse_entry(entry)
                    if parsed:
                        messages.append(parsed)
                except json.JSONDecodeError as e:
                    # Skip malformed JSON lines but continue processing
                    # This is expected for corrupted/partial files
                    continue

        return messages

    def parse_file_as_dicts(self, jsonl_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a JSONL file and return list of dictionaries.

        Convenience method for code that expects dicts instead of objects.

        Args:
            jsonl_path: Path to JSONL file

        Returns:
            List of message dictionaries

        Raises:
            FileNotFoundError: If the file doesn't exist
            PermissionError: If the file can't be read
        """
        return [msg.to_dict() for msg in self.parse_file(jsonl_path)]

    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """
        Parse a single JSONL entry into a ParsedMessage.

        Routes the entry to the appropriate type-specific parser based on the
        'type' field. Unknown types return None for forward compatibility.

        Args:
            entry: Dictionary from parsing a JSON line

        Returns:
            ParsedMessage for known types, None for unknown types
        """
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

    def _parse_user_message(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """
        Parse user message entry.

        Extracts text content from message.content (handles both string and
        array formats via extract_text). Returns None if no text content found.

        Fields extracted: type, role, content, timestamp, timestamp_dt, uuid, session_id
        """
        message = entry.get("message", {})
        content = message.get("content", "")

        text = extract_text(content)
        if not text:
            return None

        timestamp_str = entry.get("timestamp")

        return ParsedMessage(
            type="user",
            role="user",
            content=text,
            timestamp=timestamp_str,
            timestamp_dt=parse_timestamp(timestamp_str),
            uuid=entry.get("uuid"),
            session_id=entry.get("sessionId"),
        )

    def _parse_assistant_message(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """
        Parse assistant message entry.

        Processes the content array to extract:
        - Text blocks (type="text") -> concatenated into content field
        - Thinking blocks (type="thinking") -> stored in thinking field
        - Tool use blocks (type="tool_use") -> collected into tool_calls list

        Returns None if no text, thinking, or tool calls found.

        Fields extracted: type, role, content, thinking, tool_calls, timestamp,
                         timestamp_dt, uuid, session_id, model, usage, stop_reason
        """
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
        timestamp_str = entry.get("timestamp")

        return ParsedMessage(
            type="assistant",
            role="assistant",
            content=text,
            thinking=thinking,
            tool_calls=tool_calls if tool_calls else None,
            timestamp=timestamp_str,
            timestamp_dt=parse_timestamp(timestamp_str),
            uuid=entry.get("uuid"),
            session_id=entry.get("sessionId"),
            model=message.get("model"),
            usage={
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
            } if usage else None,
            stop_reason=message.get("stop_reason"),
        )

    def _parse_tool_use(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """
        Parse tool use entry.

        These entries record individual tool invocations separate from the
        assistant message that requested them. The tool.name and tool.input
        fields contain the invocation details.

        Fields extracted: type, role, tool_name, tool_input, timestamp, timestamp_dt, uuid
        """
        tool = entry.get("tool", {})
        timestamp_str = entry.get("timestamp")

        return ParsedMessage(
            type="tool_use",
            role="tool",
            tool_name=tool.get("name", "unknown"),
            tool_input=tool.get("input", {}),
            timestamp=timestamp_str,
            timestamp_dt=parse_timestamp(timestamp_str),
            uuid=entry.get("uuid"),
        )

    def _parse_tool_result(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """
        Parse tool result entry.

        These entries contain the output from tool execution. The result.output
        field holds successful output, while result.error contains any error
        message (null on success).

        Fields extracted: type, role, output, error, timestamp, timestamp_dt, uuid
        """
        result = entry.get("result", {})
        timestamp_str = entry.get("timestamp")

        return ParsedMessage(
            type="tool_result",
            role="tool",
            output=result.get("output", ""),
            error=result.get("error"),
            timestamp=timestamp_str,
            timestamp_dt=parse_timestamp(timestamp_str),
            uuid=entry.get("uuid"),
        )
