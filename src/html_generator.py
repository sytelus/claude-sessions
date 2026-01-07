#!/usr/bin/env python3
"""
HTML generation for Claude Sessions.

This module provides shared HTML templates, CSS styles, and generators for
the index page and statistics dashboard. It creates a unified, modern UI
for browsing Claude Code session backups.

Features:
    - Shared CSS design system with consistent theming
    - Dark mode support
    - Index page with project/session navigation and search
    - Statistics dashboard with rich visualizations
    - Activity calendar heatmap
    - Cost estimation
    - Tool usage breakdown

Classes:
    HtmlGenerator: Main class for generating HTML pages
"""

import hashlib
import html
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .parser import SessionParser
from .utils import iter_project_dirs, extract_text

# Cost per 1M tokens (approximate, using Claude 3.5 Sonnet pricing as baseline)
# These are rough estimates - actual costs vary by model
COST_PER_1M_INPUT_TOKENS = 3.00   # $3 per 1M input tokens
COST_PER_1M_OUTPUT_TOKENS = 15.00  # $15 per 1M output tokens
COST_PER_1M_CACHE_READ = 0.30     # $0.30 per 1M cache read tokens
COST_PER_1M_CACHE_CREATE = 3.75   # $3.75 per 1M cache creation tokens


def estimate_cost(stats: Dict[str, Any]) -> Dict[str, float]:
    """
    Estimate API costs based on token usage.

    Args:
        stats: Aggregate statistics dictionary

    Returns:
        Dictionary with cost breakdown
    """
    input_tokens = stats.get("total_input_tokens", 0)
    output_tokens = stats.get("total_output_tokens", 0)
    cache_read = stats.get("total_cache_read_tokens", 0)
    cache_create = stats.get("total_cache_creation_tokens", 0)

    input_cost = (input_tokens / 1_000_000) * COST_PER_1M_INPUT_TOKENS
    output_cost = (output_tokens / 1_000_000) * COST_PER_1M_OUTPUT_TOKENS
    cache_read_cost = (cache_read / 1_000_000) * COST_PER_1M_CACHE_READ
    cache_create_cost = (cache_create / 1_000_000) * COST_PER_1M_CACHE_CREATE

    total = input_cost + output_cost + cache_read_cost + cache_create_cost

    # Calculate savings from cache
    cache_savings = (cache_read / 1_000_000) * (COST_PER_1M_INPUT_TOKENS - COST_PER_1M_CACHE_READ)

    return {
        "input": input_cost,
        "output": output_cost,
        "cache_read": cache_read_cost,
        "cache_create": cache_create_cost,
        "total": total,
        "cache_savings": cache_savings,
    }


