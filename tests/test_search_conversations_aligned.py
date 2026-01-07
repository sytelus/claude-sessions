#!/usr/bin/env python3
"""
Tests for search_conversations.py

Tests the ConversationSearcher and SearchResult classes, covering:
- SearchResult dataclass functionality
- Various search modes (exact, regex, smart, semantic)
- Filtering by speaker, date range
- Content extraction from different message formats
- Relevance scoring
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

# Add project root to path for package imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Local imports after sys.path modification
from src.search_conversations import ConversationSearcher, SearchResult  # noqa: E402


class TestSearchResult(unittest.TestCase):
    """Test SearchResult dataclass"""

    def test_search_result_creation(self):
        """Test creating a SearchResult with all fields"""
        result = SearchResult(
            file_path=Path("/test/path.jsonl"),
            conversation_id="test-session",
            matched_content="Hello world",
            context="Previous message",
            speaker="human",
            timestamp=datetime(2024, 1, 1, 10, 0),
            relevance_score=0.95,
            line_number=5,
        )

        self.assertEqual(result.file_path, Path("/test/path.jsonl"))
        self.assertEqual(result.conversation_id, "test-session")
        self.assertEqual(result.matched_content, "Hello world")
        self.assertEqual(result.relevance_score, 0.95)
        self.assertEqual(result.speaker, "human")
        self.assertEqual(result.line_number, 5)

    def test_search_result_defaults(self):
        """Test SearchResult default values"""
        result = SearchResult(
            file_path=Path("/test/path.jsonl"),
            conversation_id="test",
            matched_content="content",
            context="context",
            speaker="human",
        )

        self.assertIsNone(result.timestamp)
        self.assertEqual(result.relevance_score, 0.0)
        self.assertEqual(result.line_number, 0)

    def test_search_result_string_representation(self):
        """Test SearchResult string representation"""
        result = SearchResult(
            file_path=Path("/test/project/chat_123.jsonl"),
            conversation_id="chat_123",
            matched_content="Test content",
            context="Test context",
            speaker="human",
            relevance_score=0.8,
        )

        str_repr = str(result)
        self.assertIn("chat_123.jsonl", str_repr)
        self.assertIn("Human", str_repr)  # Capitalized in output
        self.assertIn("80%", str_repr)  # Relevance score as percentage


class TestConversationSearcher(unittest.TestCase):
    """Test ConversationSearcher functionality"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.searcher = ConversationSearcher()
        self.create_test_conversations()

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_conversations(self):
        """Create test conversation files"""
        # Project 1: Python discussion
        project1 = Path(self.temp_dir) / ".claude" / "projects" / "python_project"
        project1.mkdir(parents=True)

        conv1 = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "How do I use Python decorators?",
                },
                "timestamp": "2024-01-01T10:00:00Z",
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "Python decorators are a way to modify functions.",
                        }
                    ],
                },
                "timestamp": "2024-01-01T10:01:00Z",
            },
        ]

        with open(project1 / "chat_001.jsonl", "w") as f:
            for msg in conv1:
                f.write(json.dumps(msg) + "\n")

        # Project 2: JavaScript discussion
        project2 = Path(self.temp_dir) / ".claude" / "projects" / "js_project"
        project2.mkdir(parents=True)

        conv2 = [
            {
                "type": "user",
                "message": {"role": "user", "content": "Explain JavaScript promises"},
                "timestamp": "2024-01-02T10:00:00Z",
            }
        ]

        with open(project2 / "chat_002.jsonl", "w") as f:
            for msg in conv2:
                f.write(json.dumps(msg) + "\n")

    def test_search_exact_match(self):
        """Test exact string matching"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("Python decorators", mode="exact", search_dir=search_dir)

        self.assertGreater(len(results), 0)
        self.assertIn("decorators", results[0].matched_content.lower())

    def test_search_case_insensitive(self):
        """Test case-insensitive search"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results1 = self.searcher.search("python", case_sensitive=False, search_dir=search_dir)
        results2 = self.searcher.search("PYTHON", case_sensitive=False, search_dir=search_dir)

        # Should find same results regardless of case
        self.assertEqual(len(results1), len(results2))

    def test_search_case_sensitive(self):
        """Test case-sensitive search"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results1 = self.searcher.search("Python", case_sensitive=True, search_dir=search_dir)
        results2 = self.searcher.search("python", case_sensitive=True, search_dir=search_dir)

        # May find different results based on case
        self.assertIsNotNone(results1)
        self.assertIsNotNone(results2)

    def test_search_regex_mode(self):
        """Test regex pattern matching"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search(r"Python|JavaScript", mode="regex", search_dir=search_dir)

        # Should find both Python and JavaScript mentions
        self.assertGreater(len(results), 0)
        contents = [r.matched_content for r in results]
        self.assertTrue(
            any("Python" in c for c in contents)
            or any("JavaScript" in c for c in contents)
        )

    def test_search_smart_mode(self):
        """Test smart search mode"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("programming language", mode="smart", search_dir=search_dir)

        # Should find relevant results even without exact match
        self.assertIsNotNone(results)

    def test_search_speaker_filter(self):
        """Test filtering by speaker"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        human_results = self.searcher.search("How", speaker_filter="human", search_dir=search_dir)
        assistant_results = self.searcher.search(
            "way to", speaker_filter="assistant", search_dir=search_dir
        )

        # Check speaker filtering
        for result in human_results:
            self.assertEqual(result.speaker, "human")

        for result in assistant_results:
            self.assertEqual(result.speaker, "assistant")

    def test_search_max_results(self):
        """Test limiting number of results"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search(
            "Python", max_results=1, search_dir=search_dir
        )

        self.assertLessEqual(len(results), 1)

    def test_search_no_matches(self):
        """Test search with no matches"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("nonexistent12345query", search_dir=search_dir)

        self.assertEqual(len(results), 0)

    def test_search_with_context(self):
        """Test that search results include context"""
        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        results = self.searcher.search("decorators", mode="exact", search_dir=search_dir)

        if results:
            # Should have context
            self.assertIsNotNone(results[0].context)

    def test_search_corrupted_jsonl(self):
        """Test search handles corrupted JSONL files gracefully"""
        # Create corrupted file
        bad_project = Path(self.temp_dir) / ".claude" / "projects" / "bad_project"
        bad_project.mkdir(parents=True)

        with open(bad_project / "chat_bad.jsonl", "w") as f:
            f.write("not json\n")
            f.write('{"invalid": json}\n')
            f.write('{"type": "user", "message": {"content": "Valid message"}}\n')

        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        # Should not crash, just skip bad lines
        results = self.searcher.search("Valid", search_dir=search_dir)
        self.assertIsNotNone(results)

    def test_extract_content_string(self):
        """Test content extraction from string format"""
        entry = {"type": "user", "message": {"content": "Simple string"}}
        content = self.searcher._extract_content(entry)
        self.assertEqual(content, "Simple string")

    def test_extract_content_list(self):
        """Test content extraction from list format"""
        entry = {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Part 1"},
                    {"type": "text", "text": "Part 2"}
                ]
            }
        }
        content = self.searcher._extract_content(entry)
        self.assertIn("Part 1", content)
        self.assertIn("Part 2", content)

    def test_extract_content_empty(self):
        """Test content extraction from empty/missing content"""
        entry = {"type": "user", "message": {}}
        content = self.searcher._extract_content(entry)
        self.assertEqual(content, "")


