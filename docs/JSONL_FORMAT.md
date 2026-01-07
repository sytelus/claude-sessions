# Claude Code JSONL Format Reference

This document describes the JSONL file format used by Claude Code to log conversation sessions.

## Overview

Claude Code stores conversation logs as JSONL (JSON Lines) files, where each line is a self-contained JSON object representing a single event in the conversation.

**Location**: `~/.claude/projects/<project-hash>/<session-id>.jsonl`

**Encoding**: UTF-8

## Entry Types

Each JSON line has a `type` field that determines its structure:

| Type | Description |
|------|-------------|
| `user` | User message sent to Claude |
| `assistant` | Claude's response |
| `tool_use` | Tool invocation by Claude |
| `tool_result` | Result from tool execution |

---

## User Message (`type: "user"`)

Represents a message from the user to Claude.

### Structure

```json
{
  "type": "user",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "uuid": "unique-message-id",
  "sessionId": "session-identifier",
  "message": {
    "content": <content>
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"user"` |
| `timestamp` | string | ISO 8601 timestamp with 'Z' suffix (UTC) |
| `uuid` | string | Unique identifier for this message |
| `sessionId` | string | Session identifier |
| `message.content` | string \| array | Message content (see Content Formats) |

---

## Assistant Message (`type: "assistant"`)

Represents Claude's response to the user.

### Structure

```json
{
  "type": "assistant",
  "timestamp": "2024-01-15T10:30:05.000Z",
  "uuid": "unique-message-id",
  "message": {
    "model": "claude-3-opus-20240229",
    "content": [
      {"type": "thinking", "thinking": "Internal reasoning..."},
      {"type": "text", "text": "Response text..."},
      {"type": "tool_use", "id": "tool-1", "name": "Read", "input": {...}}
    ],
    "usage": {
      "input_tokens": 150,
      "output_tokens": 200,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 100
    },
    "stop_reason": "end_turn"
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"assistant"` |
| `timestamp` | string | ISO 8601 timestamp |
| `uuid` | string | Unique identifier |
| `message.model` | string | Model ID used for this response |
| `message.content` | array | Array of content blocks |
| `message.usage` | object | Token usage statistics |
| `message.stop_reason` | string | Why generation stopped |

### Content Block Types

#### Text Block
```json
{"type": "text", "text": "The actual response text..."}
```

#### Thinking Block
```json
{"type": "thinking", "thinking": "Claude's internal reasoning..."}
```

#### Tool Use Block
```json
{
  "type": "tool_use",
  "id": "unique-tool-call-id",
  "name": "ToolName",
  "input": {
    "parameter1": "value1",
    "parameter2": "value2"
  }
}
```

### Usage Object

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | int | Tokens in the input/prompt |
| `output_tokens` | int | Tokens in the response |
| `cache_creation_input_tokens` | int | Tokens used to create cache |
| `cache_read_input_tokens` | int | Tokens read from cache |

### Stop Reasons

| Value | Meaning |
|-------|---------|
| `end_turn` | Natural completion |
| `max_tokens` | Hit token limit |
| `tool_use` | Stopped to use a tool |
| `stop_sequence` | Hit a stop sequence |

---

## Tool Use (`type: "tool_use"`)

Represents a tool being invoked by Claude.

### Structure

```json
{
  "type": "tool_use",
  "timestamp": "2024-01-15T10:30:10.000Z",
  "uuid": "unique-id",
  "tool": {
    "name": "Read",
    "input": {
      "file_path": "/path/to/file.py"
    }
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"tool_use"` |
| `timestamp` | string | ISO 8601 timestamp |
| `uuid` | string | Unique identifier |
| `tool.name` | string | Name of the tool |
| `tool.input` | object | Tool parameters |

### Common Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `Read` | Read file contents | `file_path` |
| `Write` | Write/create file | `file_path`, `content` |
| `Edit` | Edit file | `file_path`, `old_string`, `new_string` |
| `Bash` | Run shell command | `command` |
| `Glob` | Find files | `pattern`, `path` |
| `Grep` | Search file contents | `pattern`, `path` |
| `WebFetch` | Fetch URL | `url`, `prompt` |
| `WebSearch` | Web search | `query` |
| `Task` | Launch sub-agent | `prompt`, `subagent_type` |