# Shared CSS for all generated HTML pages
SHARED_CSS = """
:root {
    --primary: #6366f1;
    --primary-dark: #4f46e5;
    --primary-light: #e0e7ff;
    --success: #22c55e;
    --success-light: #dcfce7;
    --warning: #f59e0b;
    --warning-light: #fef3c7;
    --danger: #ef4444;
    --danger-light: #fee2e2;
    --user-color: #3b82f6;
    --assistant-color: #10b981;
    --tool-color: #f59e0b;
    --bg: #f8fafc;
    --bg-alt: #f1f5f9;
    --card: white;
    --text: #1e293b;
    --text-secondary: #475569;
    --muted: #64748b;
    --border: #e2e8f0;
    --shadow: 0 1px 3px rgba(0,0,0,0.1);
    --shadow-lg: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
    --radius: 12px;
    --radius-sm: 8px;
}

/* Dark mode */
[data-theme="dark"] {
    --primary: #818cf8;
    --primary-dark: #6366f1;
    --primary-light: #312e81;
    --success: #4ade80;
    --success-light: #14532d;
    --warning: #fbbf24;
    --warning-light: #78350f;
    --danger: #f87171;
    --danger-light: #7f1d1d;
    --bg: #0f172a;
    --bg-alt: #1e293b;
    --card: #1e293b;
    --text: #f1f5f9;
    --text-secondary: #cbd5e1;
    --muted: #94a3b8;
    --border: #334155;
}

* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
    line-height: 1.6;
    color: var(--text);
    background: var(--bg);
    margin: 0;
    padding: 0;
    transition: background 0.3s, color 0.3s;
}
.container {
    max-width: 1400px;
    margin: 0 auto;
    padding: 24px;
}
a { color: var(--primary); text-decoration: none; }
a:hover { color: var(--primary-dark); text-decoration: underline; }

/* Navigation */
.nav {
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 24px;
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: var(--shadow);
}
.nav-content {
    max-width: 1400px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 24px;
}
.nav-brand {
    font-weight: 700;
    font-size: 1.125rem;
    color: var(--primary);
    display: flex;
    align-items: center;
    gap: 8px;
}
.nav-links {
    display: flex;
    gap: 24px;
    align-items: center;
}
.nav-links a {
    color: var(--text-secondary);
    font-weight: 500;
    padding: 4px 0;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
}
.nav-links a:hover, .nav-links a.active {
    color: var(--primary);
    border-bottom-color: var(--primary);
    text-decoration: none;
}

/* Theme toggle */
.theme-toggle {
    background: var(--bg-alt);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 6px 12px;
    cursor: pointer;
    font-size: 0.875rem;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
}
.theme-toggle:hover { background: var(--primary-light); }

/* Header */
.header {
    padding: 32px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 32px;
}
.header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 8px 0;
}
.header .subtitle {
    color: var(--muted);
    font-size: 1rem;
    margin: 0;
}

/* Search */
.search-container {
    margin-bottom: 24px;
}
.search-input {
    width: 100%;
    max-width: 400px;
    padding: 12px 16px;
    padding-left: 44px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-size: 1rem;
    background: var(--card);
    color: var(--text);
    transition: all 0.2s;
}
.search-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px var(--primary-light);
}
.search-wrapper {
    position: relative;
    display: inline-block;
    width: 100%;
    max-width: 400px;
}
.search-icon {
    position: absolute;
    left: 14px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
}

/* Cards */
.card {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 20px;
    transition: all 0.2s;
}
.card:hover { box-shadow: var(--shadow-lg); }
.card-title {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
}
.card-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--text);
    line-height: 1.2;
}
.card-value.money { color: var(--success); }
.card-value.warning { color: var(--warning); }
.card-detail {
    font-size: 0.875rem;
    color: var(--muted);
    margin-top: 4px;
}

/* Grid layouts */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
}

/* Project cards */
.projects-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 24px;
}
.project-card {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
    transition: all 0.2s;
}
.project-card:hover {
    box-shadow: var(--shadow-lg);
    transform: translateY(-2px);
}
.project-card.hidden { display: none; }
.project-header {
    padding: 20px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(135deg, var(--primary-light) 0%, var(--card) 100%);
}
.project-name {
    font-weight: 600;
    font-size: 1rem;
    color: var(--text);
    margin: 0 0 4px 0;
    word-break: break-all;
}
.project-path {
    font-size: 0.75rem;
    color: var(--muted);
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
}
.project-stats {
    display: flex;
    gap: 16px;
    padding: 12px 20px;
    background: var(--bg-alt);
    font-size: 0.875rem;
}
.project-stat {
    display: flex;
    align-items: center;
    gap: 4px;
    color: var(--text-secondary);
}
.project-stat strong { color: var(--text); }
.sessions-list {
    padding: 12px 20px;
    max-height: 350px;
    overflow-y: auto;
}
.session-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    margin: 4px 0;
    border-radius: var(--radius-sm);
    background: var(--bg);
    transition: all 0.2s;
    gap: 12px;
}
.session-item:hover { background: var(--primary-light); }
.session-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    flex: 1;
}
.session-id {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 0.8rem;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.session-date {
    font-size: 0.75rem;
    color: var(--muted);
}
.session-preview {
    font-size: 0.75rem;
    color: var(--text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
    font-style: italic;
}
.session-links {
    display: flex;
    gap: 8px;
    flex-shrink: 0;
}
.session-link {
    padding: 4px 10px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 500;
    background: var(--primary-light);
    color: var(--primary);
    transition: all 0.2s;
}
.session-link:hover {
    background: var(--primary);
    color: white;
    text-decoration: none;
}

/* Tables */
table {
    width: 100%;
    border-collapse: collapse;
    background: var(--card);
    border-radius: var(--radius);
    overflow: hidden;
    box-shadow: var(--shadow);
}
th, td {
    padding: 14px 16px;
    text-align: left;
}
th {
    background: var(--bg-alt);
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
}
td { border-top: 1px solid var(--border); }
tr:hover td { background: var(--bg); }
.table-link { font-weight: 500; }

/* Section */
.section {
    margin-bottom: 48px;
}
.section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
}
.section-title {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--text);
    margin: 0;
}

/* Charts */
.chart-container {
    background: var(--card);
    padding: 24px;
    border-radius: var(--radius);
    box-shadow: var(--shadow);
}
.bar-chart {
    display: flex;
    align-items: flex-end;
    height: 120px;
    gap: 3px;
    padding-bottom: 24px;
}
.bar {
    flex: 1;
    background: linear-gradient(180deg, var(--primary) 0%, var(--primary-dark) 100%);
    border-radius: 4px 4px 0 0;
    min-height: 4px;
    position: relative;
    transition: opacity 0.2s;
}
.bar:hover { opacity: 0.8; }
.bar-label {
    position: absolute;
    bottom: -20px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 9px;
    color: var(--muted);
}

/* Activity Calendar */
.calendar-container {
    background: var(--card);
    padding: 24px;
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow-x: auto;
}
.calendar-grid {
    display: flex;
    gap: 3px;
    min-width: fit-content;
}
.calendar-week {
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.calendar-day {
    width: 12px;
    height: 12px;
    border-radius: 2px;
    background: var(--bg-alt);
}
.calendar-day[data-level="1"] { background: #c6e48b; }
.calendar-day[data-level="2"] { background: #7bc96f; }
.calendar-day[data-level="3"] { background: #449335; }
.calendar-day[data-level="4"] { background: #196127; }
[data-theme="dark"] .calendar-day[data-level="1"] { background: #0e4429; }
[data-theme="dark"] .calendar-day[data-level="2"] { background: #006d32; }
[data-theme="dark"] .calendar-day[data-level="3"] { background: #26a641; }
[data-theme="dark"] .calendar-day[data-level="4"] { background: #39d353; }
.calendar-legend {
    display: flex;
    align-items: center;
    gap: 4px;
    margin-top: 12px;
    font-size: 0.75rem;
    color: var(--muted);
}
.calendar-months {
    display: flex;
    gap: 3px;
    margin-bottom: 8px;
    font-size: 0.7rem;
    color: var(--muted);
}
.calendar-month { width: 48px; }

/* Tool usage */
.tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 12px;
}
.tool-item {
    background: var(--bg-alt);
    border-radius: var(--radius-sm);
    padding: 16px;
    text-align: center;
}
.tool-name {
    font-weight: 600;
    font-size: 0.875rem;
    color: var(--text);
    margin-bottom: 4px;
}
.tool-count {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--primary);
}
.tool-bar {
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    margin-top: 8px;
    overflow: hidden;
}
.tool-bar-fill {
    height: 100%;
    background: var(--primary);
    border-radius: 2px;
}

/* Trend chart */
.trend-chart {
    height: 100px;
    display: flex;
    align-items: flex-end;
    gap: 2px;
    padding-bottom: 20px;
}
.trend-bar {
    flex: 1;
    background: var(--primary-light);
    border-radius: 2px 2px 0 0;
    min-height: 2px;
    position: relative;
}
.trend-bar:hover {
    background: var(--primary);
}

/* Language badges */
.lang-badge {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
    background: var(--bg-alt);
    color: var(--text);
    margin: 4px;
}
.lang-badge .count {
    background: var(--primary);
    color: white;
    padding: 2px 8px;
    border-radius: 12px;
    margin-left: 8px;
    font-size: 0.7rem;
}

/* Badges */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 500;
}
.badge-primary { background: var(--primary-light); color: var(--primary); }
.badge-success { background: var(--success-light); color: var(--success); }
.badge-warning { background: var(--warning-light); color: var(--warning); }
.badges-list { display: flex; flex-wrap: wrap; gap: 8px; }

/* Two column layout */
.two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
}
@media (max-width: 900px) {
    .two-col { grid-template-columns: 1fr; }
}

/* Footer */
.footer {
    text-align: center;
    padding: 32px 0;
    margin-top: 48px;
    border-top: 1px solid var(--border);
    color: var(--muted);
    font-size: 0.875rem;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-alt); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }

/* Empty state */
.empty-state {
    text-align: center;
    padding: 48px;
    color: var(--muted);
}
.empty-state h3 { color: var(--text-secondary); margin-bottom: 8px; }

/* Insights */
.insight-card {
    background: linear-gradient(135deg, var(--primary-light) 0%, var(--card) 100%);
    border-left: 4px solid var(--primary);
}
.insight-card .card-title { color: var(--primary); }
"""

