#!/usr/bin/env python3
"""
Shared utilities for Claude Sessions.

Common functions used across multiple modules.
"""

from datetime import datetime
from typing import Optional


def extract_text(content) -> str:
    """
    Extract text from various content formats.

    Handles:
    - Plain strings
    - Lists of text blocks (Claude API format)
    - Mixed content lists

    Args:
        content: String, list, or other content format

    Returns:
        Extracted text as a single string
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
    Parse ISO timestamp string to datetime.

    Handles timestamps with 'Z' suffix (UTC) and various ISO formats.

    Args:
        timestamp_str: ISO format timestamp string or None

    Returns:
        datetime object or None if parsing fails
    """
    if not timestamp_str:
        return None
    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception:
        return None
