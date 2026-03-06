"""
biography.py — Load, query, and save biographical ground truth data.
"""

import json
from pathlib import Path
from typing import Any

BIOGRAPHY_FILE = Path(__file__).parent.parent / "data" / "biography.json"

# Maps topic keywords to biography sections
TOPIC_MAP = {
    "family": ["family", "parent", "mother", "father", "sibling", "brother", "sister",
               "spouse", "partner", "wife", "husband", "child", "children", "son", "daughter",
               "grandparent", "grandmother", "grandfather", "relative", "cousin", "uncle", "aunt"],
    "places": ["place", "live", "lived", "born", "grew up", "moved", "home", "city",
               "town", "country", "location", "address", "where"],
    "education": ["school", "university", "college", "study", "studied", "degree",
                  "qualification", "graduate", "education", "learn", "course"],
    "career": ["work", "job", "career", "employer", "company", "role", "profession",
               "occupation", "business", "employed", "hire", "salary"],
    "milestones": ["milestone", "important", "significant", "event", "happened", "memory",
                   "moment", "landmark", "turning point", "first time", "achievement"],
    "subject": ["name", "born", "age", "nationality", "who are you", "about you",
                "tell me about yourself", "background"],
    "interests": ["hobby", "interest", "enjoy", "passion", "like", "love", "sport",
                  "music", "book", "film", "travel", "pastime"]
}


def load() -> dict:
    """Load the biography data from disk."""
    if not BIOGRAPHY_FILE.exists():
        raise FileNotFoundError(f"Biography file not found: {BIOGRAPHY_FILE}")
    with open(BIOGRAPHY_FILE) as f:
        return json.load(f)


def save(data: dict) -> None:
    """Save updated biography data to disk."""
    from datetime import date
    data["_meta"]["last_updated"] = str(date.today())
    with open(BIOGRAPHY_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"✓ Biography saved to {BIOGRAPHY_FILE}")


def detect_topics(text: str) -> list[str]:
    """Detect which biography sections are relevant to a given text."""
    text_lower = text.lower()
    matched = []
    for topic, keywords in TOPIC_MAP.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(topic)
    return matched if matched else list(TOPIC_MAP.keys())  # fallback: return all


def get_sections(topics: list[str], bio: dict) -> dict:
    """Extract the relevant sections from the biography for given topics."""
    sections = {}
    for topic in topics:
        if topic in bio and bio[topic]:
            sections[topic] = bio[topic]
    return sections


def format_for_prompt(sections: dict, subject_name: str = None) -> str:
    """Format retrieved biography sections as a readable prompt injection."""
    if not sections:
        return ""

    name = subject_name or "the subject"
    lines = [f"KNOWN FACTS ABOUT {name.upper()}:"]
    lines.append("(These are verified ground truth facts. Use them — do not contradict them.)\n")

    for section, data in sections.items():
        lines.append(f"[{section.upper()}]")
        if isinstance(data, list):
            for item in data:
                if item and any(v for v in item.values() if v and v != "null"):
                    lines.append("  " + _format_item(item))
        elif isinstance(data, dict):
            for k, v in data.items():
                if v and k != "_meta":
                    lines.append(f"  {k}: {v}")
        elif data:
            lines.append(f"  {data}")
        lines.append("")

    return "\n".join(lines)


def _format_item(item: dict) -> str:
    """Format a single dict item as a readable line."""
    parts = []
    for k, v in item.items():
        if v and v not in ("null", "birthplace|childhood|education|work|current"):
            parts.append(f"{k}: {v}")
    return " | ".join(parts) if parts else ""