# JavaScript for interactivity
SHARED_JS = """
// Theme toggle
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    updateThemeIcon();
}

function updateThemeIcon() {
    const btn = document.querySelector('.theme-toggle');
    if (!btn) return;
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    btn.innerHTML = isDark ? '☀️ Light' : '🌙 Dark';
}

// Initialize theme from localStorage
(function() {
    const saved = localStorage.getItem('theme');
    if (saved) {
        document.documentElement.setAttribute('data-theme', saved);
    } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
    document.addEventListener('DOMContentLoaded', updateThemeIcon);
})();

// Search functionality
function initSearch() {
    const input = document.getElementById('search-input');
    if (!input) return;

    input.addEventListener('input', function(e) {
        const query = e.target.value.toLowerCase();
        const cards = document.querySelectorAll('.project-card');

        cards.forEach(card => {
            const name = card.querySelector('.project-name')?.textContent.toLowerCase() || '';
            const path = card.querySelector('.project-path')?.textContent.toLowerCase() || '';
            const sessions = card.querySelectorAll('.session-preview');
            let sessionMatch = false;
            sessions.forEach(s => {
                if (s.textContent.toLowerCase().includes(query)) sessionMatch = true;
            });

            if (name.includes(query) || path.includes(query) || sessionMatch) {
                card.classList.remove('hidden');
            } else {
                card.classList.add('hidden');
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', initSearch);
"""


