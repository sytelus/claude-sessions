#!/usr/bin/env python3
"""
Session parser for Claude Sessions.

Unified JSONL parsing logic used by formatters and statistics modules.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from utils import extract_text, parse_timestamp
except ImportError:
    from .utils import extract_text, parse_timestamp


class ParsedMessage:
    """Represents a parsed message from a Claude session."""

    def __init__(self, data: Dict[str, Any]):
        self.type = data.get("type")
        self.role = data.get("role")
        self.content = data.get("content", "")
        self.timestamp = data.get("timestamp")
        self.timestamp_dt = data.get("timestamp_dt")
        self.uuid = data.get("uuid")
        self.session_id = data.get("session_id")
        self.model = data.get("model")
        self.thinking = data.get("thinking")
        self.tool_calls = data.get("tool_calls")
        self.tool_name = data.get("tool_name")
        self.tool_input = data.get("tool_input")
        self.output = data.get("output")
        self.error = data.get("error")
        self.usage = data.get("usage")
        self.stop_reason = data.get("stop_reason")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None and key != "timestamp_dt":
                result[key] = value
        return result


class SessionParser:
    """Parses Claude session JSONL files into normalized message structures."""

    def parse_file(self, jsonl_path: Path) -> List[ParsedMessage]:
        """
        Parse a JSONL file and return list of parsed messages.

        Args:
            jsonl_path: Path to JSONL file

        Returns:
            List of ParsedMessage objects
        """
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

    def parse_file_as_dicts(self, jsonl_path: Path) -> List[Dict[str, Any]]:
        """
        Parse a JSONL file and return list of dictionaries.

        Convenience method for code that expects dicts instead of objects.

        Args:
            jsonl_path: Path to JSONL file

        Returns:
            List of message dictionaries
        """
        return [msg.to_dict() for msg in self.parse_file(jsonl_path)]

    def _parse_entry(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse a single JSONL entry into a ParsedMessage."""
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
        """Parse user message entry."""
        message = entry.get("message", {})
        content = message.get("content", "")

        text = extract_text(content)
        if not text:
            return None

        timestamp_str = entry.get("timestamp")

        return ParsedMessage({
            "type": "user",
            "role": "user",
            "content": text,
            "timestamp": timestamp_str,
            "timestamp_dt": parse_timestamp(timestamp_str),
            "uuid": entry.get("uuid"),
            "session_id": entry.get("sessionId"),
        })

    def _parse_assistant_message(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
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
        timestamp_str = entry.get("timestamp")

        return ParsedMessage({
            "type": "assistant",
            "role": "assistant",
            "content": text,
            "thinking": thinking,
            "tool_calls": tool_calls if tool_calls else None,
            "timestamp": timestamp_str,
            "timestamp_dt": parse_timestamp(timestamp_str),
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
        })

    def _parse_tool_use(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse tool use entry."""
        tool = entry.get("tool", {})
        timestamp_str = entry.get("timestamp")

        return ParsedMessage({
            "type": "tool_use",
            "role": "tool",
            "tool_name": tool.get("name", "unknown"),
            "tool_input": tool.get("input", {}),
            "timestamp": timestamp_str,
            "timestamp_dt": parse_timestamp(timestamp_str),
            "uuid": entry.get("uuid"),
        })

    def _parse_tool_result(self, entry: Dict[str, Any]) -> Optional[ParsedMessage]:
        """Parse tool result entry."""
        result = entry.get("result", {})
        timestamp_str = entry.get("timestamp")

        return ParsedMessage({
            "type": "tool_result",
            "role": "tool",
            "output": result.get("output", ""),
            "error": result.get("error"),
            "timestamp": timestamp_str,
            "timestamp_dt": parse_timestamp(timestamp_str),
            "uuid": entry.get("uuid"),
        })
