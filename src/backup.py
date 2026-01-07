#!/usr/bin/env python3
"""
Backup functionality for Claude Sessions.

This module provides incremental backup of Claude Code session files from the
user's ~/.claude/projects/ directory to a specified output location. It uses
timestamp-based comparison to avoid unnecessary copies.

Key Features:
    - Incremental backup: Only copies new or modified files
    - Timestamp preservation: Output files retain original modification times
    - Project structure: Maintains the same directory hierarchy as source
    - Error resilience: Continues on individual file errors, reports at end

Incremental Strategy:
    Files are compared by modification timestamp with 1-second tolerance.
    This accounts for filesystem precision differences across platforms.
    - Same timestamp (within tolerance): Skip
    - Different timestamp: Overwrite with source file
    - File doesn't exist: Copy

For architecture overview, see:
    docs/ARCHITECTURE.md

Example:
    >>> from backup import BackupManager
    >>> manager = BackupManager(Path("~/.claude/projects"), Path("./backups"))
    >>> stats = manager.backup()
    >>> print(f"Copied {stats['files_copied']} new files")

Classes:
    BackupManager: Handles incremental file synchronization
"""

import os
import shutil
from pathlib import Path
from typing import Any, Dict, Literal


class BackupManager:
    """
    Manages incremental backup of Claude session files.

    This class handles the synchronization of JSONL session files from Claude
    Code's projects directory to a backup location. It maintains the project
    directory structure and only copies files that are new or have been modified.

    The backup process:
        1. Scans input_dir for project subdirectories containing *.jsonl files
        2. Creates corresponding directories in output_dir if they don't exist
        3. For each JSONL file, compares timestamps with any existing backup
        4. Copies only if file is new or has different modification time
        5. Preserves original timestamps on copied files

    Directory Structure:
        input_dir/                     output_dir/
        ├── project-hash-a/           ├── project-hash-a/
        │   ├── session1.jsonl   -->  │   ├── session1.jsonl
        │   └── session2.jsonl   -->  │   └── session2.jsonl
        └── project-hash-b/           └── project-hash-b/
            └── session1.jsonl   -->      └── session1.jsonl

    Attributes:
        input_dir (Path): Source directory containing Claude Code projects
        output_dir (Path): Destination directory for backups

    Example:
        >>> manager = BackupManager(
        ...     Path.home() / ".claude" / "projects",
        ...     Path("./backups")
        ... )
        >>> stats = manager.backup()
        >>> print(f"Found {stats['projects_found']} projects")
        >>> print(f"Copied {stats['files_copied']} files")
    """

    def __init__(self, input_dir: Path, output_dir: Path):
        """
        Initialize backup manager.

        Args:
            input_dir: Source directory (e.g., ~/.claude/projects/)
            output_dir: Destination directory for backups
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

    def backup(self) -> Dict[str, Any]:
        """
        Perform incremental backup.

        Scans all project directories in input_dir and synchronizes JSONL files
        to output_dir. Progress is printed to stdout as files are processed.

        Operations performed:
            - Creates new project folders that don't exist
            - Copies files that don't exist in output
            - Overwrites files with different timestamps (>1 second difference)
            - Skips files with identical timestamps (within 1 second)
            - Preserves original timestamps on all copied files

        Returns:
            dict: Backup statistics with the following keys:
                - projects_found (int): Number of input projects with JSONL files
                - projects_created (int): Number of new output directories created
                - files_copied (int): Number of new files copied
                - files_updated (int): Number of existing files overwritten
                - files_skipped (int): Number of unchanged files skipped
                - errors (list): List of error messages for failed operations
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

    def _sync_file(
        self, input_file: Path, output_project: Path
    ) -> Literal["copied", "updated", "skipped"] | str:
        """
        Sync a single file from input to output.

        Args:
            input_file: Source file path
            output_project: Destination project directory

        Returns:
            Status: "copied", "updated", "skipped", or "error: <message>"
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

    def _preserve_timestamp(self, source: Path, dest: Path) -> None:
        """
        Preserve original file timestamps on copied file.

        Sets the access time (atime) and modification time (mtime) of the
        destination file to match the source file. This is critical for the
        incremental backup to work correctly on subsequent runs.

        Args:
            source: Original file to read timestamps from
            dest: Copied file to update timestamps on

        Raises:
            OSError: If timestamp cannot be set on destination file
        """
        source_stat = source.stat()
        os.utime(dest, (source_stat.st_atime, source_stat.st_mtime))

    def get_sync_status(self) -> Dict[str, Any]:
        """
        Get current sync status without making changes.

        Compares input and output directories to determine how many files
        exist in each and how many may need syncing. This is a read-only
        operation that does not modify any files.

        Note:
            The pending_files count is an approximation based on file counts
            per project, not actual timestamp comparison. A file may be counted
            as "synced" even if it needs updating due to timestamp changes.

        Returns:
            dict: Status information with the following keys:
                - input_projects (dict): Map of project name -> file count in input
                - output_projects (dict): Map of project name -> file count in output
                - pending_files (int): Estimated files needing sync (new files only)
                - synced_files (int): Files that exist in both locations
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