def get_project_id(project_name: str) -> str:
    """Generate a deterministic HTML ID for a project."""
    hash_val = hashlib.md5(project_name.encode()).hexdigest()[:8]
    return f"project-{hash_val}"


def format_project_display_name(project_name: str) -> str:
    """Convert project directory name to readable display name."""
    if project_name.startswith("-"):
        name = project_name.replace("-", "/")[1:]
    else:
        name = project_name
    return name


def format_short_name(project_name: str, max_len: int = 40) -> str:
    """Get a shortened display name for a project."""
    name = format_project_display_name(project_name)
    if len(name) > max_len:
        return "..." + name[-(max_len - 3):]
    return name


def generate_calendar_html(daily_usage: Dict[str, int]) -> str:
    """
    Generate GitHub-style activity calendar HTML.

    Args:
        daily_usage: Dictionary of date strings to session counts

    Returns:
        HTML string for the calendar
    """
    if not daily_usage:
        return '<p class="muted">No activity data available</p>'

    # Get date range (last 365 days or available data)
    today = datetime.now().date()
    start_date = today - timedelta(days=364)

    # Find max for color scaling
    max_count = max(daily_usage.values()) if daily_usage else 1

    # Generate weeks
    weeks_html = []
    current_date = start_date

    # Align to start of week (Sunday)
    while current_date.weekday() != 6:  # 6 = Sunday
        current_date -= timedelta(days=1)

    months_seen = set()
    month_markers = []

    while current_date <= today:
        week_html = ['<div class="calendar-week">']
        for _ in range(7):
            if current_date <= today:
                date_str = current_date.strftime("%Y-%m-%d")
                count = daily_usage.get(date_str, 0)

                # Determine level (0-4)
                if count == 0:
                    level = 0
                elif count <= max_count * 0.25:
                    level = 1
                elif count <= max_count * 0.5:
                    level = 2
                elif count <= max_count * 0.75:
                    level = 3
                else:
                    level = 4

                month = current_date.strftime("%b")
                if month not in months_seen and current_date.day <= 7:
                    months_seen.add(month)
                    month_markers.append((len(weeks_html), month))

                week_html.append(
                    f'<div class="calendar-day" data-level="{level}" '
                    f'title="{date_str}: {count} sessions"></div>'
                )
            else:
                week_html.append('<div class="calendar-day" style="visibility:hidden"></div>')
            current_date += timedelta(days=1)
        week_html.append('</div>')
        weeks_html.append(''.join(week_html))

    calendar = f'''
        <div class="calendar-grid">
            {''.join(weeks_html)}
        </div>
        <div class="calendar-legend">
            Less
            <div class="calendar-day" data-level="0"></div>
            <div class="calendar-day" data-level="1"></div>
            <div class="calendar-day" data-level="2"></div>
            <div class="calendar-day" data-level="3"></div>
            <div class="calendar-day" data-level="4"></div>
            More
        </div>
    '''

    return calendar


