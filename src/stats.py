#!/usr/bin/env python3
"""
Statistics generation for Claude Sessions.

Computes comprehensive statistics about Claude usage patterns.
"""

import html
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class StatisticsGenerator:
    """Generates comprehensive statistics from Claude session data."""

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

    def generate(self, output_dir: Path) -> Dict:
        """
        Generate statistics for all backed up sessions.

        Args:
            output_dir: Output directory containing project folders

        Returns:
            Dict containing per-project and aggregate statistics
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
        for project_dir in output_dir.iterdir():
            if not project_dir.is_dir():
                continue
            if project_dir.name in ["markdown", "html", "data"]:
                continue

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

    def _compute_project_stats(self, project_dir: Path) -> Optional[Dict]:
        """Compute statistics for a single project."""
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

    def _analyze_session(self, jsonl_file: Path) -> Optional[Dict]:
        """Analyze a single session file."""
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

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entry_type = entry.get("type")

                        # Parse timestamp
                        timestamp = self._parse_timestamp(entry.get("timestamp"))
                        if timestamp:
                            all_timestamps.append(timestamp)
                            stats["active_hours"].append(timestamp.hour)

                        if entry_type == "user":
                            stats["user_messages"] += 1
                            stats["total_messages"] += 1
                            last_user_time = timestamp

                        elif entry_type == "assistant":
                            stats["assistant_messages"] += 1
                            stats["total_messages"] += 1

                            message = entry.get("message", {})

                            # Extract usage
                            usage = message.get("usage", {})
                            input_tok = usage.get("input_tokens", 0)
                            output_tok = usage.get("output_tokens", 0)
                            stats["input_tokens"] += input_tok
                            stats["output_tokens"] += output_tok
                            stats["total_tokens"] += input_tok + output_tok

                            # Track model
                            model = message.get("model")
                            if model and model not in stats["models"]:
                                stats["models"].append(model)

                            # Calculate response time
                            if last_user_time and timestamp:
                                delta = (timestamp - last_user_time).total_seconds()
                                if 0 < delta < 600:  # Reasonable range (0-10 minutes)
                                    stats["response_times"].append(delta)

                            # Analyze content
                            content = message.get("content", [])
                            if isinstance(content, list):
                                for item in content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        text = item.get("text", "")
                                        stats["code_blocks"] += len(
                                            re.findall(self.CODE_BLOCK_PATTERN, text)
                                        )
                                        stats["apologies"] += self._count_apologies(text)

                        elif entry_type == "tool_use":
                            stats["tool_uses"] += 1

                    except json.JSONDecodeError:
                        continue

        except Exception:
            return None

        # Calculate duration
        if all_timestamps:
            stats["start_time"] = min(all_timestamps)
            stats["end_time"] = max(all_timestamps)
            duration = stats["end_time"] - stats["start_time"]
            stats["duration_minutes"] = duration.total_seconds() / 60

        return stats

    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp string."""
        if not timestamp_str:
            return None
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except Exception:
            return None

    def _count_apologies(self, text: str) -> int:
        """Count apology patterns in text."""
        count = 0
        text_lower = text.lower()
        for pattern in self.APOLOGY_PATTERNS:
            count += len(re.findall(pattern, text_lower))
        return count

    def save_json(self, stats: Dict, output_path: Path):
        """Save statistics as JSON."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    def save_html(self, stats: Dict, output_path: Path):
        """Save statistics as HTML dashboard."""
        agg = stats["aggregate"]
        projects = stats["projects"]

        # Generate work hours chart data
        work_hours_data = [agg["work_hours"].get(str(h), 0) for h in range(24)]
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
