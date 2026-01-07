#!/usr/bin/env python3
"""
Prompts extraction for Claude Sessions.

Extracts user prompts from session files into readable YAML format.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from parser import SessionParser
    from utils import iter_project_dirs
except ImportError:
    from .parser import SessionParser
    from .utils import iter_project_dirs

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


class PromptsExtractor:
    """Extracts user prompts from Claude session files."""

    def __init__(self) -> None:
        self.parser = SessionParser()

    def extract_all(self, output_dir: Path) -> Dict[str, int]:
        """
        Extract prompts from all projects in output directory.

        Args:
            output_dir: Output directory containing project folders

        Returns:
            Dict with extraction statistics
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
        """Extract prompts from a single project."""
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
        """Extract prompts from a single session file."""
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
        """Extract user prompt from entry."""
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
        """Clean up prompt text."""
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
        """Determine if prompt should be skipped."""
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
        """Save prompts to YAML file."""
        if YAML_AVAILABLE:
            self._save_as_yaml(project_prompts, output_path)
        else:
            self._save_as_yaml_manual(project_prompts, output_path)

    def _save_as_yaml(self, data: Dict[str, Any], output_path: Path) -> None:
        """Save using PyYAML library."""
        # Custom Dumper that handles multiline strings
        class MultilineDumper(yaml.SafeDumper):
            pass

        def str_representer(dumper, data):
            if "\n" in data:
                return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
            return dumper.represent_scalar("tag:yaml.org,2002:str", data)

        MultilineDumper.add_representer(str, str_representer)

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, Dumper=MultilineDumper, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def _save_as_yaml_manual(self, data: Dict[str, Any], output_path: Path) -> None:
        """Save as YAML manually (without PyYAML dependency)."""
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
        """Escape text for YAML output."""
        # If text contains special chars, quote it
        if any(c in text for c in ":{}[]&*#?|-<>=!%@`'\""):
            # Escape quotes and wrap in quotes
            text = text.replace("\\", "\\\\")
            text = text.replace('"', '\\"')
            return f'"{text}"'
        return text
