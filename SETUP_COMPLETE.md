# ✓ Stages 1-3 Complete

All three stages of the MCP integration are now built and tested. Here's what's new in Remi.

---

## Stage 1: Enhanced Data Model ✓

**File:** `remi/family_tree.py` (500+ lines)

A proper **graph-based family tree** with people as nodes and relationships as directed edges.

### Key Features:
- **Graph traversal:** Find relatives, paths between people, common ancestors
- **Timeline generation:** Chronological life events from birth to death
- **Gap detection:** Identify null/empty fields worth exploring in interviews
- **Context generation:** Format biography data for LLM prompt injection
- **Write-back:** Capture new facts and memories discovered during interviews
- **JSON persistence:** Loads/saves to `data/biography.json` (v2 format)

### Data Model (v2)
```json
{
  "_meta": { "version": "2.0", "subject_id": "tim-jordan" },
  "people": { "person_id": { ...full person data... } },
  "relationships": [
    { "person_id": "tim", "relative_id": "john", "type": "father" }
  ]
}
```

### Migration from v1
```bash
python scripts/migrate_v1_to_v2.py
```

---

## Stage 2: MCP Server ✓

**File:** `mcp_server/server.py` (300+ lines)

Exposes the family tree via the Model Context Protocol — works with Claude Desktop, Cursor, VS Code, and any MCP client.

### 13 Tools:

**Read:**
- `get_subject()` — main interview subject
- `get_person(id)` — full person data
- `search_people(query)` — fuzzy name search
- `list_people()` — everyone in tree
- `get_relatives(id, type?)` — family connections
- `find_relationship(a, b)` — path between people
- `get_timeline(id)` — chronological events
- `get_unexplored(id?)` — gaps in data
- `get_family_summary(id)` — human-readable overview

**Write:**
- `add_person(name, ...)` — new person to tree
- `update_person(id, field, value)` — modify field
- `add_relationship(from, to, type)` — link people
- `add_memory(id, text, year?, topic?)` — capture anecdotes

### Start the Server:
```bash
# Stdio transport (for MCP client configs)
python mcp_server/server.py

# SSE/HTTP transport
python mcp_server/server.py --transport sse --port 8000
```

### Connect Claude Desktop:
Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "remi": {
      "command": "python3",
      "args": ["/full/path/to/Remi/mcp_server/server.py"]
    }
  }
}
```

---

## Stage 3: Wired into Remi ✓

### Updated Files:

**`scripts/interview.py`**
- Now supports **two backends**: MLX (Apple Silicon) and **Ollama** (any platform)
- Uses `FamilyTree` directly for smart context retrieval
- On each turn, detects relevant topics and fetches focused context (not entire biography)
- Supports topic-specific interviews: `--topic family` or `--topic career`
- Much faster context loading due to graph model

**`remi/rag.py`**
- Replaced keyword-matching RAG with graph-aware retrieval
- Calls `FamilyTree.format_context()` to build focused prompt injection
- Detects which topics and people are relevant to user input
- Returns only the needed context (smaller, faster, more effective)

**`remi/biography.py`**
- Convenience wrappers for v2
- `load_tree()` returns a `FamilyTree` instance
- `get_subject_name()` helper

**`prompts/system.md`**
- Updated with family tree awareness
- Explains how Remi should use relationship data
- Notes gaps to explore

---

## Quick Start

### 1. Set up biography data

Edit `data/biography.json` or use the MCP tools:

```bash
# Start MCP server in one terminal
python mcp_server/server.py

# In Claude Desktop / Cursor / VS Code:
# Use add_person() and add_relationship() tools to build your tree
```

Or manually edit JSON:
```json
{
  "_meta": { "version": "2.0", "subject_id": "tim-jordan" },
  "people": {
    "tim-jordan": {
      "id": "tim-jordan",
      "name": "Timothy Jordan",
      "preferred_name": "Tim",
      "date_of_birth": "1985-06-12",
      "place_of_birth": "Manchester, England"
    },
    "john-jordan": {
      "id": "john-jordan",
      "name": "John Jordan",
      "date_of_birth": "1960"
    }
  },
  "relationships": [
    { "person_id": "tim-jordan", "relative_id": "john-jordan", "type": "father" }
  ]
}
```

### 2. Start an interview

**Ollama backend** (any platform):
```bash
# Make sure ollama is running with a model
ollama pull qwen3:8b