class HtmlGenerator:
    """
    Generates HTML pages for browsing Claude session backups.

    Creates index.html with project navigation and session links,
    using a shared design system with stats.html.
    """

    def __init__(self) -> None:
        self.parser = SessionParser()

    def generate_index(self, output_dir: Path) -> None:
        """
        Generate index.html with project and session navigation.

        Creates a browsable index page showing:
        - Search functionality
        - Quick stats summary
        - All projects with session lists and previews
        - Direct links to HTML-formatted conversations

        Args:
            output_dir: Root output directory (claude-sessions folder)
        """
        projects_data = self._collect_projects_data(output_dir)

        # Calculate totals
        total_sessions = sum(p["session_count"] for p in projects_data)
        total_projects = len(projects_data)

        # Recent sessions across all projects
        all_sessions = []
        for proj in projects_data:
            for session in proj["sessions"]:
                all_sessions.append({
                    **session,
                    "project": proj["name"],
                    "project_display": format_short_name(proj["name"], 30)
                })

        # Sort by date and get recent
        recent_sessions = sorted(
            [s for s in all_sessions if s.get("date")],
            key=lambda x: x["date"],
            reverse=True
        )[:10]

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Sessions</title>
    <style>{SHARED_CSS}</style>
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
                <a href="index.html" class="active">Browse</a>
                <a href="stats.html">Statistics</a>
                <button class="theme-toggle" onclick="toggleTheme()">🌙 Dark</button>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="header">
            <h1>Session Browser</h1>
            <p class="subtitle">Browse and view your Claude Code conversations</p>
        </div>

        <div class="search-container">
            <div class="search-wrapper">
                <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="11" cy="11" r="8"></circle>
                    <path d="M21 21l-4.35-4.35"></path>
                </svg>
                <input type="text" id="search-input" class="search-input" placeholder="Search projects and sessions...">
            </div>
        </div>

        <div class="stats-grid">
            <div class="card">
                <div class="card-title">Projects</div>
                <div class="card-value">{total_projects:,}</div>
            </div>
            <div class="card">
                <div class="card-title">Sessions</div>
                <div class="card-value">{total_sessions:,}</div>
            </div>
            <div class="card">
                <div class="card-title">Last Updated</div>
                <div class="card-value" style="font-size: 1rem;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </div>
"""

        # Recent sessions section
        if recent_sessions:
            html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Recent Sessions</h2>
            </div>
            <div class="card" style="padding: 0; overflow: hidden;">
                <div style="max-height: 300px; overflow-y: auto;">
"""
            for session in recent_sessions:
                html_path = f"{session['project']}/html/{session['id']}.html"
                preview = html.escape(session.get('preview', '')[:60]) if session.get('preview') else ''
                html_content += f"""
                    <div class="session-item" style="margin: 0; border-radius: 0; border-bottom: 1px solid var(--border);">
                        <div class="session-info">
                            <span class="session-id">{html.escape(session['project_display'])}</span>
                            <span class="session-date">{html.escape(session.get('date', ''))}</span>
                            {f'<span class="session-preview">{preview}...</span>' if preview else ''}
                        </div>
                        <div class="session-links">
                            <a href="{html.escape(html_path)}" class="session-link">View</a>
                        </div>
                    </div>
"""
            html_content += """
                </div>
            </div>
        </div>
"""

        html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Projects</h2>
            </div>
            <div class="projects-grid">
"""

        # Generate project cards
        for proj in sorted(projects_data, key=lambda x: -x["session_count"]):
            project_id = get_project_id(proj["name"])
            display_name = format_short_name(proj["name"])
            full_path = format_project_display_name(proj["name"])

            html_content += f"""
                <div class="project-card" id="{project_id}">
                    <div class="project-header">
                        <h3 class="project-name">{html.escape(display_name)}</h3>
                        <div class="project-path" title="{html.escape(full_path)}">{html.escape(full_path[:60] + '...' if len(full_path) > 60 else full_path)}</div>
                    </div>
                    <div class="project-stats">
                        <div class="project-stat"><strong>{proj['session_count']}</strong> sessions</div>
                    </div>
                    <div class="sessions-list">
