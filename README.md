# Remi — Personal Biography Assistant

Remi is a local, private biography assistant that knows you. It stores your ground truth biographical facts in a **family tree graph** and uses them during interview sessions — so you never have to re-explain your life every time you sit down to talk.

## How It Works

1. **You fill in your facts** — `data/biography.json` holds your family tree (people, relationships, life events)
2. **Remi retrieves what's relevant** — before each interview turn, the graph-aware RAG pulls the right context
3. **You go deeper** — Remi uses your facts as a foundation and interviews you for texture, detail, and the things that aren't written down yet
4. **Sessions are saved** — every interview is stored in `data/sessions/` so Remi can pick up where you left off

## Quick Start

```bash
# 1. Install dependencies
pip install "mcp[cli]"

# For MLX (Apple Silicon):
pip install mlx-lm

# For Ollama (any platform):
# Install from https://ollama.ai, then: ollama pull qwen3:8b

# 2. Start an interview (MLX)
python scripts/interview.py --quality

# 2b. Start an interview (Ollama)
python scripts/interview.py --ollama

# 3. Focus on a specific topic
python scripts/interview.py --ollama --topic family

# 4. Resume a previous session
python scripts/interview.py --ollama --resume data/sessions/session_20260101_120000.json
```

## MCP Server

Remi includes an MCP server that lets any MCP client (Claude Desktop, Cursor, VS Code) query and update the family tree.

```bash
# Start the MCP server
python mcp_server/server.py

# Or with HTTP transport
python mcp_server/server.py --transport sse --port 8000
```

See [docs/mcp-setup.md](docs/mcp-setup.md) for full setup instructions.

## Project Structure

```
Remi/
├── data/
│   ├── biography.json       ← Your family tree (v2 graph format)
│   ├── biography_v1_backup.json  ← Backup of v1 format
│   └── sessions/            ← Auto-saved interview sessions
├── mcp_server/
│   ├── server.py            ← MCP server (for external clients)
│   └── requirements.txt
├── remi/
│   ├── family_tree.py       ← Core graph model + persistence
│   ├── biography.py         ← Convenience wrappers
│   └── rag.py               ← Graph-aware RAG retrieval
├── scripts/
│   ├── interview.py         ← Main interview script
│   └── migrate_v1_to_v2.py  ← v1 → v2 migration
├── prompts/
│   └── system.md            ← Remi's personality and instructions
└── docs/
    └── mcp-setup.md         ← MCP setup guide
```

## Models

| Flag | Model | Notes |
|------|-------|-------|
| *(default)* | `mlx-community/Llama-3.2-3B-Instruct-4bit` | Fast, lighter (MLX) |
| `--quality` | `mlx-community/Qwen2.5-7B-Instruct-4bit` | Better reasoning (MLX) |
| `--ollama` | `qwen3:8b` | Ollama backend (any platform) |
| `--model <name>` | Any compatible model | Custom model |

## Family Tree Format (v2)

The family tree is a graph: **people are nodes, relationships are edges.**

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
    }
  },
  "relationships": [
    { "person_id": "tim-jordan", "relative_id": "john-jordan", "type": "father" }
  ]
}
```

Edit `data/biography.json` or use the MCP tools to build your tree. Leave fields as `null` if unknown — Remi will discover them through interviews.

## Migrating from v1

```bash
python scripts/migrate_v1_to_v2.py
```

## Privacy

Everything runs locally. No data leaves your machine. Your biography file and sessions are yours alone.
