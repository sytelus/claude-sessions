#!/usr/bin/env python3
"""
HTML generation for Claude Sessions.

This module provides shared HTML templates, CSS styles, and generators for
the index page and statistics dashboard. It creates a unified, modern UI
for browsing Claude Code session backups.

Features:
    - Shared CSS design system with consistent theming
    - Dark/light mode support with persistence
    - Index page with project/session navigation, search, and pagination
    - Statistics dashboard with rich visualizations
    - Activity calendar heatmap (GitHub-style)
    - Cost estimation based on Claude API pricing
    - Tool usage breakdown and code metrics
    - Responsive design for mobile and desktop

Classes:
    HtmlGenerator: Generates index.html with project/session navigation

Functions:
    generate_stats_html: Generates statistics dashboard (stats.html)
    generate_calendar_html: Creates GitHub-style activity calendar
    estimate_cost: Calculates API cost estimates from token usage
    get_project_hash: Creates deterministic HTML IDs for projects
    extract_cwd_from_session: Extracts working directory from session file
    format_project_display_name: Converts project directory to display name
    format_short_name: Shortened project name (last path component)
    format_duration: Formats minutes to human-readable string
    format_days_ago: Formats days ago to human-readable string
    format_tokens_compact: Formats token counts in K/M notation

Constants:
    SHARED_CSS: CSS styles shared across all generated pages
    SHARED_JS: JavaScript for theme toggle, search, and interactivity
    COST_PER_1M_*: Token pricing constants for cost estimation
"""

import hashlib
import html
import json
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from parser import SessionParser
from utils import iter_project_dirs, extract_text

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

/* Project list (scalable) */
.project-list {
    background: var(--card);
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    overflow: hidden;
}
.project-row {
    border-bottom: 1px solid var(--border);
    transition: all 0.2s;
}
.project-row:last-child { border-bottom: none; }
.project-row.hidden { display: none; }
.project-row-header {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    cursor: pointer;
    gap: 12px;
    transition: background 0.2s;
}
.project-row-header:hover { background: var(--bg-alt); }
.project-row-expand {
    width: 24px;
    height: 24px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--muted);
    transition: transform 0.2s;
}
.project-row.expanded .project-row-expand { transform: rotate(90deg); }
.project-row-info { flex: 1; min-width: 0; }
.project-row-name {
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.project-row-path {
    font-size: 0.7rem;
    color: var(--muted);
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.project-row-stats {
    display: flex;
    gap: 16px;
    font-size: 0.75rem;
    color: var(--text-secondary);
    flex-shrink: 0;
}
.project-row-stat { display: flex; align-items: center; gap: 4px; }
.project-row-stat strong { color: var(--text); font-weight: 600; }
/* Responsive stat visibility classes */
.stat-desktop { display: none; }
.stat-wide { display: none; }
@media (min-width: 768px) {
    .stat-desktop { display: flex; }
}
@media (min-width: 1200px) {
    .stat-wide { display: flex; }
}
.project-sessions {
    display: none;
    background: var(--bg);
    padding: 12px 16px 12px 52px;
    border-top: 1px solid var(--border);
}
.project-row.expanded .project-sessions { display: block; }
.session-groups {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.session-group {
    background: var(--card);
    border-radius: var(--radius-sm);
    overflow: hidden;
}
.session-group-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    cursor: pointer;
    background: var(--bg-alt);
    font-size: 0.8rem;
    color: var(--muted);
}
.session-group-header:hover { background: var(--border); }
.session-group-count {
    background: var(--primary-light);
    color: var(--primary);
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 0.7rem;
    font-weight: 600;
}
.session-group-items { display: none; }
.session-group.expanded .session-group-items { display: block; }
.sessions-list {
    padding: 8px;
    max-height: 400px;
    overflow-y: auto;
}
/* Pagination */
.pagination {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 16px;
    border-top: 1px solid var(--border);
}
.pagination-btn {
    padding: 6px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--card);
    color: var(--text);
    cursor: pointer;
    font-size: 0.8rem;
    transition: all 0.2s;
}
.pagination-btn:hover:not(:disabled) { background: var(--primary-light); border-color: var(--primary); }
.pagination-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pagination-info { font-size: 0.8rem; color: var(--muted); }
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
        // Search in project rows (new layout)
        const rows = document.querySelectorAll('.project-row');
        rows.forEach(row => {
            const name = row.querySelector('.project-row-name')?.textContent.toLowerCase() || '';
            const path = row.querySelector('.project-row-path')?.textContent.toLowerCase() || '';
            if (name.includes(query) || path.includes(query)) {
                row.classList.remove('hidden');
            } else {
                row.classList.add('hidden');
            }
        });
        // Update pagination after filter
        if (typeof updatePagination === 'function') updatePagination();
    });
}