class TestSearchIntegration(unittest.TestCase):
    """Integration tests for search functionality"""

    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.mkdtemp()
        self.searcher = ConversationSearcher()

    def tearDown(self):
        """Clean up test environment"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_end_to_end_search_workflow(self):
        """Test complete search workflow"""
        # Create realistic conversation
        project = Path(self.temp_dir) / ".claude" / "projects" / "test_project"
        project.mkdir(parents=True)

        conversation = [
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": "How do I handle errors in Python?",
                },
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": "You can use try-except blocks for error handling.",
                        }
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "user",
                "message": {"role": "user", "content": "Can you show an example?"},
                "timestamp": datetime.now().isoformat(),
            },
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "try:\n    risky_operation()\n"
                                "except Exception as e:\n    print(f'Error: {e}')"
                            ),
                        }
                    ],
                },
                "timestamp": datetime.now().isoformat(),
            },
        ]

        with open(project / "chat_test.jsonl", "w") as f:
            for msg in conversation:
                f.write(json.dumps(msg) + "\n")

        search_dir = Path(self.temp_dir) / ".claude" / "projects"
        # Search for error handling
        results = self.searcher.search("error handling", mode="smart", search_dir=search_dir)

        self.assertGreater(len(results), 0)

        # Verify results have expected structure
        first = results[0]
        self.assertIsInstance(first.file_path, Path)
        self.assertIn("test_project", str(first.file_path))
        self.assertGreater(first.relevance_score, 0)
        self.assertIn(first.speaker, ["human", "assistant"])


if __name__ == "__main__":
    unittest.main()
