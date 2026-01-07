#!/usr/bin/env python3
"""
Prompts extraction for Claude Sessions.

This module extracts user prompts from Claude Code session JSONL files and
saves them in a human-readable YAML format. It's useful for reviewing what
questions/requests were made without the full conversation context.

Features:
    - Extracts only user messages (filters out assistant, tool_use, tool_result)
    - Cleans prompt text (removes XML tags, system prefixes, tool outputs)
    - Filters out non-meaningful messages (continuation notices, single-word responses)
    - Organizes prompts by project and session
    - Uses block scalar style (|) for multiline prompts in YAML

Output Format (prompts.yaml):
    project: project-hash-name
    sessions:
      - session_id: abc123-def456
        date: "2024-01-15"
        prompts:
          - prompt: "First user question"
            timestamp: "2024-01-15T10:00:00.000Z"
          - prompt: |
              Multiline prompt
              with multiple lines
            timestamp: "2024-01-15T10:05:00.000Z"

Dependencies:
    - PyYAML (optional): If available, uses yaml.dump() for proper YAML output.
      If not available, falls back to manual YAML generation.

For architecture overview, see:
    docs/ARCHITECTURE.md

For JSONL input format, see:
    docs/JSONL_FORMAT.md

Example:
    >>> from prompts import PromptsExtractor
    >>> extractor = PromptsExtractor()
    >>> result = extractor.extract_all(Path("./output"))
    >>> print(f"Extracted {result['prompts']} prompts from {result['sessions']} sessions")

Classes:
    PromptsExtractor: Main class for extracting and saving prompts

Module Constants:
    YAML_AVAILABLE (bool): True if PyYAML is installed
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import SessionParser
from .utils import iter_project_dirs

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class PromptsExtractor:
    """
    Extracts user prompts from Claude session files.

    This class processes JSONL session files, extracts user messages, cleans
    them up, and saves them in a structured YAML format. The output is designed
    for human review of what prompts were sent to Claude.

    Processing Pipeline:
        1. Iterate through all projects in output directory
        2. For each project, process all JSONL files sorted by modification time
        3. Extract user messages using SessionParser
        4. Clean prompt text (remove XML, system prefixes, tool outputs)
        5. Filter out non-meaningful prompts (continuations, single-word responses)
        6. Save cleaned prompts to prompts.yaml in each project directory

    Text Cleaning:
        The extractor removes several types of noise from prompts:
        - XML-like tags: <system-reminder>...</system-reminder>
        - Self-closing tags: <tag/>
        - Tool result prefixes: tool_use_id:...
        - System prefixes: [Request interrupted...], [Image #1...]
        - Excess whitespace and blank lines

    Filtered Prompts:
        These types of prompts are skipped:
        - Session continuation messages
        - "warmup" messages (used by some tools)
        - Single-word responses: y, n, yes, no, ok, okay

    Attributes:
        parser (SessionParser): Parser instance for reading JSONL files

    Example:
        >>> extractor = PromptsExtractor()
        >>> result = extractor.extract_all(Path("./output"))
        >>> print(f"Projects: {result['projects']}")
        >>> print(f"Sessions: {result['sessions']}")
        >>> print(f"Prompts: {result['prompts']}")
    """

    def __init__(self) -> None:
        """Initialize extractor with a SessionParser instance."""
        self.parser = SessionParser()

    def extract_all(self, output_dir: Path) -> Dict[str, int]:
        """
        Extract prompts from all projects in output directory.

        Iterates through all project directories, extracts prompts from each,
        and saves a prompts.yaml file in each project directory that has
        valid prompts.

        Args:
            output_dir: Root output directory containing project folders.
                        Each project folder should contain *.jsonl files.

        Returns:
            dict: Extraction statistics with keys:
                - projects (int): Number of projects with extracted prompts
                - sessions (int): Number of sessions with extracted prompts
                - prompts (int): Total number of prompts extracted
        """
        result = {
            "projects": 0,
            "sessions": 0,
            "prompts": 0,
        }

        for project_dir in iter_project_dirs(output_dir):
            project_prompts = self._extract_project_prompts(project_dir)
            if project_prompts:
                result["projects"] += 1
                result["sessions"] += len(project_prompts["sessions"])
                for session in project_prompts["sessions"]:
                    result["prompts"] += len(session.get("prompts", []))

                # Save prompts.yaml
                self._save_prompts(project_prompts, project_dir / "prompts.yaml")

        return result

    def _extract_project_prompts(self, project_dir: Path) -> Optional[Dict[str, Any]]:
        """
        Extract prompts from a single project directory.

        Processes all JSONL files in the project, sorted by modification time
        (oldest first), and aggregates prompts into a single structure.

        Args:
            project_dir: Path to project directory containing *.jsonl files

        Returns:
            dict: Project prompts with keys:
                - project (str): Project directory name
                - sessions (list): List of session prompt data
            None: If no JSONL files found or no valid prompts extracted
        """
        jsonl_files = list(project_dir.glob("*.jsonl"))
        if not jsonl_files:
            return None

        project_data = {
            "project": project_dir.name,
            "sessions": [],
        }

        for jsonl_file in sorted(jsonl_files, key=lambda x: x.stat().st_mtime):
            session_prompts = self._extract_session_prompts(jsonl_file)
            if session_prompts and session_prompts.get("prompts"):
                project_data["sessions"].append(session_prompts)

        return project_data if project_data["sessions"] else None

    def _extract_session_prompts(self, jsonl_file: Path) -> Optional[Dict[str, Any]]:
        """
        Extract prompts from a single session JSONL file.

        Reads the file using SessionParser, filters for user messages,
        cleans and validates each prompt.

        Args:
            jsonl_file: Path to session JSONL file

        Returns:
            dict: Session prompts with keys:
                - session_id (str): JSONL filename without extension
                - date (str): Session date from first prompt (YYYY-MM-DD)
                - prompts (list): List of {prompt, timestamp} dicts
            None: If no valid prompts found in session
        """
        session_data: Dict[str, Any] = {
            "session_id": jsonl_file.stem,
            "prompts": [],
        }

        # Use SessionParser to read the file
        messages = self.parser.parse_file_as_dicts(jsonl_file)

        for msg in messages:
            if msg.get("type") == "user":
                prompt = self._extract_user_prompt(msg)
                if prompt:
                    session_data["prompts"].append(prompt)

        # Get first timestamp as session date
        if session_data["prompts"]:
            first_ts = session_data["prompts"][0].get("timestamp")
            if first_ts:
                session_data["date"] = first_ts[:10]  # YYYY-MM-DD

        return session_data if session_data["prompts"] else None

    def _extract_user_prompt(self, entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract and clean a single user prompt from a parsed message entry.

        Applies text cleaning, length validation, and content filtering.

        Args:
            entry: Parsed message dictionary (from SessionParser)

        Returns:
            dict: Prompt data with keys:
                - prompt (str): Cleaned prompt text
                - timestamp (str): Original ISO timestamp (if available)
            None: If prompt is empty, too short, or should be filtered
        """
        # SessionParser already extracts content as text
        text = entry.get("content", "")
        if not text:
            return None

        # Clean up the text
        text = self._clean_prompt_text(text)
        if not text or len(text) < 2:
            return None

        # Skip certain types of messages
        if self._should_skip_prompt(text):
            return None

        prompt_data = {
            "prompt": text,
        }

        # Add timestamp if available
        timestamp = entry.get("timestamp")
        if timestamp:
            prompt_data["timestamp"] = timestamp

        return prompt_data

    def _clean_prompt_text(self, text: str) -> str:
        """
        Clean up prompt text by removing noise.

        Removes:
        - XML-like tags and their contents: <tag>...</tag>
        - Self-closing XML tags: <tag/>
        - Opening XML tags without content: <tag>
        - Tool result prefixes: tool_use_id:...
        - System message prefixes: [Request interrupted...], [Image #1...]
        - Excessive whitespace: collapses multiple blank lines to single

        Args:
            text: Raw prompt text from user message

        Returns:
            Cleaned text with noise removed and whitespace normalized
        """
        # Remove XML-like tags (system messages, tool outputs)
        text = re.sub(r"<[^>]+>[\s\S]*?</[^>]+>", "", text)
        text = re.sub(r"<[^>]+/>", "", text)
        text = re.sub(r"<[^>]+>", "", text)

        # Remove tool result prefixes
        text = re.sub(r"^tool_use_id:[\s\S]*?(?=\n|$)", "", text)

        # Remove common system prefixes
        text = re.sub(r"^\[Request interrupted[^\]]*\]", "", text)
        text = re.sub(r"^\[Image #\d+[^\]]*\]", "", text)

        # Clean whitespace
        text = text.strip()
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    def _should_skip_prompt(self, text: str) -> bool:
        """
        Determine if prompt should be skipped (not included in output).

        Filters out prompts that are not meaningful user requests:
        - Session continuation messages (auto-generated by Claude Code)
        - Warmup messages (used by some testing tools)
        - Single-word confirmations: y, n, yes, no, ok, okay

        Args:
            text: Cleaned prompt text

        Returns:
            True if prompt should be skipped, False to include it
        """
        text_lower = text.lower()

        # Skip continuation messages
        if "session is being continued" in text_lower:
            return True

        # Skip warmup messages
        if text_lower.strip() == "warmup":
            return True

        # Skip very short single-word responses that are likely commands
        if len(text.split()) == 1 and text_lower in ["y", "n", "yes", "no", "ok", "okay"]:
            return True

        return False

    def _save_prompts(self, project_prompts: Dict[str, Any], output_path: Path) -> None:
        """
        Save prompts to YAML file.

        Dispatches to either PyYAML-based saving (if available) or manual
        YAML generation (fallback).

        Args:
            project_prompts: Project prompts dictionary from _extract_project_prompts()
            output_path: Path for output YAML file
        """
        if YAML_AVAILABLE:
            self._save_as_yaml(project_prompts, output_path)
        else:
            self._save_as_yaml_manual(project_prompts, output_path)

    def _save_as_yaml(self, data: Dict[str, Any], output_path: Path) -> None:
        """
        Save using PyYAML library.

        Uses a custom Dumper that formats multiline strings with block scalar
        style (|) for better readability of long prompts.

        Args:
            data: Project prompts dictionary
            output_path: Path for output YAML file
        """
        # Custom Dumper that handles multiline strings
        class MultilineDumper(yaml.SafeDumper):
            pass

        def str_representer(dumper: Any, data: str) -> Any:
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        MultilineDumper.add_representer(str, str_representer)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=MultilineDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _save_as_yaml_manual(self, data: Dict[str, Any], output_path: Path) -> None:
        """
        Save as YAML manually (without PyYAML dependency).

        Generates valid YAML output using string formatting. This is a fallback
        for when PyYAML is not installed. Handles multiline prompts using
        block scalar style (|) and properly escapes special characters.

        Args:
            data: Project prompts dictionary
            output_path: Path for output YAML file
        """
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(f"# User prompts for project: {data['project']}\n")
            f.write(f"project: {self._yaml_escape(data['project'])}\n\n")
            f.write("sessions:\n")

            for session in data["sessions"]:
                f.write(f"  - session_id: {session['session_id']}\n")
                if session.get("date"):
                    f.write(f"    date: {session['date']}\n")
                f.write("    prompts:\n")

                for prompt_data in session["prompts"]:
                    prompt_text = prompt_data["prompt"]

                    # Handle multiline prompts
                    if "\n" in prompt_text:
                        f.write("      - prompt: |\n")
                        for line in prompt_text.split("\n"):
                            f.write(f"          {line}\n")
                    else:
                        f.write(f"      - prompt: {self._yaml_escape(prompt_text)}\n")

                    if prompt_data.get("timestamp"):
                        f.write(f"        timestamp: {prompt_data['timestamp']}\n")

                f.write("\n")

    def _yaml_escape(self, text: str) -> str:
        """
        Escape text for safe inclusion in YAML output.

        Wraps text in double quotes if it contains YAML special characters
        that could cause parsing issues. Also escapes backslashes and quotes.

        Special characters that trigger quoting:
            : { } [ ] & * # ? | - < > = ! % @ ` ' "

        Args:
            text: Text to escape

        Returns:
            Escaped text, quoted if necessary
        """
        # If text contains special chars, quote it
        if any(c in text for c in ":{}[]&*#?|-<>=!%@`'\""):
            # Escape quotes and wrap in quotes
            text = text.replace("\\", "\\\\")
            text = text.replace('"', '\\"')
            return f'"{text}"'
        return text