// Toggle project row expansion
function toggleProjectRow(projectId) {
    const row = document.getElementById('project-' + projectId);
    if (row) {
        row.classList.toggle('expanded');
    }
}

// Toggle session group expansion
function toggleSessionGroup(groupId) {
    const group = document.getElementById(groupId);
    if (group) {
        group.classList.toggle('expanded');
    }
}

// Pagination state
let currentPage = 1;
const itemsPerPage = 25;

function updatePagination() {
    const rows = document.querySelectorAll('.project-row:not(.hidden)');
    const totalPages = Math.ceil(rows.length / itemsPerPage);
    if (currentPage > totalPages) currentPage = Math.max(1, totalPages);

    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;

    rows.forEach((row, idx) => {
        row.style.display = (idx >= start && idx < end) ? '' : 'none';
    });

    const info = document.querySelector('.pagination-info');
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');

    if (info) {
        const visibleCount = rows.length;
        info.textContent = `Showing ${Math.min(start + 1, visibleCount)}-${Math.min(end, visibleCount)} of ${visibleCount} projects`;
    }
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
}

function prevPage() {
    if (currentPage > 1) {
        currentPage--;
        updatePagination();
    }
}

function nextPage() {
    const rows = document.querySelectorAll('.project-row:not(.hidden)');
    const totalPages = Math.ceil(rows.length / itemsPerPage);
    if (currentPage < totalPages) {
        currentPage++;
        updatePagination();
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initSearch();
    if (document.querySelector('.project-list')) {
        updatePagination();
    }
});
"""


def get_project_hash(project_name: str) -> str:
    """
    Generate a deterministic hash for a project name.

    Used to create unique HTML IDs for projects. Returns just the hash;
    callers should add appropriate prefixes (e.g., "project-", "group-").

    Args:
        project_name: The project directory name

    Returns:
        8-character hex hash of the project name
    """
    return hashlib.md5(project_name.encode()).hexdigest()[:8]


def extract_cwd_from_session(jsonl_file: Path) -> Optional[str]:
    """
    Extract the cwd (working directory) from a session file.

    Reads through the JSONL file line by line until finding an entry
    with a "cwd" field. Returns None if file cannot be read or no cwd found.

    Args:
        jsonl_file: Path to the JSONL session file

    Returns:
        The working directory path, or None if not found
    """
    try:
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if "cwd" in entry:
                            return entry["cwd"]
                    except json.JSONDecodeError:
                        # Malformed JSON line, try next line
                        continue
    except (OSError, IOError):
        # File cannot be read (missing, permission denied, etc.)
        pass
    return None


def format_project_display_name(project_name: str, cwd: Optional[str] = None) -> str:
    """
    Convert project directory name to readable display name.

    Uses the cwd (working directory) if provided, otherwise falls back
    to decoding the hyphen-encoded directory name. Claude Code stores
    projects with paths like "-home-user-project" which decode to
    "/home/user/project".

    Args:
        project_name: The project directory name (hyphen-encoded path)
        cwd: Optional working directory extracted from session file

    Returns:
        Human-readable path string
    """
    if cwd:
        return cwd

    # Fallback: decode hyphen-encoded path (less reliable)
    if project_name.startswith("-"):
        name = project_name.replace("-", "/")[1:]
    else:
        name = project_name
    return name


def format_short_name(project_name: str, max_len: int = 40, cwd: Optional[str] = None) -> str:
    """
    Get a shortened display name for a project.

    Extracts just the final directory name from the full path, useful for
    displaying in space-constrained UI elements like table cells.

    Args:
        project_name: The project directory name (hyphen-encoded path)
        max_len: Maximum length before truncation (default 40)
        cwd: Optional working directory extracted from session file

    Returns:
        Last path component, truncated with "..." if over max_len
    """
    full_path = format_project_display_name(project_name, cwd)
    # Return just the last component of the path (the actual directory name)
    if "/" in full_path:
        name = full_path.rstrip("/").rsplit("/", 1)[-1]
    else:
        name = full_path
    return name if len(name) <= max_len else name[:max_len-3] + "..."


def format_duration(mins: Optional[float]) -> str:
    """
    Format a duration in minutes to a human-readable string.

    Args:
        mins: Duration in minutes, or None

    Returns:
        Formatted string like "<1m", "45m", "2.5h", "1.2d", or "" if None
    """
    if mins is None:
        return ""
    if mins < 1:
        return "<1m"
    if mins < 60:
        return f"{int(mins)}m"
    if mins < 1440:  # 24 hours
        return f"{mins / 60:.1f}h"
    return f"{mins / 1440:.1f}d"


def format_days_ago(days: Optional[int]) -> str:
    """
    Format a number of days ago to a human-readable string.

    Args:
        days: Number of days ago, or None

    Returns:
        Formatted string like "today", "yesterday", "3d ago", "2w ago", "1mo ago"
    """
    if days is None:
        return ""
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days}d ago"
    if days < 30:
        return f"{days // 7}w ago"
    return f"{days // 30}mo ago"


def format_tokens_compact(tokens: int) -> str:
    """
    Format token count in compact notation.

    Args:
        tokens: Number of tokens

    Returns:
        Formatted string like "500", "9.5K", "1.2M"
    """
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}K"
    return f"{tokens:,}"


def generate_calendar_html(daily_usage: Dict[str, int]) -> str:
    """
    Generate GitHub-style activity calendar HTML for the last 4 weeks.

    Args:
        daily_usage: Dictionary of date strings to session counts

    Returns:
        HTML string for the calendar
    """
    if not daily_usage:
        return '<p class="muted">No activity data available</p>'

    # Get date range (last 4 weeks = 28 days)
    today = datetime.now().date()
    start_date = today - timedelta(days=27)  # 4 weeks = 28 days

    # Find max for color scaling (within our 4 week range)
    max_count = 1
    for i in range(28):
        date_str = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        count = daily_usage.get(date_str, 0)
        if count > max_count:
            max_count = count

    # Day labels
    day_labels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

    # Generate weeks (4 weeks total)
    weeks_html = []
    current_date = start_date

    # Align to start of week (Sunday)
    while current_date.weekday() != 6:  # 6 = Sunday
        current_date -= timedelta(days=1)

    week_num = 1
    while current_date <= today and week_num <= 5:  # Allow up to 5 partial weeks
        week_html = ['<div class="calendar-week">']
        for _ in range(7):
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

            # Hide days outside our range but keep structure
            if current_date < start_date or current_date > today:
                week_html.append('<div class="calendar-day" style="visibility:hidden"></div>')
            else:
                week_html.append(
                    f'<div class="calendar-day" data-level="{level}" '
                    f'title="{date_str}: {count} sessions"></div>'
                )
            current_date += timedelta(days=1)
        week_html.append('</div>')
        weeks_html.append(''.join(week_html))
        week_num += 1

    # Generate week labels (dates for each week)
    week_labels = []
    label_date = start_date
    while label_date.weekday() != 6:
        label_date -= timedelta(days=1)
    for i in range(len(weeks_html)):
        week_start = label_date + timedelta(days=i * 7)
        week_labels.append(week_start.strftime("%b %d"))

    calendar = f'''
        <div class="calendar-wrapper" style="display: flex; gap: 8px;">
            <div class="calendar-day-labels" style="display: flex; flex-direction: column; gap: 3px; padding-top: 24px;">
                {''.join(f'<div style="height: 12px; font-size: 10px; color: var(--muted); line-height: 12px;">{day}</div>' for day in day_labels)}
            </div>
            <div>
                <div class="calendar-week-labels" style="display: flex; gap: 3px; margin-bottom: 4px;">
                    {''.join(f'<div style="width: 12px; font-size: 9px; color: var(--muted); text-align: center; white-space: nowrap;">{label if i % 2 == 0 else ""}</div>' for i, label in enumerate(week_labels))}
                </div>
                <div class="calendar-grid">
                    {''.join(weeks_html)}
                </div>
            </div>
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
            project_cwd = proj.get("cwd")
            for session in proj["sessions"]:
                all_sessions.append({
                    **session,
                    "project": proj["name"],
                    "project_display": format_short_name(proj["name"], 30, cwd=project_cwd)
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
            <div class="project-list">
"""

        # Generate project rows (scalable list)
        for proj in sorted(projects_data, key=lambda x: -x["session_count"]):
            project_hash = get_project_hash(proj["name"])
            project_cwd = proj.get("cwd")
            display_name = format_short_name(proj["name"], cwd=project_cwd)
            full_path = format_project_display_name(proj["name"], cwd=project_cwd)

            # Categorize sessions
            regular_sessions = []
            warmup_sessions = []  # Sessions with just "Warmup" as content
            no_html_sessions = []

            for session in proj["sessions"]:
                preview_lower = (session.get("preview", "") or "").strip().lower()
                is_warmup = preview_lower in ("warmup", "warm up", "warm-up") or (
                    session.get("total_messages", 0) <= 2 and "warmup" in preview_lower
                )
                has_html = session.get("html_exists", False)

                if is_warmup:
                    warmup_sessions.append(session)
                elif not has_html:
                    no_html_sessions.append(session)
                else:
                    regular_sessions.append(session)

            # Calculate project totals from session stats
            total_tokens = sum(s.get("total_tokens", 0) for s in proj["sessions"])
            total_messages = sum(s.get("total_messages", 0) for s in proj["sessions"])

            # Calculate total duration (sum of session durations)
            total_duration_mins = sum(s.get("duration_mins", 0) or 0 for s in proj["sessions"])
            duration_str = format_duration(total_duration_mins) if total_duration_mins > 0 else ""

            # Find last active (min days_ago)
            days_ago_list = [s.get("days_ago") for s in proj["sessions"] if s.get("days_ago") is not None]
            last_active_str = format_days_ago(min(days_ago_list)) if days_ago_list else ""

            # Format tokens for display (compact format for large numbers)
            tokens_display = format_tokens_compact(total_tokens)

            html_content += f"""
                <div class="project-row" id="project-{project_hash}">
                    <div class="project-row-header" onclick="toggleProjectRow('{project_hash}')">
                        <div class="project-row-expand">▶</div>
                        <div class="project-row-info">
                            <div class="project-row-name" title="{html.escape(full_path)}">{html.escape(display_name)}</div>
                            <div class="project-row-path">{html.escape(full_path)}</div>
                        </div>
                        <div class="project-row-stats">
                            <div class="project-row-stat"><strong>{proj['session_count']}</strong> sessions</div>
                            <div class="project-row-stat"><strong>{total_messages:,}</strong> msgs</div>
                            <div class="project-row-stat stat-desktop"><strong>{tokens_display}</strong> tokens</div>
                            {f'<div class="project-row-stat stat-desktop"><strong>{duration_str}</strong> time</div>' if duration_str else ''}
                            {f'<div class="project-row-stat stat-wide"><strong>{last_active_str}</strong></div>' if last_active_str else ''}
                        </div>
                    </div>
                    <div class="project-sessions">
                        <div class="session-groups">
"""

            # Regular sessions
            if regular_sessions:
                html_content += f"""
                            <div class="session-group expanded" id="group-regular-{project_hash}">
                                <div class="session-group-header" onclick="toggleSessionGroup('group-regular-{project_hash}')">
                                    <span>📝 Active Sessions</span>
                                    <span class="session-group-count">{len(regular_sessions)}</span>
                                </div>
                                <div class="session-group-items">
                                    <div class="sessions-list">
"""
                for session in regular_sessions[:30]:
                    session_id = session["id"]
                    session_date = session.get("date", "")
                    preview = html.escape(session.get("preview", "")[:40]) if session.get("preview") else ""
                    html_path = f"{proj['name']}/html/{session_id}.html"
                    msgs = session.get("total_messages", 0)
                    tokens = session.get("total_tokens", 0)
                    duration = format_duration(session.get("duration_mins"))
                    days_ago = format_days_ago(session.get("days_ago"))

                    stats_html = f'<span style="color:var(--muted);font-size:0.65rem;margin-left:8px;">{msgs} msgs • {tokens:,} tok'
                    if duration:
                        stats_html += f' • {duration}'
                    if days_ago:
                        stats_html += f' • {days_ago}'
                    stats_html += '</span>'

                    html_content += f"""
                                        <div class="session-item">
                                            <div class="session-info">
                                                <span class="session-id" title="{html.escape(session_id)}">{html.escape(session_id[:16])}...{stats_html}</span>
                                                <span class="session-preview" title="{preview}">{preview}</span>
                                            </div>
                                            <div class="session-links">
                                                <a href="{html.escape(html_path)}" class="session-link">View</a>
                                            </div>
                                        </div>
"""
                if len(regular_sessions) > 30:
                    html_content += f"""
                                        <div class="session-item" style="justify-content:center;color:var(--muted);font-size:0.8rem;">
                                            +{len(regular_sessions) - 30} more sessions
                                        </div>
"""
                html_content += """
                                    </div>
                                </div>
                            </div>
"""

            # Warmup/empty sessions (collapsed by default)
            if warmup_sessions:
                html_content += f"""
                            <div class="session-group" id="group-warmup-{project_hash}">
                                <div class="session-group-header" onclick="toggleSessionGroup('group-warmup-{project_hash}')" title="Sessions that only contain a 'Warmup' message with no substantial content">
                                    <span>🔸 Empty/Warmup Sessions</span>
                                    <span class="session-group-count">{len(warmup_sessions)}</span>
                                </div>
                                <div class="session-group-items">
                                    <div class="sessions-list" style="max-height:200px;">
                                        <div style="padding:8px;font-size:0.75rem;color:var(--muted);background:var(--bg-alt);margin-bottom:8px;border-radius:4px;">
                                            ℹ️ These are sessions with only "Warmup" messages. They are typically test or initialization sessions.
                                        </div>
"""
                for session in warmup_sessions[:10]:
                    session_id = session["id"]
                    session_date = session.get("date", "")
                    html_path = f"{proj['name']}/html/{session_id}.html"
                    has_html = session.get("html_exists", False)

                    html_content += f"""
                                        <div class="session-item">
                                            <div class="session-info">
                                                <span class="session-id">{html.escape(session_id[:16])}...</span>
                                                <span class="session-date">{html.escape(session_date)}</span>
                                            </div>
                                            <div class="session-links">
                                                {f'<a href="{html.escape(html_path)}" class="session-link">View</a>' if has_html else ''}
                                            </div>
                                        </div>
"""
                if len(warmup_sessions) > 10:
                    html_content += f"""
                                        <div class="session-item" style="justify-content:center;color:var(--muted);font-size:0.8rem;">
                                            +{len(warmup_sessions) - 10} more
                                        </div>
"""
                html_content += """
                                    </div>
                                </div>
                            </div>
"""

            # No HTML sessions (collapsed by default)
            if no_html_sessions:
                html_content += f"""
                            <div class="session-group" id="group-nohtml-{project_hash}">
                                <div class="session-group-header" onclick="toggleSessionGroup('group-nohtml-{project_hash}')" title="Sessions without HTML view - usually due to parsing errors or incomplete data">
                                    <span>⚠️ Sessions Without HTML</span>
                                    <span class="session-group-count">{len(no_html_sessions)}</span>
                                </div>
                                <div class="session-group-items">
                                    <div class="sessions-list" style="max-height:200px;">
                                        <div style="padding:8px;font-size:0.75rem;color:var(--muted);background:var(--bg-alt);margin-bottom:8px;border-radius:4px;">
                                            ℹ️ These sessions don't have HTML views. This can happen when:<br>
                                            • The session data couldn't be parsed<br>
                                            • The session is very new and not yet processed<br>
                                            • There was an error during HTML generation
                                        </div>
"""
                for session in no_html_sessions[:10]:
                    session_id = session["id"]
                    session_date = session.get("date", "")
                    preview = html.escape(session.get("preview", "")[:30]) if session.get("preview") else ""

                    html_content += f"""
                                        <div class="session-item">
                                            <div class="session-info">
                                                <span class="session-id">{html.escape(session_id[:16])}...</span>
                                                <span class="session-date">{html.escape(session_date)}</span>
                                                {f'<span class="session-preview">{preview}</span>' if preview else ''}
                                            </div>
                                        </div>
"""
                if len(no_html_sessions) > 10:
                    html_content += f"""
                                        <div class="session-item" style="justify-content:center;color:var(--muted);font-size:0.8rem;">
                                            +{len(no_html_sessions) - 10} more
                                        </div>
"""
                html_content += """
                                    </div>
                                </div>
                            </div>
"""

            html_content += """
                        </div>
                    </div>
                </div>
"""

        if not projects_data:
            html_content += """
                <div style="padding: 40px; text-align: center; color: var(--muted);">
                    <h3>No sessions found</h3>
                    <p>Run a backup to populate this page.</p>
                </div>
"""

        html_content += f"""
            </div>
            <div class="pagination">
                <button class="pagination-btn" id="prev-page" onclick="prevPage()">← Previous</button>
                <span class="pagination-info">Loading...</span>
                <button class="pagination-btn" id="next-page" onclick="nextPage()">Next →</button>
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
            project_cwd = None  # Will be extracted from first session

            # Get session info from JSONL files
            jsonl_files = sorted(
                project_dir.glob("*.jsonl"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )

            for jsonl_file in jsonl_files:
                session_id = jsonl_file.stem

                # Get date and preview from first message
                date_str = ""
                preview = ""
                session_stats = {}
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

                        # Calculate session stats
                        user_msgs = sum(1 for m in messages if m.type == "user")
                        asst_msgs = sum(1 for m in messages if m.type == "assistant")
                        total_tokens = 0
                        for msg in messages:
                            if msg.usage:
                                total_tokens += msg.usage.get("input_tokens", 0)
                                total_tokens += msg.usage.get("output_tokens", 0)

                        # Calculate session duration
                        timestamps = [m.timestamp_dt for m in messages if m.timestamp_dt]
                        duration_mins = None
                        if len(timestamps) >= 2:
                            duration = (max(timestamps) - min(timestamps)).total_seconds() / 60
                            duration_mins = round(duration, 1)

                        # Calculate days ago
                        days_ago = None
                        if timestamps:
                            latest = max(timestamps)
                            days_ago = (datetime.now(latest.tzinfo) - latest).days

                        session_stats = {
                            "user_messages": user_msgs,
                            "assistant_messages": asst_msgs,
                            "total_messages": len(messages),
                            "total_tokens": total_tokens,
                            "duration_mins": duration_mins,
                            "days_ago": days_ago,
                        }
                except (OSError, IOError, json.JSONDecodeError, AttributeError, KeyError):
                    # Session parsing failed - continue with empty stats.
                    # Session will still appear in list but without detailed info.
                    pass

                # Extract cwd from first session file for this project
                if project_cwd is None:
                    project_cwd = extract_cwd_from_session(jsonl_file)

                # Check if HTML exists
                html_exists = (html_dir / f"{session_id}.html").exists()

                sessions.append({
                    "id": session_id,
                    "date": date_str,
                    "preview": preview,
                    "html_exists": html_exists,
                    **session_stats,
                })

            if sessions:
                projects.append({
                    "name": project_dir.name,
                    "cwd": project_cwd,
                    "session_count": len(sessions),
                    "sessions": sessions,
                })

        return projects


def _generate_rates_section(agg: Dict[str, Any]) -> str:
    """
    Generate the Daily Rates section HTML for the statistics page.

    Creates a grid of cards showing per-day averages for sessions, messages,
    tokens, tool calls, code lines, cost, and time. Only rendered if rate
    data is available in the aggregate statistics.

    Args:
        agg: Aggregate statistics dictionary containing "rates" and "span_days"

    Returns:
        HTML string for the rates section, or empty string if no rate data
    """
    rates = agg.get("rates", {})
    span_days = agg.get("span_days", 0)

    if not rates or span_days == 0:
        return ""

    # Calculate total time for display
    total_time_mins = agg.get("total_time_mins", 0)
    time_per_day = rates.get("time_per_day_mins", 0)
    avg_session_dur = agg.get("session_duration_stats", {}).get("avg_minutes", 0)

    # Format total time nicely
    if total_time_mins >= 60:
        total_time_str = f"{total_time_mins / 60:.1f} hrs"
    else:
        total_time_str = f"{total_time_mins:.0f} min"

    # Format time per day
    if time_per_day >= 60:
        time_per_day_str = f"{time_per_day / 60:.1f} hrs"
    else:
        time_per_day_str = f"{time_per_day:.0f} min"

    return f"""
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Daily Rates</h2>
                <span class="section-subtitle" style="color: var(--text-secondary); margin-left: 12px;">Based on {span_days} day span ({agg.get('first_date', 'N/A')} to {agg.get('last_date', 'N/A')})</span>
            </div>
            <div class="stats-grid">
                <div class="card" title="Average number of Claude sessions started per day">
                    <div class="card-title">Sessions/Day</div>
                    <div class="card-value">{rates.get('sessions_per_day', 0):.1f}</div>
                    <div class="card-detail">{agg.get('total_sessions', 0):,} total</div>
                </div>
                <div class="card" title="Average messages (user + assistant) exchanged per day">
                    <div class="card-title">Messages/Day</div>
                    <div class="card-value">{rates.get('messages_per_day', 0):.0f}</div>
                    <div class="card-detail">{agg.get('total_messages', 0):,} total</div>
                </div>
                <div class="card" title="Average tokens (input + output) consumed per day">
                    <div class="card-title">Tokens/Day</div>
                    <div class="card-value">{rates.get('tokens_per_day', 0):,.0f}</div>
                    <div class="card-detail">{agg.get('total_tokens', 0):,} total</div>
                </div>
                <div class="card" title="Average tool invocations (Read, Write, Bash, etc) per day">
                    <div class="card-title">Tool Calls/Day</div>
                    <div class="card-value">{rates.get('tool_calls_per_day', 0):.1f}</div>
                    <div class="card-detail">{agg.get('total_tool_uses', 0):,} total</div>
                </div>
                <div class="card" title="Code lines per day = code block lines + Write tool lines + Edit tool lines">
                    <div class="card-title">Code Lines/Day</div>
                    <div class="card-value">{rates.get('code_lines_per_day', 0):,.0f}</div>
                    <div class="card-detail">{agg.get('total_code_lines', 0) + agg.get('total_lines_written', 0) + agg.get('total_lines_edited', 0):,} total</div>
                </div>
                <div class="card insight-card" title="Estimated daily cost based on Claude API pricing">
                    <div class="card-title">Cost/Day</div>
                    <div class="card-value money">${rates.get('cost_per_day', 0):.2f}</div>
                    <div class="card-detail">${agg.get('estimated_cost', 0):.2f} total</div>
                </div>
                <div class="card" title="Estimated time spent per day based on average session duration of {avg_session_dur:.1f} min">
                    <div class="card-title">Time/Day</div>
                    <div class="card-value">{time_per_day_str}</div>
                    <div class="card-detail">{total_time_str} total (estimated)</div>
                </div>
            </div>
        </div>