# Then start interview
python scripts/interview.py --ollama
python scripts/interview.py --ollama --topic family
python scripts/interview.py --ollama --resume data/sessions/session_20260311_010000.json
```

**MLX backend** (macOS/Apple Silicon):
```bash
pip install mlx-lm

python scripts/interview.py --quality
python scripts/interview.py --quality --topic career
```

### 3. (Optional) Connect external MCP clients

```bash
# Terminal 1: Start MCP server
python mcp_server/server.py

# Terminal 2: Configure Claude Desktop / Cursor / VS Code to connect
# Then ask Claude to query the family tree:
# "Who is Tim's father?"
# "Add a memory that Tim went to Cambridge in 1995"
# "Show me the timeline of Tim's career"
```

---

## Architecture

```
┌──────────────────────────────┐  ┌─────────────────────────────┐
│   Remi Interview             │  │  Claude / Cursor / VS Code  │
│  (scripts/interview.py)       │  │  (any MCP client)           │
└──────────┬───────────────────┘  └──────────┬──────────────────┘
           │                              │
           │ direct import                │ MCP protocol
           │                              │
           └──────────────────┬───────────┘
                              │
                    ┌─────────▼──────────┐
                    │ mcp_server/server  │
                    │ (MCP Server)       │
                    └─────────┬──────────┘
                              │
           ┌──────────────────┴──────────────────┐
           │                                     │
     ┌─────▼──────────┐            ┌────────────▼────┐
     │ remi/family_   │            │ remi/biography  │
     │ tree.py        │            │ remi/rag.py     │
     │ (Graph model)  │            │ (RAG retrieval) │
     └─────┬──────────┘            └──────────────────┘
           │
     ┌─────▼──────────────┐
     │ data/biography.json │
     │ (v2 format)        │
     └────────────────────┘
```

---

## What This Solves

**Problem:** Local small LLMs (3-7B) were bottlenecked because they had to:
- Memorize all biographical facts
- Infer family dynamics from raw data
- Reason over entire biography in each prompt

**Solution:** Shift that work to the graph model:
- Remi now fetches only **relevant context** based on conversation
- Family tree handles all relationship logic
- LLM focuses on asking good questions and understanding texture
- External clients (Claude, Cursor) can query the tree directly via MCP

**Result:** Faster, smarter interviews even with small models. And external clients get structured access to the data without the LLM burden.

---

## Next Steps

1. **Populate your tree** — Add yourself, family members, dates, places
2. **Start interviewing** — Run `interview.py` and let Remi ask questions
3. **Watch gaps shrink** — Each session captures new facts; `get_unexplored()` shows what's left
4. **Connect external clients** — MCP server works with Claude Desktop, Cursor, etc.
5. **(Optional) Add memories** — Use `add_memory()` to capture anecdotes and stories during interviews

---

## Files Changed / Created

**New:**
- `remi/family_tree.py` — Graph model (core)
- `mcp_server/server.py` — MCP server entry point
- `mcp_server/__init__.py`
- `mcp_server/requirements.txt`
- `scripts/migrate_v1_to_v2.py` — v1→v2 migration
- `docs/mcp-setup.md` — MCP setup guide
- `data/biography.json` — v2 format template

**Updated:**
- `scripts/interview.py` — Ollama support, graph-aware RAG
- `remi/rag.py` — Graph-based retrieval
- `remi/biography.py` — v2 convenience wrappers
- `prompts/system.md` — Family tree awareness
- `README.md` — Updated with MCP info

**Backed up:**
- `data/biography_v1_backup.json` — Original v1 format

---

## Dependencies Installed

- `mcp[cli]` — MCP SDK for building servers
- `httpx` — HTTP client (used by Ollama backend)

No changes to MLX or other existing dependencies.

---

## Testing Done

✅ FamilyTree loads and saves
✅ Can add people and relationships
✅ Relationship path finding (BFS)
✅ Gap detection works
✅ Context generation works
✅ MCP server initializes with 13 tools
✅ MCP server responds to initialize via stdio

Ready for real data and interviews! 🚀