---

## Tool Result (`type: "tool_result"`)

Represents the result of a tool execution.

### Structure

```json
{
  "type": "tool_result",
  "timestamp": "2024-01-15T10:30:11.000Z",
  "uuid": "unique-id",
  "result": {
    "output": "File contents here...",
    "error": null
  }
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"tool_result"` |
| `timestamp` | string | ISO 8601 timestamp |
| `uuid` | string | Unique identifier |
| `result.output` | string | Tool output (may be large) |
| `result.error` | string \| null | Error message if failed |

---

## Content Formats

User and assistant messages can have content in different formats:

### String Format
```json
{"content": "Plain text message"}
```

### Array Format
```json
{
  "content": [
    {"type": "text", "text": "Message text"},
    {"type": "image", "source": {...}}
  ]
}
```

### Text Extraction

When extracting text from content:

1. If `content` is a string, use it directly
2. If `content` is an array:
   - Extract `text` from blocks where `type == "text"`
   - Concatenate with newlines

See `utils.extract_text()` for the reference implementation.

---

## Timestamps

All timestamps use ISO 8601 format with:
- UTC timezone (indicated by 'Z' suffix)
- Millisecond precision

**Format**: `YYYY-MM-DDTHH:mm:ss.sssZ`

**Example**: `2024-01-15T10:30:00.000Z`

### Parsing

```python
from datetime import datetime

timestamp = "2024-01-15T10:30:00.000Z"
dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
```

See `utils.parse_timestamp()` for the reference implementation.

---

## File Organization

### Project Hash

The project directory name is a hash derived from the working directory path:

```
~/.claude/projects/
├── -home-user-project-a/       # Hash of /home/user/project-a
│   ├── session1.jsonl
│   └── session2.jsonl
└── -home-user-project-b/       # Hash of /home/user/project-b
    └── session1.jsonl
```

### Session ID

The JSONL filename (without extension) is the session ID, which is a UUID.

---

## Example Complete Session

```jsonl
{"type":"user","timestamp":"2024-01-15T10:00:00.000Z","uuid":"u1","sessionId":"sess1","message":{"content":"Hello Claude"}}
{"type":"assistant","timestamp":"2024-01-15T10:00:02.000Z","uuid":"a1","message":{"model":"claude-3-opus","content":[{"type":"text","text":"Hello! How can I help?"}],"usage":{"input_tokens":10,"output_tokens":8},"stop_reason":"end_turn"}}
{"type":"user","timestamp":"2024-01-15T10:00:10.000Z","uuid":"u2","sessionId":"sess1","message":{"content":"Read my config file"}}
{"type":"assistant","timestamp":"2024-01-15T10:00:12.000Z","uuid":"a2","message":{"model":"claude-3-opus","content":[{"type":"text","text":"I'll read your config file."},{"type":"tool_use","id":"t1","name":"Read","input":{"file_path":"config.json"}}],"usage":{"input_tokens":50,"output_tokens":30},"stop_reason":"tool_use"}}
{"type":"tool_use","timestamp":"2024-01-15T10:00:13.000Z","uuid":"t1","tool":{"name":"Read","input":{"file_path":"config.json"}}}
{"type":"tool_result","timestamp":"2024-01-15T10:00:14.000Z","uuid":"tr1","result":{"output":"{\"key\": \"value\"}","error":null}}
{"type":"assistant","timestamp":"2024-01-15T10:00:16.000Z","uuid":"a3","message":{"model":"claude-3-opus","content":[{"type":"text","text":"Your config file contains: key=value"}],"usage":{"input_tokens":80,"output_tokens":15},"stop_reason":"end_turn"}}
```

---

## Parsing Guidelines

### Error Handling

1. **Invalid JSON**: Skip the line, continue processing
2. **Missing fields**: Use defaults or skip the entry
3. **Unknown type**: Skip the entry (future compatibility)

### Performance

1. **Streaming**: Process line-by-line to handle large files
2. **Early termination**: Stop when search results are found
3. **Lazy loading**: Don't parse content until needed

### Compatibility

1. **Forward compatible**: Ignore unknown fields
2. **Backward compatible**: Handle missing optional fields
3. **Type checking**: Verify `type` field before accessing type-specific fields
