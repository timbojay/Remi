#!/usr/bin/env python3
"""
Remi — Personal Biography Interview

Now powered by the FamilyTree graph model for smarter context retrieval.

Usage:
  python scripts/interview.py                          # MLX default model
  python scripts/interview.py --quality                # MLX quality model
  python scripts/interview.py --ollama                 # Ollama backend
  python scripts/interview.py --ollama --model qwen3:8b
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

DEFAULT_MLX_MODEL = "mlx-community/Llama-3.2-3B-Instruct-4bit"
QUALITY_MLX_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"


# ======================================================================
# LLM Backends
# ======================================================================

class MLXBackend:
    """Apple Silicon local inference via mlx-lm."""

    def __init__(self, model_name: str):
        try:
            from mlx_lm import load
        except ImportError:
            print("ERROR: mlx-lm not installed. Run: pip install mlx-lm")
            print("       Or use --ollama for Ollama backend.")
            sys.exit(1)
        print(f"Loading MLX model: {model_name}...", flush=True)
        self.model, self.tokenizer = load(model_name)
        self.name = model_name

    def generate(self, messages: list, max_tokens: int = 500, temperature: float = 0.7) -> str:
        from mlx_lm import generate as mlx_generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        sampler = make_sampler(temp=temperature)
        return mlx_generate(
            self.model, self.tokenizer, prompt=prompt,
            max_tokens=max_tokens, sampler=sampler, verbose=False
        )


class OllamaBackend:
    """Ollama API backend — works on any platform."""

    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model = model_name
        self.base_url = base_url
        self.name = f"ollama/{model_name}"
        # Test connection
        try:
            import httpx
            r = httpx.get(f"{base_url}/api/tags", timeout=5)
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            if not any(model_name in m for m in models):
                print(f"WARNING: Model '{model_name}' not found in Ollama. Available: {models}")
        except Exception as e:
            print(f"WARNING: Could not connect to Ollama at {base_url}: {e}")
        print(f"Using Ollama model: {model_name}", flush=True)

    def generate(self, messages: list, max_tokens: int = 500, temperature: float = 0.7) -> str:
        import httpx

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
        }
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=120.0,
        )
        r.raise_for_status()
        return r.json()["message"]["content"]


# ======================================================================
# Interview Logic
# ======================================================================

def build_system_prompt(topic: str = None, tree=None) -> str:
    """Build the system prompt with graph-aware RAG context injected."""
    from remi.rag import retrieve_all, retrieve

    # Load base prompt
    if SYSTEM_PROMPT_FILE.exists():
        system = SYSTEM_PROMPT_FILE.read_text()
    else:
        system = (
            "You are Remi, a personal biography assistant. "
            "You know ground truth facts about the subject and use them "
            "to conduct a thoughtful interview."
        )

    # Inject biography context
    if topic:
        facts = retrieve(topic, tree)
    else:
        facts = retrieve_all(tree)

    if facts:
        system += f"\n\n---\n\n{facts}"
    else:
        system += (
            "\n\n---\n\n"
            "NOTE: No biography data loaded. The family tree is empty.\n"
            "Start by learning the subject's name and basic details."
        )

    return system


def save_session(history: list, session_file: Path) -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_data = {
        "timestamp": datetime.now().isoformat(),
        "history": history,
    }
    with open(session_file, "w") as f:
        json.dump(session_data, f, indent=2)
    print(f"\n✓ Session saved to {session_file}")


def load_session(session_file: Path) -> list:
    with open(session_file) as f:
        data = json.load(f)
    print(f"✓ Resumed session from {session_file} ({data['timestamp']})")
    return data["history"]


def main():
    parser = argparse.ArgumentParser(description="Remi — Personal Biography Interview")
    parser.add_argument("--model", default=None, help="Model name (backend-specific)")
    parser.add_argument("--quality", action="store_true",
                        help=f"Use quality MLX model ({QUALITY_MLX_MODEL})")
    parser.add_argument("--ollama", action="store_true",
                        help="Use Ollama backend instead of MLX")
    parser.add_argument("--ollama-url", default="http://localhost:11434",
                        help="Ollama API base URL")
    parser.add_argument("--topic", help="Focus on a topic (family, career, childhood, etc.)")
    parser.add_argument("--resume", help="Path to a previous session JSON to resume")
    parser.add_argument("--tokens", type=int, default=500, help="Max tokens per response")
    parser.add_argument("--data", default=None, help="Path to biography.json")
    args = parser.parse_args()

    # --- Load family tree ---
    from remi.family_tree import FamilyTree
    data_path = Path(args.data) if args.data else None
    try:
        tree = FamilyTree(data_path)
        people_count = len(tree.data.get("people", {}))
        rel_count = len(tree.data.get("relationships", []))
        print(f"  Family tree: {people_count} people, {rel_count} relationships")
    except (FileNotFoundError, ValueError) as e:
        print(f"  Family tree: {e}")
        tree = None

    # --- Select backend ---
    if args.ollama:
        model_name = args.model or DEFAULT_OLLAMA_MODEL
        backend = OllamaBackend(model_name, args.ollama_url)
    else:
        if args.quality:
            model_name = QUALITY_MLX_MODEL
        else:
            model_name = args.model or DEFAULT_MLX_MODEL
        backend = MLXBackend(model_name)

    print("\n" + "=" * 60)
    print("  REMI — Personal Biography Assistant")
    print("=" * 60)
    print(f"  Model:  {backend.name}")
    if args.topic:
        print(f"  Topic:  {args.topic}")
    print("  Type 'quit' or 'exit' to end the session.")
    print("=" * 60 + "\n")

    system = build_system_prompt(args.topic, tree)

    # Build message history
    if args.resume:
        history = load_session(Path(args.resume))
    else:
        history = []

    # Session file
    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    topic_tag = f"_{args.topic}" if args.topic else ""
    session_file = SESSIONS_DIR / f"session_{session_ts}{topic_tag}.json"

    # Opening message
    if not history:
        opening_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Please begin the interview session. "
                                        "Introduce yourself briefly and ask your first question."},
        ]
        print("Remi: ", end="", flush=True)
        opening = backend.generate(opening_messages, args.tokens)
        print(opening)
        history.append({"role": "assistant", "content": opening})
    else:
        print("--- Resuming from previous session ---\n")
        for msg in history[-4:]:
            role = "Remi" if msg["role"] == "assistant" else "You"
            print(f"{role}: {msg['content']}\n")

    # --- Interview loop ---
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

        # Rebuild context based on latest input (focused retrieval)
        from remi.rag import retrieve
        focused_facts = retrieve(user_input, tree)
        if focused_facts:
            current_system = system + f"\n\n---\n\n[CONTEXT FOR THIS TURN]\n{focused_facts}"
        else:
            current_system = system

        messages = [{"role": "system", "content": current_system}] + history

        print("\nRemi: ", end="", flush=True)
        response = backend.generate(messages, args.tokens)
        print(response)

        history.append({"role": "assistant", "content": response})
        save_session(history, session_file)

    save_session(history, session_file)
    print(f"\n✓ Full session saved to {session_file}\n")


if __name__ == "__main__":
    main()
