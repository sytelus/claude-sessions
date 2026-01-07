#!/usr/bin/env python3
"""
Statistics generation for Claude Sessions.

This module computes comprehensive statistics about Claude Code usage patterns
from session JSONL files. It generates both machine-readable JSON and human-
readable HTML dashboard outputs.

Statistics Categories:
    - Message counts: User messages, assistant messages, tool uses
    - Token usage: Input tokens, output tokens, totals
    - Timing: Session durations, response times, work hours distribution
    - Content analysis: Code blocks generated, apology pattern detection
    - Trends: Daily, weekly, and monthly usage patterns
    - Models: Which Claude models were used and how often

Output Files:
    - stats.json: Machine-readable statistics for programmatic access
    - stats.html: Interactive HTML dashboard with charts and tables

Aggregate vs Per-Project:
    Statistics are computed at two levels:
    1. Per-project: Metrics for each individual project directory
    2. Aggregate: Combined totals and averages across all projects

For architecture overview and data flow, see:
    docs/ARCHITECTURE.md

For JSONL format details (where statistics are extracted from), see:
    docs/JSONL_FORMAT.md

Example:
    >>> from stats import StatisticsGenerator
    >>> generator = StatisticsGenerator()
    >>> stats = generator.generate(Path("./output"))
    >>> print(f"Total sessions: {stats['aggregate']['total_sessions']}")
    >>> generator.save_json(stats, Path("./output/stats.json"))
    >>> generator.save_html(stats, Path("./output/stats.html"))

Classes:
    StatisticsGenerator: Main class for computing and exporting statistics

Class Attributes:
    APOLOGY_PATTERNS: Regex patterns for detecting apology language
    CODE_BLOCK_PATTERN: Regex for detecting markdown code blocks
"""

import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from parser import SessionParser, ParsedMessage
from utils import iter_project_dirs
from html_generator import generate_stats_html


