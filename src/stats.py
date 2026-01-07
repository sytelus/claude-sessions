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

import html
import json
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import SessionParser, ParsedMessage
from .utils import iter_project_dirs


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
            "total_code_blocks": 0,
            "total_apologies": 0,
            "work_hours": Counter(),  # Hour -> count
            "daily_usage": Counter(),  # Date -> count
            "weekly_usage": Counter(),  # Week -> count
            "monthly_usage": Counter(),  # Month -> count
            "all_session_durations": [],
            "all_response_times": [],
            "models_used": Counter(),
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
                aggregate["total_code_blocks"] += project_stats["code_blocks"]
                aggregate["total_apologies"] += project_stats["apologies"]

                # Merge counters
                aggregate["work_hours"].update(project_stats.get("work_hours", {}))
                aggregate["daily_usage"].update(project_stats.get("daily_usage", {}))
                aggregate["weekly_usage"].update(project_stats.get("weekly_usage", {}))
                aggregate["monthly_usage"].update(project_stats.get("monthly_usage", {}))
                aggregate["models_used"].update(project_stats.get("models_used", {}))

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
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "code_blocks": 0,
            "apologies": 0,
            "session_durations": [],
            "response_times": [],
            "work_hours": Counter(),
            "daily_usage": Counter(),
            "weekly_usage": Counter(),
            "monthly_usage": Counter(),
            "models_used": Counter(),
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
            stats["total_tokens"] += session_stats["total_tokens"]
            stats["input_tokens"] += session_stats["input_tokens"]
            stats["output_tokens"] += session_stats["output_tokens"]
            stats["code_blocks"] += session_stats["code_blocks"]
            stats["apologies"] += session_stats["apologies"]

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
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "code_blocks": 0,
            "apologies": 0,
            "duration_minutes": None,
            "response_times": [],
            "active_hours": [],
            "start_time": None,
            "end_time": None,
            "models": [],
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

                # Extract usage
                if msg.usage:
                    input_tok = msg.usage.get("input_tokens", 0)
                    output_tok = msg.usage.get("output_tokens", 0)
                    stats["input_tokens"] += input_tok
                    stats["output_tokens"] += output_tok
                    stats["total_tokens"] += input_tok + output_tok

                # Track model
                if msg.model and msg.model not in stats["models"]:
                    stats["models"].append(msg.model)

                # Calculate response time
                if last_user_time and msg.timestamp_dt:
                    delta = (msg.timestamp_dt - last_user_time).total_seconds()
                    if 0 < delta < 600:  # Reasonable range (0-10 minutes)
                        stats["response_times"].append(delta)

                # Analyze content for code blocks and apologies
                if msg.content:
                    stats["code_blocks"] += len(
                        re.findall(self.CODE_BLOCK_PATTERN, msg.content)
                    )
                    stats["apologies"] += self._count_apologies(msg.content)

            elif msg.type == "tool_use":
                stats["tool_uses"] += 1

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
        - Summary cards for key metrics (sessions, messages, tokens, code blocks)
        - Work hours bar chart (24-hour distribution)
        - Models used badges
        - Session duration statistics
        - Projects table sorted by token usage

        The HTML uses:
        - Inline CSS (no external dependencies)
        - CSS variables for theming
        - Responsive grid layout
        - Pure CSS bar charts (no JavaScript required)

        Args:
            stats: Statistics dictionary from generate()
            output_path: Path for output HTML file (typically stats.html)
        """
        agg = stats["aggregate"]
        projects = stats["projects"]

        # Generate work hours chart data
        work_hours_data = [agg["work_hours"].get(h, 0) for h in range(24)]
        max_hour_count = max(work_hours_data) if work_hours_data else 1

        # Generate monthly trend data
        monthly_data = agg.get("monthly_usage", {})
        months = list(monthly_data.keys())[-12:]  # Last 12 months
        month_counts = [monthly_data.get(m, 0) for m in months]

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Sessions Statistics</title>
    <style>
        :root {{
            --primary: #6366f1;
            --success: #22c55e;
            --warning: #f59e0b;
            --bg: #f8fafc;
            --card: white;
            --text: #1e293b;
            --muted: #64748b;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text);
            background: var(--bg);
            margin: 0;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: var(--primary); margin-bottom: 0; }}
        .subtitle {{ color: var(--muted); margin-top: 5px; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .card {{
            background: var(--card);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card-title {{ color: var(--muted); font-size: 0.875rem; margin-bottom: 5px; }}
        .card-value {{ font-size: 2rem; font-weight: bold; color: var(--text); }}
        .card-detail {{ font-size: 0.875rem; color: var(--muted); margin-top: 5px; }}
        .section {{ margin: 40px 0; }}
        .section-title {{ font-size: 1.25rem; margin-bottom: 20px; color: var(--text); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--card);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        th {{ background: #f1f5f9; font-weight: 600; color: var(--muted); }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover {{ background: #f8fafc; }}
        .chart-container {{
            background: var(--card);
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .bar-chart {{
            display: flex;
            align-items: flex-end;
            height: 150px;
            gap: 4px;
            padding: 10px 0;
        }}
        .bar {{
            flex: 1;
            background: var(--primary);
            border-radius: 4px 4px 0 0;
            min-height: 4px;
            position: relative;
        }}
        .bar:hover {{ background: #4f46e5; }}
        .bar-label {{
            position: absolute;
            bottom: -25px;
            left: 50%;
            transform: translateX(-50%);
            font-size: 10px;
            color: var(--muted);
        }}
        .models-list {{ display: flex; flex-wrap: wrap; gap: 10px; }}
        .model-badge {{
            background: #e0e7ff;
            color: var(--primary);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.875rem;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            color: var(--muted);
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Claude Sessions Statistics</h1>
        <p class="subtitle">Generated: {html.escape(stats['generated_at'])}</p>

        <div class="grid">
            <div class="card">
                <div class="card-title">Total Sessions</div>
                <div class="card-value">{agg['total_sessions']:,}</div>
                <div class="card-detail">{len(projects)} projects</div>
            </div>
            <div class="card">
                <div class="card-title">Total Messages</div>
                <div class="card-value">{agg['total_messages']:,}</div>
                <div class="card-detail">
                    {agg['total_user_messages']:,} user / {agg['total_assistant_messages']:,} assistant
                </div>
            </div>
            <div class="card">
                <div class="card-title">Total Tokens</div>
                <div class="card-value">{agg['total_tokens']:,}</div>
                <div class="card-detail">
                    {agg['total_input_tokens']:,} in / {agg['total_output_tokens']:,} out
                </div>
            </div>
            <div class="card">
                <div class="card-title">Code Blocks</div>
                <div class="card-value">{agg['total_code_blocks']:,}</div>
                <div class="card-detail">Generated by Claude</div>
            </div>
            <div class="card">
                <div class="card-title">Avg Messages/Session</div>
                <div class="card-value">{agg['avg_messages_per_session']:.1f}</div>
            </div>
            <div class="card">
                <div class="card-title">Avg Tokens/Session</div>
                <div class="card-value">{agg['avg_tokens_per_session']:,.0f}</div>
            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Work Hours Distribution</h2>
            <div class="chart-container">
                <div class="bar-chart">
"""
        # Generate hour bars
        for hour in range(24):
            count = work_hours_data[hour]
            height_pct = (count / max_hour_count * 100) if max_hour_count > 0 else 0
            label = f"{hour:02d}"
            html_content += f'                    <div class="bar" style="height: {height_pct}%" title="{count} sessions at {label}:00"><span class="bar-label">{label}</span></div>\n'

        html_content += """                </div>
            </div>
        </div>
"""

        # Models used section
        if agg["models_used"]:
            html_content += """
        <div class="section">
            <h2 class="section-title">Models Used</h2>
            <div class="card">
                <div class="models-list">
"""
            for model, count in sorted(agg["models_used"].items(), key=lambda x: -x[1]):
                html_content += f'                    <span class="model-badge">{html.escape(model)} ({count})</span>\n'

            html_content += """                </div>
            </div>
        </div>
"""

        # Timing statistics
        if agg.get("session_duration_stats"):
            dur = agg["session_duration_stats"]
            html_content += f"""
        <div class="section">
            <h2 class="section-title">Session Duration Statistics</h2>
            <div class="grid">
                <div class="card">
                    <div class="card-title">Average Duration</div>
                    <div class="card-value">{dur['avg_minutes']:.1f} min</div>
                </div>
                <div class="card">
                    <div class="card-title">Median Duration</div>
                    <div class="card-value">{dur['median_minutes']:.1f} min</div>
                </div>
                <div class="card">
                    <div class="card-title">Longest Session</div>
                    <div class="card-value">{dur['max_minutes']:.1f} min</div>
                </div>
            </div>
        </div>
"""

        # Projects table
        html_content += """
        <div class="section">
            <h2 class="section-title">Projects</h2>
            <table>
                <thead>
                    <tr>
                        <th>Project</th>
                        <th>Sessions</th>
                        <th>Messages</th>
                        <th>Tokens</th>
                        <th>Code Blocks</th>
                    </tr>
                </thead>
                <tbody>
"""
        for proj in sorted(projects, key=lambda x: -x["total_tokens"]):
            # Format project name (remove path prefix)
            name = proj["project_name"]
            if name.startswith("-"):
                name = name.replace("-", "/")[1:]  # Convert back to path format
            if len(name) > 50:
                name = "..." + name[-47:]

            html_content += f"""                    <tr>
                        <td title="{html.escape(proj['project_name'])}">{html.escape(name)}</td>
                        <td>{proj['sessions']:,}</td>
                        <td>{proj['total_messages']:,}</td>
                        <td>{proj['total_tokens']:,}</td>
                        <td>{proj['code_blocks']:,}</td>
                    </tr>
"""

        html_content += """                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>Generated by Claude Sessions</p>
        </div>
    </div>
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
