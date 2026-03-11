# Quick Start — Remi with MCP

You have 3 ways to use Remi now. Pick one:

---

## Way 1: Local Interview (Simplest)

Just talk to Remi about your life.

```bash
cd Remi

# First time: edit data/biography.json with basic facts about yourself
# (or leave it empty — Remi will ask)

# Start an interview
python scripts/interview.py --ollama

# Questions you might see:
# "Please begin the interview..."
# Then answer naturally, and Remi remembers everything

# Exit: type "quit" or "exit"
```

**Tips:**
- First run takes 30 seconds to load the model
- Each turn (question + answer) saves automatically
- Resume later: `python scripts/interview.py --ollama --resume data/sessions/session_*.json`
- Focus on a topic: `python scripts/interview.py --ollama --topic family`

---

## Way 2: MCP Server + Claude Desktop (Most Powerful)

Use Claude to query your family tree, add facts, and even interview you.

```bash
# Terminal 1: Start the MCP server
cd Remi
python mcp_server/server.py

# Terminal 2: Configure Claude Desktop
# Add to ~/Library/Application Support/Claude/claude_desktop_config.json:
{
  "mcpServers": {
    "remi": {
      "command": "python3",
      "args": ["/full/path/to/Remi/mcp_server/server.py"]
    }
  }
}

# Restart Claude Desktop
# Now try asking Claude:
# - "Who is in my family tree?"
# - "Add my father John to the tree"
# - "Show me the timeline of my career"
# - "What gaps are there in my biographical data?"
```

**Tips:**
- The MCP server is the **same data** as local Remi — changes sync automatically
- Claude has access to tools like `get_unexplored()`, `add_memory()`, etc.
- Great for querying: Claude is better at understanding complex questions

---

## Way 3: Cursor / VS Code (For Coding)

If you use Cursor or VS Code with Copilot, add the same MCP config and use it within your editor.

Same setup as Way 2 — add to your Cursor/VS Code MCP config.

---

## First Time Setup

### 1. Ensure Ollama is running

```bash
# If you haven't:
# Download from https://ollama.ai
# Then pull the model
ollama pull qwen3:8b

# Check it's running
curl http://localhost:11434/api/tags
```

### 2. Edit your biography (optional)

`data/biography.json` starts empty. You can either:
- **A)** Edit the file directly
- **B)** Leave it empty and let Remi ask you
- **C)** Use MCP to add people: `add_person("Tim", preferred_name="Timothy", ...)`

Example of manual edit:
```json
{
  "_meta": {
    "version": "2.0",
    "subject_id": "tim-jordan"
  },
  "people": {
    "tim-jordan": {
      "id": "tim-jordan",
      "name": "Timothy Jordan",
      "preferred_name": "Tim",
      "date_of_birth": "1985-06-12",
      "place_of_birth": "Manchester, England"
    }
  },
  "relationships": []
}
```

### 3. Start interviewing

```bash
python scripts/interview.py --ollama
```

---

## What to Expect

**Session 1:**
- Remi introduces itself
- Asks your name (if not in `subject_id`)
- Asks about childhood, family, key moments
- Saves everything to `data/sessions/`

**Session 2+:**
- Remi remembers what you said before
- Asks follow-up questions
- Explores gaps: "I don't know where you were born..."
- Builds a richer story each time

---

## Advanced: MCP Tools

If you want to use the MCP tools directly (via Claude or programmatically):

```bash
# Start server
python mcp_server/server.py

# In Claude:
get_person("tim-jordan")
# Returns full person data

find_relationship("tim-jordan", "john-jordan")
# Shows path between two people

get_unexplored()
# Shows what's still unknown

add_memory("tim-jordan", "Went to Cambridge in 1995", year="1995", topic="education")
# Capture a memory from an interview
```

---

## Directory Structure

```
Remi/
├── data/
│   └── biography.json          ← Your family tree (edit this!)
│   └── sessions/               ← Interview saves (auto-generated)
├── scripts/
│   └── interview.py            ← Run this to interview
├── mcp_server/
│   └── server.py               ← Run this for Claude Desktop
└── remi/
    └── family_tree.py          ← Core graph model (don't edit)
    └── rag.py                  ← Context retrieval (don't edit)
```

---

## Troubleshooting

**"ModuleNotFoundError: No module named 'mcp'"**
```bash
pip install --break-system-packages "mcp[cli]"
```

**"Could not connect to Ollama at http://localhost:11434"**
```bash
# Make sure ollama is running
ollama list
ollama pull qwen3:8b
ollama serve
```

**"biography.json is v1 format"**
```bash
python scripts/migrate_v1_to_v2.py
```

**"No biography data loaded. The family tree is empty."**
- This is OK! Remi will ask you to fill it in.
- Or edit `data/biography.json` and add your name as the subject.

---

## That's It!

You're ready. Pick way 1, 2, or 3 above and start.

For more details, see `SETUP_COMPLETE.md` or `docs/mcp-setup.md`.
