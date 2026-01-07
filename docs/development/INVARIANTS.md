# Claude Sessions - Invariants for Validation

This document lists quantities that should remain invariant throughout the backup and conversion process. These can be used to validate complex changes, detect bugs, and ensure data integrity.

---

## File-Level Invariants

### INV-F1: File Count Preservation
```
count(output/<project>/*.jsonl) >= count(input/<project>/*.jsonl)
```
- Output always has at least as many JSONL files as input
- Output may have more (deleted input files are preserved in output)

### INV-F2: File Timestamp Preservation
```
For each file F in output/<project>/:
    if F exists in input/<project>/:
        mtime(output/F) == mtime(input/F)
```
- File modification times in output match corresponding input files

### INV-F3: File Content Integrity
```
For each .jsonl file F:
    hash(output/<project>/F) == hash(input/<project>/F)
```
- Backed up JSONL files are byte-for-byte identical to source

### INV-F4: Format File Correspondence
```
For each .jsonl file F in output/<project>/:
    exists(output/<project>/markdown/F.md) XOR 'markdown' not in formats
    exists(output/<project>/html/F.html) XOR 'html' not in formats
    exists(output/<project>/data/F.json) XOR 'data' not in formats
```
- Each backed up JSONL has corresponding format files (based on --format)

---

## Message-Level Invariants

### INV-M1: Message Count Preservation
```
For each session S:
    count(messages in input/S.jsonl) == count(messages in output/S.jsonl)
    count(messages in input/S.jsonl) == count(messages in data/S.json)
```
- Number of messages is preserved across all representations

### INV-M2: Message Order Preservation
```
For each session S:
    order(messages in output) == order(messages in input)
```
- Message ordering is identical to source

### INV-M3: Turn Count Consistency
```
For each session S:
    turns_in_markdown(S) == turns_in_html(S) == turns_in_data(S)
```
- Turn count is consistent across all format representations

### INV-M4: User Message Extraction Completeness
```
For each session S in project P:
    count(user_prompts in prompts.yaml for S) <= count(user_messages in S.jsonl)
```
- User messages are captured in prompts.yaml (some are filtered: short responses like "y", "ok"; continuation messages; empty messages)

---

## Statistics Invariants

### INV-S1: Aggregate Sum Consistency
```
sum(sessions per project in stats.json) == total_sessions in stats.json
sum(messages per project) == total_messages
sum(tokens per project) == total_tokens
```
- Aggregate statistics equal sum of per-project statistics

### INV-S2: Statistics Bounds
```
For any metric M:
    min(M) <= avg(M) <= max(M)
    std_dev(M) >= 0
```
- Statistical measures satisfy mathematical constraints

### INV-S3: Count Non-Negativity
```
For all count metrics:
    value >= 0
```
- All counts are non-negative integers

### INV-S4: HTML/JSON Consistency
```
parse(stats.html).values == parse(stats.json).values
```
- Statistics in HTML and JSON representations are identical

---

## Timestamp Invariants

### INV-T1: Chronological Ordering
```
For each session S:
    timestamp(message[i]) <= timestamp(message[i+1])
```
- Messages within a session are chronologically ordered

### INV-T2: Session Timestamp Range
```
For each session S:
    session_start_time == min(message timestamps)
    session_end_time == max(message timestamps)
```
- Session time range matches message timestamp range

### INV-T3: Duration Calculation
```
session_duration == session_end_time - session_start_time
```
- Duration is difference between last and first message timestamps

---

## Idempotency Invariants

### INV-I1: Backup Idempotency
```
backup(backup(state)) == backup(state)
```
- Running backup twice with no input changes produces identical output

### INV-I2: No Spurious Modifications
```
If no input files changed:
    backup produces no file writes (except stats regeneration)
```
- Unchanged inputs don't trigger unnecessary file operations

### INV-I3: List Mode Read-Only
```
--list mode produces no file system changes
```
- List mode is purely read-only operation

---

## Format Conversion Invariants

### INV-C1: Markdown Fidelity
```
For each message M:
    text_content(M in markdown) contains text_content(M in jsonl)
```
- Markdown preserves all text content from source

### INV-C2: HTML Fidelity
```
For each message M:
    text_content(M in html) contains text_content(M in jsonl)
```
- HTML preserves all text content from source

### INV-C3: Structured Data Completeness
```
For each field F in input jsonl:
    F exists in output data/json OR F is explicitly excluded
```
- Structured data preserves maximum information

### INV-C4: Code Block Preservation
```
count(code_blocks in markdown) == count(code_blocks in source)
count(code_blocks in html) == count(code_blocks in source)
```
- All code blocks are preserved in converted formats

---

## Validation Test Cases

### Test: File Integrity Check
```python
def test_file_integrity():
    for project in output_projects:
        for jsonl in project.jsonl_files:
            input_file = input_path / project / jsonl.name
            if input_file.exists():
                assert hash(jsonl) == hash(input_file)
```

### Test: Message Count Check
```python
def test_message_counts():
    for session in all_sessions:
        input_count = count_messages(input_jsonl)
        output_count = count_messages(output_jsonl)
        data_count = count_messages(data_json)
        assert input_count == output_count == data_count
```

### Test: Statistics Sum Check
```python
def test_statistics_sums():
    stats = load_stats_json()
    project_sum = sum(p['sessions'] for p in stats['projects'])
    assert project_sum == stats['aggregate']['total_sessions']
```

### Test: Timestamp Preservation Check
```python
def test_timestamps():
    for project in output_projects:
        for jsonl in project.jsonl_files:
            input_file = input_path / project / jsonl.name
            if input_file.exists():
                assert jsonl.stat().st_mtime == input_file.stat().st_mtime
```

### Test: Idempotency Check
```python
def test_idempotency():
    backup()
    state1 = snapshot_output()
    backup()
    state2 = snapshot_output()
    assert state1 == state2  # Excluding stats timestamp
```

---

## Usage Notes

1. **Automated Testing**: Use these invariants to generate automated tests
2. **Debug Validation**: Check invariants when investigating bugs
3. **Regression Testing**: Verify invariants after major changes
4. **Data Recovery**: Use invariants to detect corruption
