#!/usr/bin/env python3
"""
Remi — Personal Biography Interview
Usage:
  python scripts/interview.py
  python scripts/interview.py --model mlx-community/Qwen2.5-7B-Instruct-4bit
  python scripts/interview.py --topic family
  python scripts/interview.py --resume data/sessions/session_001.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

SYSTEM_PROMPT_FILE = BASE_DIR / "prompts" / "system.md"
SESSIONS_DIR = BASE_DIR / "data" / "sessions"

DEFAULT_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
QUALITY_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"


def load_model(model_name: str):
    try:
        from mlx_lm import load
    except ImportError:
        print("ERROR: mlx-lm not installed. Run: pip install mlx-lm")
        sys.exit(1)
    print(f"Loading model: {model_name}...", flush=True)
    return load(model_name)


def generate(model, tokenizer, messages: list, max_tokens: int = 500, temperature: float = 0.7) -> str:
    from mlx_lm import generate as mlx_generate
    from mlx_lm.sample_utils import make_sampler

    prompt = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False
    )
    sampler = make_sampler(temp=temperature)
    return mlx_generate(model, tokenizer, prompt=prompt,
                        max_tokens=max_tokens, sampler=sampler, verbose=False)


def build_system_prompt(topic: str = None) -> str:
    """Build the full system prompt with RAG-retrieved facts injected."""
    from remi.rag import retrieve_all, retrieve

    # Load base system prompt
    if SYSTEM_PROMPT_FILE.exists():
        system = SYSTEM_PROMPT_FILE.read_text()
    else:
        system = "You are Remi, a personal biography assistant. You know ground truth facts about the subject and use them to conduct a thoughtful interview."

    # Inject biography facts
    if topic:
        facts = retrieve(topic)
    else:
        facts = retrieve_all()

    if facts:
        system += f"\n\n---\n\n{facts}"
    else:
        system += "\n\n---\n\nNOTE: No biography data found. Ask the subject to fill in data/biography.json with their known facts."

    return system


def save_session(history: list, session_file: Path) -> None:
    """Save the interview session to disk."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "history": history
    }
    with open(session_file, "w") as f:
        json.dump(session_data, f, indent=2)
    print(f"\n✓ Session saved to {session_file}")


def load_session(session_file: Path) -> list:
    """Load a previous interview session."""
    with open(session_file) as f:
        data = json.load(f)
    print(f"✓ Resumed session from {session_file} ({data['timestamp']})")
    return data["history"]


def main():
    parser = argparse.ArgumentParser(description="Remi — Personal Biography Interview")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--quality", action="store_true",
                        help=f"Use quality model ({QUALITY_MODEL})")
    parser.add_argument("--topic", help="Focus the session on a specific topic (e.g. family, career, childhood)")
    parser.add_argument("--resume", help="Path to a previous session JSON to resume from")
    parser.add_argument("--tokens", type=int, default=500, help="Max tokens per response")
    args = parser.parse_args()

    model_name = QUALITY_MODEL if args.quality else args.model

    print("\n" + "="*60)
    print("  REMI — Personal Biography Assistant")
    print("="*60)
    print(f"  Model: {model_name}")
    if args.topic:
        print(f"  Topic: {args.topic}")
    print("  Type 'quit' or 'exit' to end the session.")
    print("="*60 + "\n")

    model, tokenizer = load_model(model_name)
    system = build_system_prompt(args.topic)

    # Build message history
    if args.resume:
        history = load_session(Path(args.resume))
    else:
        history = []

    # Session file for saving
    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_tag = f"_{args.topic}" if args.topic else ""
    session_file = SESSIONS_DIR / f"session_{session_ts}{topic_tag}.json"

    # Opening message from Remi
    if not history:
        opening_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Please begin the interview session. Introduce yourself briefly and ask your first question."}
        ]
        print("Remi: ", end="", flush=True)
        opening = generate(model, tokenizer, opening_messages, args.tokens)
        print(opening)
        history.append({"role": "assistant", "content": opening})
    else:
        # Print recent history for context
        print("--- Resuming from previous session ---\n")
        for msg in history[-4:]:
            role = "Remi" if msg["role"] == "assistant" else "You"
            print(f"{role}: {msg['content']}\n")

    # Interview loop
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nEnding session...")
            break

        if user_input.lower() in ("quit", "exit", "bye", "stop"):
            print("\nRemi: Thank you — this has been wonderful. We'll pick up again soon.")
            break

        if not user_input:
            continue

        history.append({"role": "user", "content": user_input})

        # Build messages for this turn
        messages = [{"role": "system", "content": system}] + history

        print("\nRemi: ", end="", flush=True)
        response = generate(model, tokenizer, messages, args.tokens)
        print(response)

        history.append({"role": "assistant", "content": response})

        # Auto-save every turn
        save_session(history, session_file)

    save_session(history, session_file)
    print(f"\n✓ Full session saved to {session_file}\n")


if __name__ == "__main__":
    main()