"""

            # Add session items with previews
            for session in proj["sessions"][:20]:  # Limit to 20 most recent
                session_id = session["id"]
                session_date = session.get("date", "")
                preview = html.escape(session.get("preview", "")[:50]) if session.get("preview") else ""
                html_path = f"{proj['name']}/html/{session_id}.html"

                html_content += f"""
                        <div class="session-item">
                            <div class="session-info">
                                <span class="session-id" title="{html.escape(session_id)}">{html.escape(session_id[:20])}...</span>
                                <span class="session-date">{html.escape(session_date)}</span>
                                {f'<span class="session-preview" title="{preview}">{preview}...</span>' if preview else ''}
                            </div>
                            <div class="session-links">
                                <a href="{html.escape(html_path)}" class="session-link">View</a>
                            </div>
                        </div>
"""

            if proj["session_count"] > 20:
                html_content += f"""
                        <div class="session-item" style="justify-content: center; color: var(--muted);">
                            +{proj['session_count'] - 20} more sessions
                        </div>
"""

            html_content += """
                    </div>
                </div>
"""

        if not projects_data:
            html_content += """
                <div class="empty-state">
                    <h3>No sessions found</h3>
                    <p>Run a backup to populate this page.</p>
                </div>
"""

        html_content += f"""
            </div>
        </div>

        <div class="footer">
            <p>Generated by Claude Sessions</p>
        </div>
    </div>
    <script>{SHARED_JS}</script>