class StatisticsGenerator:
    """
    Generates comprehensive statistics from Claude session data.

    This class processes all JSONL session files in a backup directory and
    computes various metrics about Claude Code usage. Statistics are computed
    both per-project and as aggregate totals.

    The generator uses SessionParser to read session files, ensuring consistent
    parsing across all modules.

    Statistics Computed:
        Message Metrics:
            - Total messages (user + assistant + tool)
            - User message count
            - Assistant message count
            - Tool use count

        Token Metrics:
            - Input tokens (cumulative across all sessions)
            - Output tokens (cumulative across all sessions)
            - Total tokens
            - Average tokens per session

        Timing Metrics:
            - Session duration (first to last message)
            - Response times (user message to assistant response)
            - Work hours distribution (sessions per hour of day)

        Content Analysis:
            - Code blocks generated (markdown ``` blocks)
            - Apology patterns (self-correction language)

        Usage Trends:
            - Daily usage counts
            - Weekly usage counts
            - Monthly usage counts

        Model Usage:
            - Count of sessions per model version

    Attributes:
        parser (SessionParser): Parser instance for reading JSONL files

    Example:
        >>> generator = StatisticsGenerator()
        >>> stats = generator.generate(Path("./backups"))
        >>> # Access aggregate statistics
        >>> print(f"Sessions: {stats['aggregate']['total_sessions']}")
        >>> print(f"Tokens: {stats['aggregate']['total_tokens']:,}")
        >>> # Access per-project statistics
        >>> for project in stats['projects']:
        ...     print(f"{project['project_name']}: {project['sessions']} sessions")
    """

    # Patterns for detecting communication patterns
    APOLOGY_PATTERNS = [
        r"\bi('m| am) sorry\b",
        r"\bapologi[zs]e\b",
        r"\bmy mistake\b",
        r"\bi was wrong\b",
        r"\bcorrection\b",
        r"\blet me (fix|correct)\b",
    ]

    # Patterns for detecting code blocks
    CODE_BLOCK_PATTERN = r"```[\s\S]*?```"
    # Pattern for detecting code block language
    CODE_LANG_PATTERN = r"```(\w+)"

    def __init__(self) -> None:
        self.parser = SessionParser()

    def generate(self, output_dir: Path) -> Dict[str, Any]:
        """
        Generate statistics for all backed up sessions.

        Iterates through all project directories in output_dir, analyzes
        each session JSONL file, and aggregates the results.

        Args:
            output_dir: Root output directory containing project folders.
                        Each project folder should contain *.jsonl files.

        Returns:
            dict: Statistics with the following structure:
                - generated_at (str): ISO timestamp when stats were generated
                - aggregate (dict): Combined statistics across all projects:
                    - total_sessions, total_messages, total_tokens, etc.
                    - work_hours (dict): Hour (0-23) -> session count
                    - daily_usage (dict): Date string -> session count
                    - models_used (dict): Model ID -> usage count
                    - session_duration_stats (dict): min/max/avg/median minutes
                    - response_time_stats (dict): min/max/avg/median seconds
                - projects (list): Per-project statistics, each containing:
                    - project_name, sessions, total_messages, total_tokens
                    - first_session, last_session (ISO timestamps)
                    - work_hours, daily_usage, models_used (dicts)
        """
        all_projects = []
        aggregate = {
            "total_sessions": 0,
            "total_messages": 0,
            "total_user_messages": 0,
            "total_assistant_messages": 0,
            "total_tokens": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cache_read_tokens": 0,
            "total_cache_creation_tokens": 0,
            "total_code_blocks": 0,
            "total_code_lines": 0,  # Lines in code blocks
            "total_lines_written": 0,  # Lines written via Write tool
            "total_lines_edited": 0,  # Lines changed via Edit tool
            "total_apologies": 0,
            "total_tool_uses": 0,
            "total_tool_errors": 0,
            "total_thinking_blocks": 0,
            "work_hours": Counter(),  # Hour -> count
            "daily_usage": Counter(),  # Date -> count
            "weekly_usage": Counter(),  # Week -> count
            "monthly_usage": Counter(),  # Month -> count
            "all_session_durations": [],
            "all_response_times": [],
            "models_used": Counter(),
            "tools_used": Counter(),  # Tool name -> count
            "code_languages": Counter(),  # Language -> count
            "files_touched": Counter(),  # File path -> count
        }

        # Process each project
        for project_dir in iter_project_dirs(output_dir):
            project_stats = self._compute_project_stats(project_dir)
            if project_stats:
                all_projects.append(project_stats)

                # Accumulate aggregate stats
                aggregate["total_sessions"] += project_stats["sessions"]
                aggregate["total_messages"] += project_stats["total_messages"]
                aggregate["total_user_messages"] += project_stats["user_messages"]
                aggregate["total_assistant_messages"] += project_stats["assistant_messages"]
                aggregate["total_tokens"] += project_stats["total_tokens"]
                aggregate["total_input_tokens"] += project_stats["input_tokens"]
                aggregate["total_output_tokens"] += project_stats["output_tokens"]
                aggregate["total_cache_read_tokens"] += project_stats.get("cache_read_tokens", 0)
                aggregate["total_cache_creation_tokens"] += project_stats.get("cache_creation_tokens", 0)
                aggregate["total_code_blocks"] += project_stats["code_blocks"]
                aggregate["total_code_lines"] += project_stats.get("code_lines", 0)
                aggregate["total_lines_written"] += project_stats.get("lines_written", 0)
                aggregate["total_lines_edited"] += project_stats.get("lines_edited", 0)
                aggregate["total_apologies"] += project_stats["apologies"]
                aggregate["total_tool_uses"] += project_stats.get("tool_uses", 0)
                aggregate["total_tool_errors"] += project_stats.get("tool_errors", 0)
                aggregate["total_thinking_blocks"] += project_stats.get("thinking_blocks", 0)

                # Merge counters
                aggregate["work_hours"].update(project_stats.get("work_hours", {}))
                aggregate["daily_usage"].update(project_stats.get("daily_usage", {}))
                aggregate["weekly_usage"].update(project_stats.get("weekly_usage", {}))
                aggregate["monthly_usage"].update(project_stats.get("monthly_usage", {}))
                aggregate["models_used"].update(project_stats.get("models_used", {}))
                aggregate["tools_used"].update(project_stats.get("tools_used", {}))
                aggregate["code_languages"].update(project_stats.get("code_languages", {}))
                aggregate["files_touched"].update(project_stats.get("files_touched", {}))

                # Collect timing data
                aggregate["all_session_durations"].extend(
                    project_stats.get("session_durations", [])
                )
                aggregate["all_response_times"].extend(
                    project_stats.get("response_times", [])
                )

        # Compute aggregate statistics
        aggregate["avg_messages_per_session"] = (
            aggregate["total_messages"] / aggregate["total_sessions"]
            if aggregate["total_sessions"] > 0 else 0
        )
        aggregate["avg_tokens_per_session"] = (
            aggregate["total_tokens"] / aggregate["total_sessions"]
            if aggregate["total_sessions"] > 0 else 0
        )

        # Session duration stats
        if aggregate["all_session_durations"]:
            durations = aggregate["all_session_durations"]
            aggregate["session_duration_stats"] = {
                "min_minutes": min(durations),
                "max_minutes": max(durations),
                "avg_minutes": statistics.mean(durations),
                "median_minutes": statistics.median(durations),
                "std_dev_minutes": statistics.stdev(durations) if len(durations) > 1 else 0,
            }
        else:
            aggregate["session_duration_stats"] = None

        # Response time stats
        if aggregate["all_response_times"]:
            times = aggregate["all_response_times"]
            aggregate["response_time_stats"] = {
                "min_seconds": min(times),
                "max_seconds": max(times),
                "avg_seconds": statistics.mean(times),
                "median_seconds": statistics.median(times),
            }
        else:
            aggregate["response_time_stats"] = None

        # Convert counters to dicts for JSON serialization
        aggregate["work_hours"] = dict(aggregate["work_hours"])
        aggregate["daily_usage"] = dict(sorted(aggregate["daily_usage"].items()))
        aggregate["weekly_usage"] = dict(sorted(aggregate["weekly_usage"].items()))
        aggregate["monthly_usage"] = dict(sorted(aggregate["monthly_usage"].items()))
        aggregate["models_used"] = dict(aggregate["models_used"])
        aggregate["tools_used"] = dict(aggregate["tools_used"])
        aggregate["code_languages"] = dict(aggregate["code_languages"])
        # Limit files_touched to top 50 most accessed
        aggregate["files_touched"] = dict(
            sorted(aggregate["files_touched"].items(), key=lambda x: -x[1])[:50]
        )

        # Calculate cache efficiency (cache_read / (input + cache_read))
        # Note: Claude API reports cache_read_tokens separately from input_tokens
        total_input_with_cache = (
            aggregate["total_input_tokens"] + aggregate["total_cache_read_tokens"]
        )
        if total_input_with_cache > 0:
            aggregate["cache_hit_rate"] = (
                aggregate["total_cache_read_tokens"] / total_input_with_cache
            )
        else:
            aggregate["cache_hit_rate"] = 0.0

        # Calculate tool error rate
        if aggregate["total_tool_uses"] > 0:
            aggregate["tool_error_rate"] = (
                aggregate["total_tool_errors"] / aggregate["total_tool_uses"]
            )
        else:
            aggregate["tool_error_rate"] = 0.0

        # Remove raw lists from aggregate (too large for JSON)
        del aggregate["all_session_durations"]
        del aggregate["all_response_times"]

        return {
            "generated_at": datetime.now().isoformat(),
            "aggregate": aggregate,
            "projects": all_projects,
        }

    def _compute_project_stats(self, project_dir: Path) -> Optional[Dict[str, Any]]:
        """
        Compute statistics for a single project directory.

        Processes all JSONL files in the project directory and aggregates
        their statistics into a single project-level summary.

        Args:
            project_dir: Path to project directory containing *.jsonl files

        Returns:
            dict: Project statistics (see generate() for structure), or
            None: If no JSONL files found in directory
        """
        jsonl_files = list(project_dir.glob("*.jsonl"))
        if not jsonl_files:
            return None

        stats = {
            "project_name": project_dir.name,
            "sessions": len(jsonl_files),
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_uses": 0,
            "tool_errors": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "code_blocks": 0,
            "code_lines": 0,
            "lines_written": 0,
            "lines_edited": 0,
            "apologies": 0,
            "thinking_blocks": 0,
            "session_durations": [],
            "response_times": [],
            "work_hours": Counter(),
            "daily_usage": Counter(),
            "weekly_usage": Counter(),
            "monthly_usage": Counter(),
            "models_used": Counter(),
            "tools_used": Counter(),
            "code_languages": Counter(),
            "files_touched": Counter(),
            "first_session": None,
            "last_session": None,
        }

        for jsonl_file in jsonl_files:
            session_stats = self._analyze_session(jsonl_file)
            if not session_stats:
                continue

            # Accumulate counts
            stats["total_messages"] += session_stats["total_messages"]
            stats["user_messages"] += session_stats["user_messages"]
            stats["assistant_messages"] += session_stats["assistant_messages"]
            stats["tool_uses"] += session_stats["tool_uses"]
            stats["tool_errors"] += session_stats.get("tool_errors", 0)
            stats["total_tokens"] += session_stats["total_tokens"]
            stats["input_tokens"] += session_stats["input_tokens"]
            stats["output_tokens"] += session_stats["output_tokens"]
            stats["cache_read_tokens"] += session_stats.get("cache_read_tokens", 0)
            stats["cache_creation_tokens"] += session_stats.get("cache_creation_tokens", 0)
            stats["code_blocks"] += session_stats["code_blocks"]
            stats["code_lines"] += session_stats.get("code_lines", 0)
            stats["lines_written"] += session_stats.get("lines_written", 0)
            stats["lines_edited"] += session_stats.get("lines_edited", 0)
            stats["apologies"] += session_stats["apologies"]
            stats["thinking_blocks"] += session_stats.get("thinking_blocks", 0)

            # Merge tool/language/file counters
            stats["tools_used"].update(session_stats.get("tools_used", {}))
            stats["code_languages"].update(session_stats.get("code_languages", {}))
            stats["files_touched"].update(session_stats.get("files_touched", {}))

            # Track timing
            if session_stats["duration_minutes"] is not None:
                stats["session_durations"].append(session_stats["duration_minutes"])

            stats["response_times"].extend(session_stats.get("response_times", []))

            # Track work hours
            for hour in session_stats.get("active_hours", []):
                stats["work_hours"][hour] += 1

            # Track usage over time
            if session_stats.get("start_time"):
                start = session_stats["start_time"]
                date_key = start.strftime("%Y-%m-%d")
                week_key = start.strftime("%Y-W%W")
                month_key = start.strftime("%Y-%m")

                stats["daily_usage"][date_key] += 1
                stats["weekly_usage"][week_key] += 1
                stats["monthly_usage"][month_key] += 1

                # Track first/last session
                if stats["first_session"] is None or start < stats["first_session"]:
                    stats["first_session"] = start
                if stats["last_session"] is None or start > stats["last_session"]:
                    stats["last_session"] = start

            # Track models
            for model in session_stats.get("models", []):
                stats["models_used"][model] += 1

        # Convert to serializable format
        stats["work_hours"] = dict(stats["work_hours"])
        stats["daily_usage"] = dict(stats["daily_usage"])
        stats["weekly_usage"] = dict(stats["weekly_usage"])
        stats["monthly_usage"] = dict(stats["monthly_usage"])
        stats["models_used"] = dict(stats["models_used"])
        stats["tools_used"] = dict(stats["tools_used"])
        stats["code_languages"] = dict(stats["code_languages"])
        stats["files_touched"] = dict(
            sorted(stats["files_touched"].items(), key=lambda x: -x[1])[:20]
        )

        if stats["first_session"]:
            stats["first_session"] = stats["first_session"].isoformat()
        if stats["last_session"]:
            stats["last_session"] = stats["last_session"].isoformat()

        # Compute per-project statistics
        if stats["sessions"] > 0:
            stats["avg_messages_per_session"] = stats["total_messages"] / stats["sessions"]
            stats["avg_tokens_per_session"] = stats["total_tokens"] / stats["sessions"]
        else:
            stats["avg_messages_per_session"] = 0
            stats["avg_tokens_per_session"] = 0

        return stats

    def _analyze_session(self, jsonl_file: Path) -> Optional[Dict[str, Any]]:
        """
        Analyze a single session file using the shared parser.

        Extracts all statistics from a single JSONL session file, including
        message counts, token usage, timing information, and content analysis.

        Args:
            jsonl_file: Path to session JSONL file

        Returns:
            dict: Session statistics with keys:
                - total_messages, user_messages, assistant_messages, tool_uses
                - total_tokens, input_tokens, output_tokens
                - code_blocks, apologies (content analysis counts)
                - duration_minutes (None if single message)
                - response_times (list of seconds between user->assistant)
                - active_hours (list of hours with activity)
                - start_time, end_time (datetime objects)
                - models (list of model IDs used)
            None: If file cannot be parsed or is empty
        """
        messages = self.parser.parse_file(jsonl_file)
        if not messages:
            return None

        stats = {
            "total_messages": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_uses": 0,
            "tool_errors": 0,
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "code_blocks": 0,
            "code_lines": 0,
            "lines_written": 0,
            "lines_edited": 0,
            "apologies": 0,
            "thinking_blocks": 0,
            "duration_minutes": None,
            "response_times": [],
            "active_hours": [],
            "start_time": None,
            "end_time": None,
            "models": [],
            "tools_used": Counter(),
            "code_languages": Counter(),
            "files_touched": Counter(),
        }

        last_user_time = None
        all_timestamps = []

        for msg in messages:
            # Track timestamps
            if msg.timestamp_dt:
                all_timestamps.append(msg.timestamp_dt)
                stats["active_hours"].append(msg.timestamp_dt.hour)

            if msg.type == "user":
                stats["user_messages"] += 1
                stats["total_messages"] += 1
                last_user_time = msg.timestamp_dt

            elif msg.type == "assistant":
                stats["assistant_messages"] += 1
                stats["total_messages"] += 1

                # Extract usage including cache tokens
                if msg.usage:
                    input_tok = msg.usage.get("input_tokens", 0)
                    output_tok = msg.usage.get("output_tokens", 0)
                    cache_read = msg.usage.get("cache_read_input_tokens", 0)
                    cache_create = msg.usage.get("cache_creation_input_tokens", 0)
                    stats["input_tokens"] += input_tok
                    stats["output_tokens"] += output_tok
                    stats["total_tokens"] += input_tok + output_tok
                    stats["cache_read_tokens"] += cache_read
                    stats["cache_creation_tokens"] += cache_create

                # Track model
                if msg.model and msg.model not in stats["models"]:
                    stats["models"].append(msg.model)

                # Calculate response time
                if last_user_time and msg.timestamp_dt:
                    delta = (msg.timestamp_dt - last_user_time).total_seconds()
                    if 0 < delta < 600:  # Reasonable range (0-10 minutes)
                        stats["response_times"].append(delta)

                # Count thinking blocks
                if msg.thinking:
                    stats["thinking_blocks"] += 1

                # Analyze content for code blocks, languages, and apologies
                if msg.content:
                    code_blocks = re.findall(self.CODE_BLOCK_PATTERN, msg.content)
                    stats["code_blocks"] += len(code_blocks)

                    # Count lines in code blocks
                    for block in code_blocks:
                        # Remove the ``` markers and count lines
                        block_content = block.strip('`').strip()
                        if block_content:
                            # Remove language identifier on first line
                            lines = block_content.split('\n')
                            if lines and not lines[0].strip().startswith('```'):
                                # First line might be language identifier
                                if len(lines[0]) < 20 and not ' ' in lines[0]:
                                    lines = lines[1:]  # Skip language line
                            stats["code_lines"] += len([l for l in lines if l.strip()])

                    # Extract languages from code blocks
                    languages = re.findall(self.CODE_LANG_PATTERN, msg.content)
                    for lang in languages:
                        if lang.lower() not in ('', 'text', 'plaintext', 'output'):
                            stats["code_languages"][lang.lower()] += 1

                    stats["apologies"] += self._count_apologies(msg.content)

                # Count tool calls from assistant messages
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        stats["tool_uses"] += 1
                        tool_name = tc.get("name")
                        if tool_name:
                            stats["tools_used"][tool_name] += 1
                        # Extract file paths from tool inputs
                        tool_input = tc.get("input", {})
                        if tool_input:
                            self._extract_file_paths(tool_input, stats["files_touched"])
                            # Count lines written/edited
                            self._count_code_lines(tool_name, tool_input, stats)

            elif msg.type == "tool_use":
                # Fallback for separate tool_use entries (if any)
                stats["tool_uses"] += 1
                if msg.tool_name:
                    stats["tools_used"][msg.tool_name] += 1
                if msg.tool_input:
                    self._extract_file_paths(msg.tool_input, stats["files_touched"])
                    # Count lines written/edited
                    self._count_code_lines(msg.tool_name, msg.tool_input, stats)

            elif msg.type == "tool_result":
                # Track tool errors
                if msg.error:
                    stats["tool_errors"] += 1

        # Calculate duration
        if all_timestamps:
            stats["start_time"] = min(all_timestamps)
            stats["end_time"] = max(all_timestamps)
            duration = stats["end_time"] - stats["start_time"]
            stats["duration_minutes"] = duration.total_seconds() / 60

        return stats

    def _count_apologies(self, text: str) -> int:
        """
        Count apology patterns in text.

        Searches for self-correction language that may indicate Claude
        made an error and corrected itself. Uses case-insensitive matching.

        Patterns detected:
            - "I'm sorry" / "I am sorry"
            - "apologize" / "apologise"
            - "my mistake"
            - "I was wrong"
            - "correction"
            - "let me fix" / "let me correct"

        Args:
            text: Text content to analyze (typically assistant message)

        Returns:
            int: Total count of apology patterns found
        """
        count = 0
        text_lower = text.lower()
        for pattern in self.APOLOGY_PATTERNS:
            count += len(re.findall(pattern, text_lower))
        return count

    def _extract_file_paths(self, tool_input: Dict[str, Any], files_counter: Counter) -> None:
        """
        Extract file paths from tool input and add to counter.

        Looks for common file path parameters in tool inputs like
        'file_path', 'path', 'file', 'notebook_path'.

        Args:
            tool_input: Dictionary of tool input parameters
            files_counter: Counter to update with found file paths
        """
        path_keys = ['file_path', 'path', 'file', 'notebook_path', 'directory']
        for key in path_keys:
            if key in tool_input:
                path = tool_input[key]
                if isinstance(path, str) and path:
                    # Normalize path - just get the filename or last component
                    if '/' in path:
                        short_path = path.rsplit('/', 1)[-1]
                    else:
                        short_path = path
                    files_counter[short_path] += 1

    def _count_code_lines(self, tool_name: str, tool_input: Dict[str, Any], stats: Dict[str, Any]) -> None:
        """
        Count lines of code written or edited via Write/Edit tools.

        Examines tool inputs to count:
        - Lines written via Write tool (content parameter)
        - Lines changed via Edit tool (new_string parameter)

        Args:
            tool_name: Name of the tool being used
            tool_input: Dictionary of tool input parameters
            stats: Stats dictionary to update with line counts
        """
        if not tool_name or not tool_input:
            return

        tool_name_lower = tool_name.lower()

        # Write tool - count lines in content
        if tool_name_lower == "write":
            content = tool_input.get("content", "")
            if content and isinstance(content, str):
                lines = [l for l in content.split('\n') if l.strip()]
                stats["lines_written"] += len(lines)

        # Edit tool - count lines in new_string
        elif tool_name_lower == "edit":
            new_string = tool_input.get("new_string", "")
            if new_string and isinstance(new_string, str):
                lines = [l for l in new_string.split('\n') if l.strip()]
                stats["lines_edited"] += len(lines)

    def save_json(self, stats: Dict[str, Any], output_path: Path) -> None:
        """
        Save statistics as JSON file.

        Writes the statistics dictionary to a JSON file with pretty formatting
        (2-space indentation). The file is encoded as UTF-8 to handle any
        international characters in project names.

        Args:
            stats: Statistics dictionary from generate()
            output_path: Path for output JSON file (typically stats.json)
        """
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    def save_html(self, stats: Dict[str, Any], output_path: Path) -> None:
        """
        Save statistics as HTML dashboard.

        Generates a self-contained HTML page with:
        - Navigation bar linking to index and stats
        - Summary cards for key metrics
        - Work hours distribution chart
        - Models used badges
        - Session duration statistics
        - Projects table with linkable IDs

        Args:
            stats: Statistics dictionary from generate()
            output_path: Path for output HTML file (typically stats.html)
        """
        generate_stats_html(stats, output_path)