"""


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
    # Work hours use string keys for JSON serialization consistency
    work_hours_data = [agg["work_hours"].get(str(h), 0) for h in range(24)]
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
            <p class="subtitle">Generated: {html.escape(stats['generated_at'])}{f" &bull; {agg.get('first_date', 'N/A')} to {agg.get('last_date', 'N/A')} ({agg.get('span_days', 0)} days)" if agg.get('span_days') else ''}</p>
        </div>

        <!-- Cost & Overview -->
        <div class="stats-grid">
            <div class="card insight-card" title="Estimated based on Claude API pricing: $3/M input tokens, $15/M output tokens, $0.30/M cached tokens">
                <div class="card-title">Estimated Cost</div>
                <div class="card-value money">${costs['total']:.2f}</div>
                <div class="card-detail">${costs['cache_savings']:.2f} saved via caching</div>
            </div>
            <div class="card" title="Total conversation sessions across all projects">
                <div class="card-title">Total Sessions</div>
                <div class="card-value">{agg['total_sessions']:,}</div>
                <div class="card-detail">{len(projects)} projects</div>
            </div>
            <div class="card" title="User messages (your prompts) + assistant messages (Claude responses)">
                <div class="card-title">Total Messages</div>
                <div class="card-value">{agg['total_messages']:,}</div>
                <div class="card-detail">{agg['total_user_messages']:,} user / {agg['total_assistant_messages']:,} assistant</div>
            </div>
            <div class="card" title="Input tokens (prompts + context) / Output tokens (Claude responses)">
                <div class="card-title">Total Tokens</div>
                <div class="card-value">{agg['total_tokens']:,}</div>
                <div class="card-detail">{agg['total_input_tokens']:,} in / {agg['total_output_tokens']:,} out</div>
            </div>
            <div class="card" title="Tool invocations (Read, Write, Edit, Bash, etc). Error rate shows percentage of failed calls.">
                <div class="card-title">Tool Calls</div>
                <div class="card-value">{agg.get('total_tool_uses', 0):,}</div>
                <div class="card-detail">{agg.get('tool_error_rate', 0):.1%} error rate</div>
            </div>
            <div class="card" title="Percentage of input tokens that were cached and reused (saves cost)">
                <div class="card-title">Cache Hit Rate</div>
                <div class="card-value">{agg.get('cache_hit_rate', 0):.1%}</div>
                <div class="card-detail">{agg.get('total_cache_read_tokens', 0):,} cached tokens</div>
            </div>
        </div>

        <!-- Daily Rates Section -->
        {_generate_rates_section(agg)}

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

    # Additional insights - calculate code line totals
    code_blocks_lines = agg.get('total_code_lines', 0)
    write_lines = agg.get('total_lines_written', 0)
    edit_lines = agg.get('total_lines_edited', 0)
    total_code_lines = code_blocks_lines + write_lines + edit_lines

    # Format estimated time
    total_time_mins = agg.get('total_time_mins', 0)
    avg_dur = agg.get('session_duration_stats', {}).get('avg_minutes', 0)
    if total_time_mins >= 60:
        total_time_str = f"{total_time_mins / 60:.1f} hrs"
    else:
        total_time_str = f"{total_time_mins:.0f} min"

    html_content += f"""
        <div class="section">
            <div class="section-header">
                <h2 class="section-title">Code & Activity Metrics</h2>
            </div>
            <div class="stats-grid">
                <div class="card insight-card" title="Total lines of code: {code_blocks_lines:,} in code blocks + {write_lines:,} via Write tool + {edit_lines:,} via Edit tool">
                    <div class="card-title">Total Code Lines</div>
                    <div class="card-value">{total_code_lines:,}</div>
                    <div class="card-detail">Hover for breakdown</div>
                </div>
                <div class="card" title="Lines of code within markdown code blocks (```...```) in assistant responses">
                    <div class="card-title">Code Block Lines</div>
                    <div class="card-value">{code_blocks_lines:,}</div>
                    <div class="card-detail">{agg.get('total_code_blocks', 0):,} blocks</div>
                </div>
                <div class="card" title="Lines written using the Write tool to create or replace files">
                    <div class="card-title">Write Tool Lines</div>
                    <div class="card-value">{write_lines:,}</div>
                </div>
                <div class="card" title="Lines affected by the Edit tool for modifying existing files">
                    <div class="card-title">Edit Tool Lines</div>
                    <div class="card-value">{edit_lines:,}</div>
                </div>
                <div class="card" title="Estimated total time based on session durations. Average session: {avg_dur:.1f} min">
                    <div class="card-title">Est. Total Time</div>
                    <div class="card-value">{total_time_str}</div>
                    <div class="card-detail">Avg: {avg_dur:.1f} min/session</div>
                </div>
                <div class="card" title="Internal reasoning blocks used by Claude for complex problems">
                    <div class="card-title">Thinking Blocks</div>
                    <div class="card-value">{agg.get('total_thinking_blocks', 0):,}</div>
                </div>
                <div class="card" title="Average tokens (input + output) per session">
                    <div class="card-title">Avg Tokens/Session</div>
                    <div class="card-value">{agg.get('avg_tokens_per_session', 0):,.0f}</div>
                </div>
                <div class="card" title="Average number of conversation turns per session">
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
        project_hash = get_project_hash(proj["project_name"])
        display_name = format_short_name(proj["project_name"], 50)
        full_path = format_project_display_name(proj["project_name"])

        html_content += f"""                    <tr id="project-{project_hash}">
                        <td><a href="index.html#project-{project_hash}" class="table-link" title="{html.escape(full_path)}">{html.escape(display_name)}</a></td>
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
