# Remi — Personal Biography Assistant

Remi is a local, private biography assistant that knows *you*. It stores your ground truth biographical facts and uses them during interview sessions — so you never have to re-explain your life every time you sit down to talk.

## How It Works

1. **You fill in your facts** — `data/biography.json` holds what Remi already knows about you (DOB, family, places, career, milestones)
2. **Remi retrieves what's relevant** — before each interview turn, RAG pulls the relevant sections of your biography into context
3. **You go deeper** — Remi uses your facts as a foundation and interviews you for texture, detail, and the things that aren't written down yet
4. **Sessions are saved** — every interview is stored in `data/sessions/` so Remi can pick up where you left off

## Quick Start

```bash
# 1. Install dependencies
pip install mlx-lm

# 2. Fill in your facts
nano data/biography.json

# 3. Start an interview
python scripts/interview.py --quality

# 4. Focus on a specific topic
python scripts/interview.py --quality --topic family

# 5. Resume a previous session
python scripts/interview.py --quality --resume data/sessions/session_20260101_120000.json
```

## Project Structure

```
Remi/
├── data/
│   ├── biography.json       ← Your ground truth facts (fill this in!)
│   ├── sessions/            ← Auto-saved interview sessions
│   └── raw/                 ← Any raw transcripts or notes
├── prompts/
│   └── system.md            ← Remi's personality and instructions
├── remi/
│   ├── biography.py         ← Loads and queries biography data
│   └── rag.py               ← RAG retrieval logic
└── scripts/
    └── interview.py         ← Main interview script
```

## Models

| Flag | Model | Notes |
|------|-------|-------|
| (default) | `mlx-community/Llama-3.2-3B-Instruct-4bit` | Fast, lighter |
| `--quality` | `mlx-community/Qwen2.5-7B-Instruct-4bit` | Better reasoning |
| `--model <name>` | Any MLX model | Custom model |

## Filling In Your Biography

Edit `data/biography.json` with what you know. Leave fields as `null` if unknown — Remi will discover them through interviews.

Example:
```json
{
  "subject": {
    "name": "Timothy Jordan",
    "preferred_name": "Tim",
    "date_of_birth": "1985-06-12",
    "place_of_birth": "Manchester, England"
  }
}
```

## Privacy

Everything runs locally on your machine. No data leaves your computer. Your biography file and sessions are yours alone.
