#!/usr/bin/env python3
"""
Backup functionality for Claude Sessions.

Provides incremental backup with timestamp preservation.
"""

import os
import shutil
from pathlib import Path
from typing import Dict


class BackupManager:
    """Manages incremental backup of Claude session files."""

    def __init__(self, input_dir: Path, output_dir: Path):
        """
        Initialize backup manager.

        Args:
            input_dir: Source directory (e.g., ~/.claude/projects/)
            output_dir: Destination directory for backups
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

    def backup(self) -> Dict:
        """
        Perform incremental backup.

        - Creates new project folders that don't exist
        - Copies files that don't exist in output
        - Overwrites files with different timestamps
        - Skips files with identical timestamps
        - Preserves original timestamps

        Returns:
            Dict with backup statistics
        """
        stats = {
            "projects_found": 0,
            "projects_created": 0,
            "files_copied": 0,
            "files_skipped": 0,
            "files_updated": 0,
            "errors": [],
        }

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Iterate through input projects
        for project_dir in self.input_dir.iterdir():
            if not project_dir.is_dir():
                continue

            # Check if project has JSONL files
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if not jsonl_files:
                continue

            stats["projects_found"] += 1

            # Create output project directory
            output_project = self.output_dir / project_dir.name
            if not output_project.exists():
                output_project.mkdir(parents=True)
                stats["projects_created"] += 1
                print(f"  + Created project: {project_dir.name}")

            # Process each JSONL file
            for input_file in jsonl_files:
                result = self._sync_file(input_file, output_project)
                if result == "copied":
                    stats["files_copied"] += 1
                    print(f"    + Copied: {input_file.name}")
                elif result == "updated":
                    stats["files_updated"] += 1
                    print(f"    ~ Updated: {input_file.name}")
                elif result == "skipped":
                    stats["files_skipped"] += 1
                elif result.startswith("error"):
                    stats["errors"].append(result)
                    print(f"    ! Error: {input_file.name}: {result}")

        return stats

    def _sync_file(self, input_file: Path, output_project: Path) -> str:
        """
        Sync a single file from input to output.

        Args:
            input_file: Source file path
            output_project: Destination project directory

        Returns:
            Status string: "copied", "updated", "skipped", or "error: ..."
        """
        output_file = output_project / input_file.name

        try:
            input_stat = input_file.stat()
            input_mtime = input_stat.st_mtime

            if output_file.exists():
                output_stat = output_file.stat()
                output_mtime = output_stat.st_mtime

                # Skip if timestamps match
                if abs(input_mtime - output_mtime) < 1:  # 1 second tolerance
                    return "skipped"

                # Update if timestamps differ
                shutil.copy2(input_file, output_file)
                self._preserve_timestamp(input_file, output_file)
                return "updated"
            else:
                # Copy new file
                shutil.copy2(input_file, output_file)
                self._preserve_timestamp(input_file, output_file)
                return "copied"

        except Exception as e:
            return f"error: {e}"

    def _preserve_timestamp(self, source: Path, dest: Path):
        """Preserve original file timestamps."""
        try:
            source_stat = source.stat()
            os.utime(dest, (source_stat.st_atime, source_stat.st_mtime))
        except Exception:
            pass  # Best effort timestamp preservation

    def get_sync_status(self) -> Dict:
        """
        Get current sync status without making changes.

        Returns:
            Dict with status information
        """
        status = {
            "input_projects": {},
            "output_projects": {},
            "pending_files": 0,
            "synced_files": 0,
        }

        # Count input files
        for project_dir in self.input_dir.iterdir():
            if project_dir.is_dir():
                jsonl_files = list(project_dir.glob("*.jsonl"))
                if jsonl_files:
                    status["input_projects"][project_dir.name] = len(jsonl_files)

        # Count output files
        if self.output_dir.exists():
            for project_dir in self.output_dir.iterdir():
                if project_dir.is_dir():
                    jsonl_files = list(project_dir.glob("*.jsonl"))
                    if jsonl_files:
                        status["output_projects"][project_dir.name] = len(jsonl_files)

        # Calculate pending
        for project, count in status["input_projects"].items():
            output_count = status["output_projects"].get(project, 0)
            if count > output_count:
                status["pending_files"] += count - output_count
            status["synced_files"] += min(count, output_count)

        return status
