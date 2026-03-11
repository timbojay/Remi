# Remi 🧠

A personal biographical AI — your life story, always within reach.

Remi combines a conversational LangGraph agent, a structured knowledge graph, and an MCP server so your biography is accessible from any AI tool that supports the Model Context Protocol.

---

## What Remi Does

- **Chats with you** to discover your life story, one conversation at a time
- **Extracts and stores** facts, people, places, and relationships automatically
- **Tracks coverage** — knows what areas of your life are well documented vs. unexplored
- **Generates prose biographies** from accumulated facts on demand
- **Exposes everything via MCP** — Claude Desktop, Cursor, VS Code Copilot, and more can read and write your biography

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (Swift/iOS)               │
│  Chat · Biography · Family Tree · Timeline · People │
└───────────────────┬─────────────────────────────────┘
                    │ REST API
┌───────────────────▼─────────────────────────────────┐
│              Backend (FastAPI + LangGraph)           │
│                                                     │
│  Agent Pipeline:                                    │
│  RECEIVE → CLASSIFY → STRATEGIZE → RESPOND          │
│                    ↓                                │
│             EXTRACT → FINALIZE                      │
│                                                     │
│  Services: biography_generator · export · LLM       │
│  DB: SQLite knowledge graph (facts, entities,       │
│      relationships, coverage, provenance)           │
└───────────────────┬─────────────────────────────────┘
                    │ direct DB access
┌───────────────────▼─────────────────────────────────┐
│              MCP Server (FastMCP)                   │
│  Tools: get_biography_summary · get_facts ·         │
│         search_facts · get_entities · get_family_   │
│         tree · add_fact · add_entity · add_         │
│         relationship · get_coverage_gaps · ...      │
└─────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY and USER_NAME
```

### 3. (Optional) Migrate existing biography.json

If you have data in `data/biography.json`, seed the database:

```bash
python scripts/migrate_json_to_db.py
```

### 4. Start the backend

```bash
cd backend
python run.py
# API available at http://127.0.0.1:8001
```

### 5. Run the MCP server

```bash
python mcp_server/server.py
# Or with SSE transport:
python mcp_server/server.py --transport sse --port 8000
```

---

## MCP Setup (Claude Desktop)

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "remi": {
      "command": "python",
      "args": ["/path/to/Remi/mcp_server/server.py"],
      "env": {
        "DB_PATH": "/path/to/Remi/backend/data/remi.db"
      }
    }
  }
}
```

See `docs/mcp-setup.md` for full setup instructions.

---

## Project Structure

```
Remi/
├── backend/                # FastAPI backend + LangGraph agent
│   ├── app/
│   │   ├── agent/          # LangGraph nodes (receive, classify, respond, extract…)
│   │   ├── db/             # SQLite knowledge graph + vector store
│   │   ├── routers/        # FastAPI routes (chat, biography, knowledge, status)
│   │   └── services/       # biography_generator, export_engine, LLM, maintenance
│   ├── requirements.txt
│   └── run.py
├── frontend/               # Swift/iOS app
│   └── Biographer/         # Xcode project
├── mcp_server/             # MCP server (reads/writes SQLite knowledge graph)
│   ├── server.py
│   └── requirements.txt
├── scripts/
│   ├── interview.py        # CLI interview tool
│   ├── migrate_json_to_db.py  # Migrate biography.json → SQLite
│   └── migrate_v1_to_v2.py   # Migrate v1 → v2 JSON format
├── data/
│   └── biography.json      # Legacy JSON (still used by CLI tools)
├── docs/
│   └── mcp-setup.md        # MCP setup guide
├── .env.example
└── requirements.txt
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required for the LangGraph agent |
| `USER_NAME` | `Tim` | Name used in biography prompts |
| `MODEL_NAME` | `claude-sonnet-4-20250514` | Claude model to use |
| `DB_PATH` | `backend/data/remi.db` | SQLite database path |

---

## iOS Frontend

The Swift app (in `frontend/`) connects to the backend API and provides:
- **Chat** — conversational interview interface
- **Biography** — generated prose biography
- **Family Tree** — visual family graph
- **Timeline** — chronological life events
- **People** — all known entities
- **Coverage** — visual life domain coverage

Open `frontend/Biographer/project.yml` with [XcodeGen](https://github.com/yonaskolb/XcodeGen) to generate the Xcode project.
