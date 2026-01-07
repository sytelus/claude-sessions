"""Claude Sessions - Backup and analyze Claude Code conversation sessions."""

__version__ = "2.0.0"
__author__ = "Dustin Kirby"

from .backup import BackupManager
from .formatters import FormatConverter
from .stats import StatisticsGenerator
from .prompts import PromptsExtractor
from .parser import SessionParser, ParsedMessage
from .utils import extract_text, parse_timestamp

# Legacy exports for backwards compatibility
from .extract_claude_logs import ClaudeConversationExtractor
from .search_conversations import ConversationSearcher

__all__ = [
    "BackupManager",
    "FormatConverter",
    "StatisticsGenerator",
    "PromptsExtractor",
    "SessionParser",
    "ParsedMessage",
    "extract_text",
    "parse_timestamp",
    "ClaudeConversationExtractor",
    "ConversationSearcher",
]