</body>
</html>
"""

        with open(output_dir / "index.html", "w", encoding="utf-8") as f:
            f.write(html_content)

    def _collect_projects_data(self, output_dir: Path) -> List[Dict[str, Any]]:
        """
        Collect project and session data for index generation.

        Args:
            output_dir: Root output directory

        Returns:
            List of project dictionaries with session info
        """
        projects = []

        for project_dir in iter_project_dirs(output_dir):
            sessions = []
            html_dir = project_dir / "html"

            # Get session info from JSONL files
            for jsonl_file in sorted(
                project_dir.glob("*.jsonl"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            ):
                session_id = jsonl_file.stem

                # Get date and preview from first message
                date_str = ""
                preview = ""
                try:
                    messages = self.parser.parse_file(jsonl_file)
                    if messages:
                        # Get date
                        if messages[0].timestamp_dt:
                            date_str = messages[0].timestamp_dt.strftime("%Y-%m-%d %H:%M")

                        # Get preview from first user message
                        for msg in messages:
                            if msg.type == "user" and msg.content:
                                preview = msg.content.strip()[:100]
                                break
                except Exception:
                    pass

                # Check if HTML exists
                html_exists = (html_dir / f"{session_id}.html").exists()

                sessions.append({
                    "id": session_id,
                    "date": date_str,
                    "preview": preview,
                    "html_exists": html_exists,
                })

            if sessions:
                projects.append({
                    "name": project_dir.name,
                    "session_count": len(sessions),
                    "sessions": sessions,
                })

        return projects


def generate_stats_html(stats: Dict[str, Any], output_path: Path) -> None:
    """
    Generate statistics HTML dashboard with modern styling.

    Creates a comprehensive statistics page with:
    - Cost estimation
    - Activity calendar heatmap
    - Summary metric cards
    - Tool usage breakdown
    - Work hours distribution
    - Daily trend chart
    - Code languages
    - Models used
    - Response time stats
    - Projects table

    Args:
        stats: Statistics dictionary from StatisticsGenerator
        output_path: Path for output HTML file
    """
    agg = stats["aggregate"]
    projects = stats["projects"]

    # Calculate costs
    costs = estimate_cost(agg)

    # Work hours chart data
    work_hours_data = [agg["work_hours"].get(str(h), agg["work_hours"].get(h, 0)) for h in range(24)]
    max_hour_count = max(work_hours_data) if work_hours_data else 1

    # Daily usage for trend chart (last 30 days)
    daily_usage = agg.get("daily_usage", {})
    sorted_days = sorted(daily_usage.items())[-30:]
    max_daily = max([v for _, v in sorted_days]) if sorted_days else 1

    # Generate calendar
    calendar_html = generate_calendar_html(daily_usage)

    # Get top tools
    tools_used = agg.get("tools_used", {})
    top_tools = sorted(tools_used.items(), key=lambda x: -x[1])[:12]
    max_tool_count = max([c for _, c in top_tools]) if top_tools else 1

    # Get top languages
    code_languages = agg.get("code_languages", {})
    top_languages = sorted(code_languages.items(), key=lambda x: -x[1])[:10]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Statistics - Claude Sessions</title>
    <style>{SHARED_CSS}</style>
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
                <a href="index.html">Browse</a>
                <a href="stats.html" class="active">Statistics</a>
                <button class="theme-toggle" onclick="toggleTheme()">🌙 Dark</button>
            </div>
        </div>
    </nav>

    <div class="container">
        <div class="header">
            <h1>Usage Statistics</h1>
            <p class="subtitle">Generated: {html.escape(stats['generated_at'])}</p>
        </div>

        <!-- Cost & Overview -->
        <div class="stats-grid">
            <div class="card insight-card">
                <div class="card-title">Estimated Cost</div>
                <div class="card-value money">${costs['total']:.2f}</div>
                <div class="card-detail">${costs['cache_savings']:.2f} saved via caching</div>
            </div>
            <div class="card">
                <div class="card-title">Total Sessions</div>
                <div class="card-value">{agg['total_sessions']:,}</div>
                <div class="card-detail">{len(projects)} projects</div>
            </div>
            <div class="card">
                <div class="card-title">Total Messages</div>
                <div class="card-value">{agg['total_messages']:,}</div>
                <div class="card-detail">{agg['total_user_messages']:,} user / {agg['total_assistant_messages']:,} assistant</div>
            </div>
            <div class="card">
                <div class="card-title">Total Tokens</div>
                <div class="card-value">{agg['total_tokens']:,}</div>
                <div class="card-detail">{agg['total_input_tokens']:,} in / {agg['total_output_tokens']:,} out</div>
            </div>
            <div class="card">
                <div class="card-title">Tool Calls</div>
                <div class="card-value">{agg.get('total_tool_uses', 0):,}</div>
                <div class="card-detail">{agg.get('tool_error_rate', 0):.1%} error rate</div>
            </div>
            <div class="card">
                <div class="card-title">Cache Hit Rate</div>
                <div class="card-value">{agg.get('cache_hit_rate', 0):.1%}</div>
                <div class="card-detail">{agg.get('total_cache_read_tokens', 0):,} cached tokens</div>
            </div>
        </div>

        <!-- Activity Calendar -->
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Activity Calendar</h2>
            </div>
            <div class="calendar-container">
                {calendar_html}
            </div>
        </div>

        <div class="two-col">
            <!-- Daily Trend -->
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">Daily Activity (Last 30 Days)</h2>
                </div>
                <div class="chart-container">
                    <div class="trend-chart">
"""

    # Generate trend bars
    for date, count in sorted_days:
        height = (count / max_daily * 100) if max_daily > 0 else 0
        short_date = date[5:]  # MM-DD
        html_content += f'                        <div class="trend-bar" style="height: {height}%" title="{date}: {count} sessions"></div>\n'

    html_content += """                    </div>
                </div>
            </div>

            <!-- Work Hours -->
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">Work Hours Distribution</h2>
                </div>
                <div class="chart-container">
                    <div class="bar-chart">
"""

    # Generate hour bars
    for hour in range(24):
        count = work_hours_data[hour]
        height_pct = (count / max_hour_count * 100) if max_hour_count > 0 else 0
        html_content += f'                        <div class="bar" style="height: {height_pct}%" title="{count} sessions at {hour:02d}:00"><span class="bar-label">{hour:02d}</span></div>\n'

    html_content += """                    </div>
                </div>
            </div>
        </div>
"""

    # Tool usage section
    if top_tools:
        html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Tool Usage</h2>
            </div>
            <div class="tools-grid">
