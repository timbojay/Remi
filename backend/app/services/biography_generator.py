"""On-demand biography generation from facts → prose via Claude."""

import hashlib
import json
from app.db import knowledge_graph as kg
from app.config import settings
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage

# Cache: hash of facts → generated biography text
_biography_cache: dict[str, str] = {}

BIOGRAPHY_PROMPT = """You are writing a biographical essay about {user_name} based on the facts below.

## Guidelines
- Write in third person, past/present tense as appropriate.
- Organize chronologically or by life domain (family, education, career, etc.)
- Use natural prose — this should read like a biography, not a list.
- Include all facts provided, weaving them into a cohesive narrative.
- If there are gaps in the story, don't invent — just transition naturally.
- Keep it concise but warm. Each section should be 1-3 paragraphs.
- Use section headings (## Family, ## Education, etc.) to organize.
"""


async def generate_biography(user_name: str = "") -> str:
    """Generate a prose biography from all known facts."""
    user_name = user_name or settings.USER_NAME

    # Get all data
    all_facts = await kg.get_all_facts()
    all_entities = await kg.get_all_entities()

    if not all_facts:
        return "No biographical information recorded yet."

    # Build a hash of current facts to check cache
    facts_hash = hashlib.md5(
        json.dumps([f["value"] for f in all_facts], sort_keys=True).encode()
    ).hexdigest()

    if facts_hash in _biography_cache:
        return _biography_cache[facts_hash]

    # Build facts context grouped by category
    by_category: dict[str, list[str]] = {}
    for fact in all_facts:
        cat = fact.get("category", "other")
        by_category.setdefault(cat, []).append(fact["value"])

    facts_text = ""
    for cat, values in sorted(by_category.items()):
        facts_text += f"\n### {cat.replace('_', ' ').title()}\n"
        for v in values:
            facts_text += f"- {v}\n"

    # Entity context
    people = [e for e in all_entities if e["entity_type"] == "person"]
    if people:
        facts_text += "\n### Key People\n"
        for p in people:
            desc = f" — {p['description']}" if p.get("description") else ""
            role = f" ({p['family_role']})" if p.get("family_role") else ""
            facts_text += f"- {p['name']}{role}{desc}\n"

    # Generate with Claude
    biography = await invoke_with_retry(
        [
            SystemMessage(content=BIOGRAPHY_PROMPT.format(user_name=user_name)),
            HumanMessage(content=f"Write a biography from these facts:\n{facts_text}"),
        ],
        node="biography",
        max_tokens=4096,
    )

    # Cache it
    _biography_cache[facts_hash] = biography

    return biography


def invalidate_cache():
    """Clear the biography cache (call after new facts are added)."""
    _biography_cache.clear()
