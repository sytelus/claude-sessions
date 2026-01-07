#!/usr/bin/env python3
"""
Search functionality for Claude Sessions.

This module provides powerful search capabilities for Claude Code session logs.
It supports multiple search modes from simple string matching to NLP-based
semantic search, with filtering by date range and speaker.

Search Modes:
    - smart: Default mode combining token matching, proximity scoring, and exact match
    - exact: Simple case-sensitive/insensitive substring matching
    - regex: Regular expression pattern matching
    - semantic: NLP-based search using spaCy (requires optional dependency)

Relevance Scoring:
    Results are ranked by relevance using multiple factors:
    - Exact match bonus: Full query string found in content
    - Token overlap: Percentage of query words found in content
    - Proximity bonus: Query terms appearing close together
    - Match density: Multiple occurrences increase score

Optional Dependencies:
    - spaCy (pip install spacy): Enables semantic search mode
    - en_core_web_sm model (python -m spacy download en_core_web_sm)

Configuration:
    Search behavior is controlled by the SearchConfig dataclass. A default
    CONFIG instance is used, but custom configurations can be created.

For architecture overview, see:
    docs/ARCHITECTURE.md

For JSONL input format, see:
    docs/JSONL_FORMAT.md

Example:
    >>> from search_conversations import ConversationSearcher
    >>> searcher = ConversationSearcher()
    >>> results = searcher.search("authentication", mode="smart", max_results=10)
    >>> for result in results:
    ...     print(f"{result.speaker}: {result.relevance_score:.0%}")
    ...     print(result.context)

Classes:
    SearchConfig: Configuration constants for search operations
    SearchResult: Data container for a single search result
    ConversationSearcher: Main search engine class

Functions:
    create_search_index: Create a pre-computed search index for faster searches

Module Constants:
    CONFIG: Default SearchConfig instance
    SPACY_AVAILABLE: True if spaCy is installed
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from .utils import extract_text, parse_timestamp

# Optional NLP imports for semantic search
try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    spacy = None
    SPACY_AVAILABLE = False


class SearchMode(Enum):
    """
    Enumeration of available search modes.

    Attributes:
        SMART: Default mode combining token matching, proximity scoring, and exact match
        EXACT: Simple case-sensitive/insensitive substring matching
        REGEX: Regular expression pattern matching
        SEMANTIC: NLP-based search using spaCy (requires optional dependency)
    """
    SMART = "smart"
    EXACT = "exact"
    REGEX = "regex"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class SearchConfig:
    """
    Configuration constants for search operations.

    This frozen dataclass holds all tunable parameters for the search engine.
    A default CONFIG instance is provided, but custom configurations can be
    created for testing or specialized search behavior.

    Attribute Groups:
        Display Settings: Control result formatting and truncation
        Topic Extraction: Configure NLP-based topic extraction
        Relevance Scoring: Tune the relevance calculation algorithm

    Example:
        >>> custom_config = SearchConfig(max_results=50, relevance_threshold=0.2)

    See Also:
        _calculate_relevance() for how these values are used in scoring
    """

    # Display settings
    major_separator_width: int = 60
    default_max_results: int = 20
    max_content_length: int = 200
    default_context_size: int = 150
    indent_number: int = 2

    # Topic extraction settings
    default_max_topics: int = 5
    content_length_processing: int = 10
    max_noun_phrases_length: int = 3
    min_topic_phrase_count: int = 1

    # Relevance scoring thresholds
    relevance_threshold: float = 0.1
    min_relevance_compared: float = 1.0
    match_factor_for_relevance: float = 0.2
    match_bonus: float = 0.5
    min_relevance_multiple_occurrences: float = 0.3
    match_factor_multiple_occurrences: float = 0.1
    min_relevance_overlap: float = 0.4
    match_factor_overlap: float = 0.4
    proximity_bonus: float = 0.1
    min_tokens_for_proximity_bonus: int = 1
    proximity_window_multiplier: int = 2
    additional_boost_exact_match: float = 0.3
    match_context_step: int = 100
    semantic_similarity_threshold: float = 0.3
    context_fallback_multiplier: int = 2


# Default configuration instance
CONFIG = SearchConfig()


@dataclass
class SearchResult:
    """
    Represents a search result with context.

    Each search result contains the matched content, surrounding context for
    display, metadata about where the match was found, and a relevance score
    for ranking results.

    Attributes:
        file_path (Path): Path to the JSONL file containing the match
        conversation_id (str): Session ID (filename without extension)
        matched_content (str): The content that matched the query (truncated)
        context (str): Surrounding text for display (with query highlighted)
        speaker (str): Who said it - 'human' or 'assistant'
        timestamp (datetime): When the message was sent (if available)
        relevance_score (float): Score from 0.0 to 1.0 indicating match quality
        line_number (int): Line number in JSONL file where match was found

    Example:
        >>> result = results[0]
        >>> print(f"Found in {result.file_path.name} by {result.speaker}")
        >>> print(f"Relevance: {result.relevance_score:.0%}")
        >>> print(result.context)
    """

    file_path: Path
    conversation_id: str
    matched_content: str
    context: str  # Surrounding text for context
    speaker: str  # 'human' or 'assistant'
    timestamp: Optional[datetime] = None
    relevance_score: float = 0.0
    line_number: int = 0

    def __str__(self) -> str:
        """User-friendly string representation for terminal output."""
        sep = "=" * CONFIG.major_separator_width
        return (
            f"\n{sep}\n"
            f"File: {self.file_path.name}\n"
            f"Speaker: {self.speaker.title()}\n"
            f"Relevance: {self.relevance_score:.0%}\n"
            f"{sep}\n"
            f"{self.context}\n"
        )


class ConversationSearcher:
    """
    Main search engine for Claude conversations.

    This class provides comprehensive search capabilities across Claude Code
    session logs. It supports multiple search modes, date filtering, speaker
    filtering, and intelligent relevance ranking.

    Search Modes:
        - smart (default): Multi-factor relevance scoring with token matching,
          proximity analysis, and exact match bonuses
        - exact: Simple substring matching, good for specific phrases
        - regex: Regular expression pattern matching
        - semantic: NLP-based conceptual search using spaCy (optional)

    Features:
        - Searches all JSONL files recursively in target directory
        - Filters by date range (file modification time)
        - Filters by speaker (human/assistant)
        - Extracts context around matches for display
        - Highlights matched text in context
        - Ranks results by configurable relevance score

    Attributes:
        nlp: spaCy NLP model instance (None if spaCy unavailable)
        stop_words (set): Common words excluded from relevance scoring

    Example:
        >>> searcher = ConversationSearcher()
        >>> # Smart search with defaults
        >>> results = searcher.search("API authentication")
        >>> # Regex search with speaker filter
        >>> results = searcher.search(r"error\\s+\\d+", mode="regex", speaker_filter="assistant")
        >>> # Date-filtered search
        >>> from datetime import datetime
        >>> results = searcher.search("bug fix", date_from=datetime(2024, 1, 1))
    """

    def __init__(self) -> None:
        """Initialize the searcher with optional NLP support."""
        # Initialize NLP if available
        self.nlp = None
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_sm")
                # Disable unnecessary components for speed
                self.nlp.select_pipes(disable=["ner", "lemmatizer"])
            except Exception:
                print("Warning: spaCy model not found. Using basic search.")

        # Common words to ignore in relevance scoring
        self.stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "i",
            "you",
            "we",
            "they",
            "it",
            "this",
            "that",
            "these",
            "those",
        }

    def search(
        self,
        query: str,
        search_dir: Optional[Path] = None,
        mode: Union[SearchMode, str] = SearchMode.SMART,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        speaker_filter: Optional[str] = None,
        max_results: int = CONFIG.default_max_results,
        case_sensitive: bool = False,
    ) -> List[SearchResult]:
        """
        Search conversations with various filters.

        Args:
            query: Search query (text or regex pattern)
            search_dir: Directory to search in (default: ~/.claude/projects)
            mode: Search mode - SearchMode enum or string ("smart", "exact", "regex", "semantic")
            date_from: Filter results from this date
            date_to: Filter results until this date
            speaker_filter: Filter by speaker - "human", "assistant", or None for both
            max_results: Maximum number of results to return
            case_sensitive: Whether search should be case-sensitive

        Returns:
            List of SearchResult objects sorted by relevance
        """
        # Default search directory
        if search_dir is None:
            search_dir = Path.home() / ".claude" / "projects"

        # Validate search directory
        if not search_dir.exists():
            raise ValueError(f"Search directory does not exist: {search_dir}")

        # Return empty results for empty query
        if not query or not query.strip():
            return []

        # Find all JSONL files
        jsonl_files = list(search_dir.rglob("*.jsonl"))
        if not jsonl_files:
            return []

        # Apply date filtering to files if provided
        if date_from or date_to:
            jsonl_files = self._filter_files_by_date(jsonl_files, date_from, date_to)

        # Normalize mode to enum value string for comparison
        mode_value = mode.value if isinstance(mode, SearchMode) else mode

        # Search based on mode
        all_results = []

        for jsonl_file in jsonl_files:
            if mode_value == SearchMode.REGEX.value:
                results = self._search_regex(
                    jsonl_file, query, speaker_filter, case_sensitive
                )
            elif mode_value == SearchMode.EXACT.value:
                results = self._search_exact(
                    jsonl_file, query, speaker_filter, case_sensitive
                )
            elif mode_value == SearchMode.SEMANTIC.value and self.nlp:
                results = self._search_semantic(jsonl_file, query, speaker_filter)
            else:  # smart mode - combines multiple approaches
                results = self._search_smart(
                    jsonl_file, query, speaker_filter, case_sensitive
                )

            all_results.extend(results)

        # Sort by relevance score
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Return top results
        return all_results[:max_results]

    def _filter_files_by_date(
        self,
        files: List[Path],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
    ) -> List[Path]:
        """
        Filter files by modification date.

        Uses file system mtime to filter files. This is a fast pre-filter that
        avoids parsing files that are outside the date range.

        Args:
            files: List of file paths to filter
            date_from: Include files modified after this date (inclusive)
            date_to: Include files modified before this date (inclusive)

        Returns:
            Filtered list of file paths within date range
        """
        filtered = []

        for file in files:
            file_mtime = datetime.fromtimestamp(file.stat().st_mtime)

            if date_from and file_mtime < date_from:
                continue
            if date_to and file_mtime > date_to:
                continue

            filtered.append(file)

        return filtered

    def _search_smart(
        self,
        jsonl_file: Path,
        query: str,
        speaker_filter: Optional[str],
        case_sensitive: bool,
    ) -> List[SearchResult]:
        """
        Smart search that combines multiple techniques.

        Uses exact matching, fuzzy matching, and semantic similarity.
        """
        results = []
        conversation_id = jsonl_file.stem

        # Process query
        if not case_sensitive:
            query_lower = query.lower()
            query_tokens = set(query_lower.split()) - self.stop_words
        else:
            query_tokens = set(query.split()) - self.stop_words

        # Read and parse JSONL
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    try:
                        entry = json.loads(line.strip())

                        # Extract message based on entry type
                        if entry.get("type") in ["user", "assistant"]:
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )

                            # Apply speaker filter
                            if speaker_filter and speaker != speaker_filter:
                                continue

                            # Extract content
                            content = self._extract_content(entry)
                            if not content:
                                continue

                            # Calculate relevance
                            relevance = self._calculate_relevance(
                                content, query, query_tokens, case_sensitive
                            )

                            if relevance > CONFIG.relevance_threshold:
                                # Extract context
                                context = self._extract_context(
                                    content, query, case_sensitive
                                )

                                # Parse timestamp if present
                                timestamp = parse_timestamp(entry.get("timestamp"))

                                result = SearchResult(
                                    file_path=jsonl_file,
                                    conversation_id=conversation_id,
                                    matched_content=content[:CONFIG.max_content_length],
                                    context=context,
                                    speaker=speaker,
                                    timestamp=timestamp,
                                    relevance_score=relevance,
                                    line_number=line_num,
                                )
                                results.append(result)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error searching {jsonl_file}: {e}")

        return results

    def _search_exact(
        self,
        jsonl_file: Path,
        query: str,
        speaker_filter: Optional[str],
        case_sensitive: bool,
    ) -> List[SearchResult]:
        """
        Exact string matching search.

        Performs simple substring matching. Relevance is calculated based on
        the number of times the query appears in the content.

        Args:
            jsonl_file: Path to session JSONL file
            query: Exact string to search for
            speaker_filter: Optional filter for 'human' or 'assistant'
            case_sensitive: Whether to match case exactly

        Returns:
            List of SearchResult for messages containing the exact query
        """
        results = []
        conversation_id = jsonl_file.stem

        search_query = query if case_sensitive else query.lower()

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    try:
                        entry = json.loads(line.strip())

                        if entry.get("type") in ["user", "assistant"]:
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )

                            if speaker_filter and speaker != speaker_filter:
                                continue

                            content = self._extract_content(entry)
                            if not content:
                                continue

                            search_content = (
                                content if case_sensitive else content.lower()
                            )

                            if search_query in search_content:
                                # Calculate relevance based on match frequency
                                match_count = search_content.count(search_query)
                                relevance = min(
                                    CONFIG.min_relevance_compared,
                                    match_count * CONFIG.match_factor_for_relevance
                                )

                                context = self._extract_context(
                                    content, query, case_sensitive
                                )

                                # Parse timestamp if present
                                timestamp = parse_timestamp(entry.get("timestamp"))

                                result = SearchResult(
                                    file_path=jsonl_file,
                                    conversation_id=conversation_id,
                                    matched_content=content[:CONFIG.max_content_length],
                                    context=context,
                                    speaker=speaker,
                                    timestamp=timestamp,
                                    relevance_score=relevance,
                                    line_number=line_num,
                                )
                                results.append(result)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error searching {jsonl_file}: {e}")

        return results

    def _search_regex(
        self,
        jsonl_file: Path,
        pattern: str,
        speaker_filter: Optional[str],
        case_sensitive: bool,
    ) -> List[SearchResult]:
        """
        Regex pattern matching search.

        Compiles the pattern as a regular expression and searches for matches.
        Context is extracted around the first match in each message.

        Args:
            jsonl_file: Path to session JSONL file
            pattern: Regular expression pattern (Python re syntax)
            speaker_filter: Optional filter for 'human' or 'assistant'
            case_sensitive: Whether regex should be case-sensitive

        Returns:
            List of SearchResult for messages matching the regex

        Note:
            Invalid regex patterns result in an error message and empty results.
        """
        results = []
        conversation_id = jsonl_file.stem

        # Compile regex pattern
        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
        except re.error as e:
            print(f"Invalid regex pattern: {e}")
            return []

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    try:
                        entry = json.loads(line.strip())

                        if entry.get("type") in ["user", "assistant"]:
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )

                            if speaker_filter and speaker != speaker_filter:
                                continue

                            content = self._extract_content(entry)
                            if not content:
                                continue

                            matches = list(regex.finditer(content))

                            if matches:
                                # Calculate relevance based on match quality
                                relevance = min(
                                    CONFIG.min_relevance_compared,
                                    len(matches) * CONFIG.match_factor_for_relevance
                                )

                                # Get context around first match
                                first_match = matches[0]
                                start = max(0, first_match.start() - CONFIG.match_context_step)
                                end = min(len(content), first_match.end() + CONFIG.match_context_step)
                                context = "..." + content[start:end] + "..."

                                # Parse timestamp if present
                                timestamp = parse_timestamp(entry.get("timestamp"))

                                result = SearchResult(
                                    file_path=jsonl_file,
                                    conversation_id=conversation_id,
                                    matched_content=first_match.group(),
                                    context=context,
                                    speaker=speaker,
                                    timestamp=timestamp,
                                    relevance_score=relevance,
                                    line_number=line_num,
                                )
                                results.append(result)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error searching {jsonl_file}: {e}")

        return results

    def _search_semantic(
        self, jsonl_file: Path, query: str, speaker_filter: Optional[str]
    ) -> List[SearchResult]:
        """
        Semantic search using spaCy NLP.

        Finds conceptually similar content even without exact matches.
        """
        if not self.nlp:
            return []

        results = []
        conversation_id = jsonl_file.stem

        # Process query with spaCy
        query_doc = self.nlp(query.lower())
        query_tokens = [
            token for token in query_doc if not token.is_stop and token.is_alpha
        ]

        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                line_num = 0
                for line in f:
                    line_num += 1
                    try:
                        entry = json.loads(line.strip())

                        if entry.get("type") in ["user", "assistant"]:
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )

                            if speaker_filter and speaker != speaker_filter:
                                continue

                            content = self._extract_content(entry)
                            if not content:
                                continue

                            # Process content with spaCy
                            content_doc = self.nlp(content.lower())

                            # Calculate semantic similarity
                            similarity = self._calculate_semantic_similarity(
                                query_doc, query_tokens, content_doc
                            )

                            if similarity > CONFIG.semantic_similarity_threshold:
                                context = self._extract_context(content, query, False)

                                # Parse timestamp if present
                                timestamp = parse_timestamp(entry.get("timestamp"))

                                result = SearchResult(
                                    file_path=jsonl_file,
                                    conversation_id=conversation_id,
                                    matched_content=content[:CONFIG.max_content_length],
                                    context=context,
                                    speaker=speaker,
                                    timestamp=timestamp,
                                    relevance_score=similarity,
                                    line_number=line_num,
                                )
                                results.append(result)

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error searching {jsonl_file}: {e}")

        return results

    def _extract_content(self, entry: Dict[str, Any]) -> str:
        """
        Extract text content from a JSONL entry.

        Handles two formats:
        1. Test format: {"type": "user", "content": "text"}
        2. Claude log format: {"type": "user", "message": {"content": "text"}}

        Uses the shared extract_text utility for handling content arrays.

        Args:
            entry: Parsed JSONL entry dictionary

        Returns:
            Extracted text content, or empty string if no content found
        """
        # Handle test format (type: user/assistant, content: string)
        if entry.get("type") in ["user", "assistant"] and "content" in entry:
            content = entry["content"]
            if isinstance(content, str):
                return content
            # Use shared extract_text for list content
            return extract_text(content)

        # Handle actual Claude log format (type: user/assistant, message: {...})
        if "message" in entry:
            msg = entry["message"]
            if isinstance(msg, dict):
                content = msg.get("content", "")
                # Use shared extract_text utility
                return extract_text(content)

        return ""

    def _calculate_relevance(
        self, content: str, query: str, query_tokens: Set[str], case_sensitive: bool
    ) -> float:
        """
        Calculate relevance score for content against query.

        Uses multiple factors:
        - Exact match bonus
        - Token overlap
        - Proximity of terms
        - Match density
        """
        relevance = 0.0

        # Prepare content
        if not case_sensitive:
            content_lower = content.lower()
            query_lower = query.lower()
        else:
            content_lower = content
            query_lower = query

        # Exact match bonus
        if query_lower in content_lower:
            relevance += CONFIG.match_bonus
            # Additional bonus for multiple occurrences
            count = content_lower.count(query_lower)
            relevance += min(
                CONFIG.min_relevance_multiple_occurrences,
                count * CONFIG.match_factor_multiple_occurrences
            )

        # Token overlap
        content_tokens = set(content_lower.split()) - self.stop_words
        if query_tokens and content_tokens:
            overlap = len(query_tokens & content_tokens)
            relevance += min(
                CONFIG.min_relevance_overlap,
                overlap / len(query_tokens) * CONFIG.match_factor_overlap
            )

        # Proximity bonus - are query terms near each other?
        if len(query_tokens) > CONFIG.min_tokens_for_proximity_bonus:
            # Check if all query tokens appear within a window
            words = content_lower.split()
            for i in range(len(words) - len(query_tokens)):
                window = set(words[i : i + len(query_tokens) * CONFIG.proximity_window_multiplier])
                if query_tokens.issubset(window):
                    relevance += CONFIG.proximity_bonus
                    break

        return min(CONFIG.min_relevance_compared, relevance)

    def _calculate_semantic_similarity(
        self, query_doc: Any, query_tokens: List[Any], content_doc: Any
    ) -> float:
        """Calculate semantic similarity using spaCy."""
        if not query_tokens:
            return 0.0

        # Find semantically similar tokens
        similar_count = 0
        for query_token in query_tokens:
            for content_token in content_doc:
                if content_token.is_alpha and not content_token.is_stop:
                    # Check if tokens are similar (same lemma or high similarity)
                    if (
                        query_token.lemma_ == content_token.lemma_
                        or query_token.text == content_token.text
                    ):
                        similar_count += 1
                        break

        # Calculate similarity score
        if query_tokens:
            base_similarity = similar_count / len(query_tokens)
        else:
            base_similarity = 0.0

        # Boost for exact phrase matches
        if query_doc.text.lower() in content_doc.text.lower():
            base_similarity = min(
                CONFIG.min_relevance_compared,
                base_similarity + CONFIG.additional_boost_exact_match
            )

        return base_similarity

    def _extract_context(
        self, content: str, query: str, case_sensitive: bool,
        context_size: int = CONFIG.default_context_size
    ) -> str:
        """Extract context around the match for display."""
        if not case_sensitive:
            # Find match position
            pos = content.lower().find(query.lower())
        else:
            pos = content.find(query)

        fallback_size = context_size * CONFIG.context_fallback_multiplier
        if pos == -1:
            # No exact match, return beginning of content
            return content[:fallback_size] + ("..." if len(content) > fallback_size else "")

        # Extract context around match
        start = max(0, pos - context_size)
        end = min(len(content), pos + len(query) + context_size)

        context = content[start:end]

        # Add ellipsis if truncated
        if start > 0:
            context = "..." + context
        if end < len(content):
            context = context + "..."

        # Highlight the match
        if not case_sensitive:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(query), re.IGNORECASE)
            context = pattern.sub(f"**{query.upper()}**", context)
        else:
            context = context.replace(query, f"**{query}**")

        return context

    def search_by_date_range(
        self, date_from: datetime, date_to: datetime, search_dir: Optional[Path] = None
    ) -> List[Path]:
        """Find all conversation files within a date range."""
        if search_dir is None:
            search_dir = Path.home() / ".claude" / "projects"

        jsonl_files = list(search_dir.rglob("*.jsonl"))
        return self._filter_files_by_date(jsonl_files, date_from, date_to)

    def get_conversation_topics(
        self, jsonl_file: Path, max_topics: int = CONFIG.default_max_topics
    ) -> List[str]:
        """
        Extract main topics from a conversation.

        Uses NLP to identify key themes and subjects.
        """
        if not self.nlp:
            return []

        # Collect all content
        all_content = []
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        content = self._extract_content(entry)
                        if content:
                            all_content.append(content)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            return []

        if not all_content:
            return []

        # Process with spaCy
        full_text = " ".join(all_content[:CONFIG.content_length_processing])
        doc = self.nlp(full_text)

        # Extract noun phrases as topics
        noun_phrases = []
        for chunk in doc.noun_chunks:
            if len(chunk.text.split()) <= CONFIG.max_noun_phrases_length:
                noun_phrases.append(chunk.text.lower())

        # Count frequency
        phrase_counts: Dict[str, int] = {}
        for phrase in noun_phrases:
            phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1

        # Sort by frequency
        sorted_phrases = sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)

        # Return top topics
        return [
            phrase for phrase, count in sorted_phrases[:max_topics]
            if count > CONFIG.min_topic_phrase_count
        ]


def create_search_index(search_dir: Path, output_file: Path) -> None:
    """
    Create a search index for faster subsequent searches.

    Pre-processes all conversations in the search directory and saves metadata
    to a JSON file. The index includes conversation counts, timestamps, and
    speaker information for quick filtering without parsing JSONL files.

    Index Structure:
        {
            "created": "2024-01-15T10:00:00",
            "conversations": {
                "session-id": {
                    "path": "/path/to/session.jsonl",
                    "modified": "2024-01-15T10:00:00",
                    "size": 12345,
                    "message_count": 42,
                    "speakers": ["human", "assistant"],
                    "first_message": "2024-01-15T10:00:00.000Z",
                    "last_message": "2024-01-15T11:00:00.000Z"
                }
            }
        }

    Args:
        search_dir: Directory containing JSONL session files (searched recursively)
        output_file: Path for output JSON index file

    Note:
        This function is currently standalone and not integrated with
        ConversationSearcher. Future enhancement could use this index
        for faster searches.
    """
    index = {"created": datetime.now().isoformat(), "conversations": {}}

    jsonl_files = list(search_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        conv_id = jsonl_file.stem

        # Extract metadata
        metadata = {
            "path": str(jsonl_file),
            "modified": datetime.fromtimestamp(jsonl_file.stat().st_mtime).isoformat(),
            "size": jsonl_file.stat().st_size,
            "message_count": 0,
            "speakers": set(),
            "first_message": None,
            "last_message": None,
        }

        # Parse file
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("type") in ["user", "assistant"]:
                            metadata["message_count"] += 1
                            speaker = (
                                "human" if entry["type"] == "user" else "assistant"
                            )
                            metadata["speakers"].add(speaker)

                            if metadata["first_message"] is None:
                                metadata["first_message"] = entry.get("timestamp")
                            metadata["last_message"] = entry.get("timestamp")

                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue

        # Convert set to list for JSON serialization
        metadata["speakers"] = list(metadata["speakers"])

        index["conversations"][conv_id] = metadata

    # Save index
    with open(output_file, "w") as f:
        json.dump(index, f, indent=CONFIG.indent_number)

    print(f"Created search index with {len(index['conversations'])} conversations")