"""
        for tool_name, count in top_tools:
            pct = (count / max_tool_count * 100) if max_tool_count > 0 else 0
            html_content += f"""
                <div class="tool-item">
                    <div class="tool-name">{html.escape(tool_name)}</div>
                    <div class="tool-count">{count:,}</div>
                    <div class="tool-bar"><div class="tool-bar-fill" style="width: {pct}%"></div></div>
                </div>
"""
        html_content += """
            </div>
        </div>
"""

    # Code languages section
    if top_languages:
        html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Code Languages</h2>
            </div>
            <div class="card">
                <div style="display: flex; flex-wrap: wrap; gap: 8px;">
"""
        for lang, count in top_languages:
            html_content += f'                    <span class="lang-badge">{html.escape(lang)}<span class="count">{count:,}</span></span>\n'

        html_content += """                </div>
            </div>
        </div>
"""

    # Models section
    if agg.get("models_used"):
        html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Models Used</h2>
            </div>
            <div class="card">
                <div class="badges-list">
"""
        for model, count in sorted(agg["models_used"].items(), key=lambda x: -x[1]):
            html_content += f'                    <span class="badge badge-primary">{html.escape(model)} ({count:,})</span>\n'

        html_content += """                </div>
            </div>
        </div>
"""

    # Duration and response time stats
    html_content += """
        <div class="two-col">
"""

    if agg.get("session_duration_stats"):
        dur = agg["session_duration_stats"]
        html_content += f"""
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">Session Duration</h2>
                </div>
                <div class="stats-grid" style="grid-template-columns: repeat(3, 1fr);">
                    <div class="card">
                        <div class="card-title">Average</div>
                        <div class="card-value">{dur['avg_minutes']:.1f} min</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Median</div>
                        <div class="card-value">{dur['median_minutes']:.1f} min</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Longest</div>
                        <div class="card-value">{dur['max_minutes']:.0f} min</div>
                    </div>
                </div>
            </div>
"""

    if agg.get("response_time_stats"):
        resp = agg["response_time_stats"]
        html_content += f"""
            <div class="section">
                <div class="section-header">
                    <h2 class="section-title">Response Time</h2>
                </div>
                <div class="stats-grid" style="grid-template-columns: repeat(3, 1fr);">
                    <div class="card">
                        <div class="card-title">Average</div>
                        <div class="card-value">{resp['avg_seconds']:.1f}s</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Median</div>
                        <div class="card-value">{resp['median_seconds']:.1f}s</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Fastest</div>
                        <div class="card-value">{resp['min_seconds']:.1f}s</div>
                    </div>
                </div>
            </div>
"""

    html_content += """
        </div>
"""

    # Additional insights
    html_content += f"""
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Quick Insights</h2>
            </div>
            <div class="stats-grid">
                <div class="card">
                    <div class="card-title">Code Blocks Generated</div>
                    <div class="card-value">{agg.get('total_code_blocks', 0):,}</div>
                </div>
                <div class="card">
                    <div class="card-title">Thinking Blocks</div>
                    <div class="card-value">{agg.get('total_thinking_blocks', 0):,}</div>
                </div>
                <div class="card">
                    <div class="card-title">Avg Tokens/Session</div>
                    <div class="card-value">{agg.get('avg_tokens_per_session', 0):,.0f}</div>
                </div>
                <div class="card">
                    <div class="card-title">Avg Messages/Session</div>
                    <div class="card-value">{agg.get('avg_messages_per_session', 0):.1f}</div>
                </div>
            </div>
        </div>
"""

    # Projects table
    html_content += """
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Projects</h2>
            </div>
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
        project_id = get_project_id(proj["project_name"])
        display_name = format_short_name(proj["project_name"], 50)
        full_path = format_project_display_name(proj["project_name"])

        html_content += f"""                    <tr id="{project_id}">
                        <td><a href="index.html#{project_id}" class="table-link" title="{html.escape(full_path)}">{html.escape(display_name)}</a></td>
                        <td>{proj['sessions']:,}</td>
                        <td>{proj['total_messages']:,}</td>
                        <td>{proj['total_tokens']:,}</td>
                        <td>{proj['code_blocks']:,}</td>
                    </tr>
"""

    html_content += f"""                </tbody>
            </table>
        </div>

        <div class="footer">
            <p>Generated by Claude Sessions</p>
        </div>
    </div>
    <script>{SHARED_JS}</script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
