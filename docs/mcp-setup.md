# MCP Server Setup Guide

Remi includes an MCP (Model Context Protocol) server that exposes the family tree data to any MCP-compatible client — Claude Desktop, Cursor, VS Code Copilot, and more.

## Quick Start

### 1. Install dependencies

```bash
cd Remi
pip install "mcp[cli]"
```

### 2. Start the server

**Stdio transport** (for MCP client configs):
```bash
python mcp_server/server.py
```

**SSE/HTTP transport** (for network access):
```bash
python mcp_server/server.py --transport sse --port 8000
```

### 3. Connect a client

#### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "remi-family-tree": {
      "command": "python3",
      "args": ["/full/path/to/Remi/mcp_server/server.py"],
      "env": {}
    }
  }
}
```

#### Cursor / VS Code

Add to your MCP config:

```json
{
  "mcpServers": {
    "remi-family-tree": {
      "command": "python3",
      "args": ["/full/path/to/Remi/mcp_server/server.py"]
    }
  }
}
```

#### Custom data file

Pass `--data` to use a different biography file:

```bash
python mcp_server/server.py --data /path/to/other/biography.json
```

---

## Available Tools

### Read Tools

| Tool | Description |
|------|-------------|
| `get_subject()` | Get the main interview subject's data |
| `get_person(person_id)` | Get full data for any person |
| `search_people(query)` | Fuzzy name search |
| `list_people()` | List everyone in the tree |
| `get_relatives(person_id, type?)` | Get relatives, optionally filtered |
| `find_relationship(a, b)` | Find connection path between two people |
| `get_timeline(person_id)` | Chronological life events |
| `get_unexplored(person_id?)` | Find gaps in biographical data |
| `get_family_summary(person_id)` | Human-readable family overview |

### Write Tools

| Tool | Description |
|------|-------------|
| `add_person(name, ...)` | Add a new person to the tree |
| `update_person(id, field, value)` | Update a field on someone's record |
| `add_relationship(from, to, type)` | Link two people |
| `add_memory(person_id, text, ...)` | Record a memory or anecdote |

### Resources

| Resource | Description |
|----------|-------------|
| `family://tree/summary` | Overview of the entire tree |

---

## Data Format (v2)

The family tree uses `data/biography.json` in v2 format:

```json
{
  "_meta": {
    "version": "2.0",
    "subject_id": "tim-jordan",
    "last_updated": "2026-03-11"
  },
  "people": {
    "tim-jordan": {
      "id": "tim-jordan",
      "name": "Timothy Jordan",
      "preferred_name": "Tim",
      "date_of_birth": "1985-06-12",
      "place_of_birth": "Manchester, England",
      ...
    }
  },
  "relationships": [
    {
      "person_id": "tim-jordan",
      "relative_id": "john-jordan",
      "type": "father",
      "notes": null
    }
  ]
}
```

### Relationship types

`father`, `mother`, `son`, `daughter`, `brother`, `sister`, `sibling`,
`spouse`, `partner`, `grandfather`, `grandmother`, `grandchild`,
`uncle`, `aunt`, `nephew`, `niece`, `cousin`, `stepfather`, `stepmother`,
`stepchild`, `half-brother`, `half-sister`, `friend`, `other`

Inverse relationships are resolved automatically — you only need to store
each relationship once.

---

## Migrating from v1

If you have an existing v1 `biography.json`:

```bash
python scripts/migrate_v1_to_v2.py
```

This reads `data/biography_v1_backup.json` and writes the v2 format to `data/biography.json`.

---

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐
│  Remi Interview      │     │  Claude Desktop /    │
│  (scripts/interview) │     │  Cursor / VS Code    │
│                      │     │  (any MCP client)    │
└──────────┬───────────┘     └──────────┬───────────┘
           │ direct import              │ MCP protocol
           ▼                            ▼
┌──────────────────────────────────────────────────┐
│               remi/family_tree.py                 │
│          (graph model + JSON persistence)         │
└──────────────────────┬───────────────────────────┘
                       │
                       ▼
              data/biography.json
```

Remi's interview script uses `family_tree.py` directly for efficiency.
External MCP clients connect via `mcp_server/server.py`, which wraps
the same `FamilyTree` class.
