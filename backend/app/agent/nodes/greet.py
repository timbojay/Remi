"""GREET node: Generates a personalized greeting for a new session."""

from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage

from app.agent.prompts import GREET_PROMPT
from app.db import knowledge_graph as kg
from app.services.llm import invoke_with_retry
from app.config import settings


async def _build_greet_context(user_name: str) -> str:
    """Build a compact context for the greeting LLM.

    Very conservative — only includes facts that are almost certainly
    still true today (identity, family, current residence).
    Past events, trips, old vehicles, etc. are excluded entirely because
    qwen3:8b will present them as current otherwise.
    """
    facts = await kg.get_all_facts()
    entities = await kg.get_all_entities()

    if not facts and not entities:
        return f"You don't know anything about {user_name} yet — this is a first conversation."

    # ONLY these categories are safe for greeting context — they describe
    # who someone IS, not what they DID
    SAFE_CATEGORIES = {"identity", "family"}
    this_year = date.today().year

    current_facts = []
    for f in facts:
        year = f.get("date_year")
        cat = f.get("category", "")

        # Skip anything with an old date
        if year and year < this_year - 2:
            continue

        val_lower = f["value"].lower()

        # Skip heavy/sensitive facts — too intense for a greeting
        if any(word in val_lower for word in ["died", "death", "passed away", "funeral", "cancer", "illness"]):
            continue

        # Only include identity and family facts (these are inherently current)
        if cat in SAFE_CATEGORIES:
            current_facts.append(f["value"])
        # Also include residence facts that DON'T mention past tense indicators
        elif cat == "residence":
            # Skip facts that mention past-tense movement or old places
            if any(word in val_lower for word in ["was", "used to", "moved from", "left", "grew up"]):
                continue
            current_facts.append(f["value"])

    # People summary — just names and roles
    people = [e for e in entities if e["entity_type"] == "person"]
    people_strs = []
    for p in people[:10]:
        label = p["name"]
        if p.get("family_role"):
            label += f" ({p['family_role']})"
        people_strs.append(label)

    # Build context
    parts = []

    if current_facts:
        parts.append(f"What you currently know about {user_name}:\n- " + "\n- ".join(current_facts[:6]))
    else:
        parts.append(
            f"You've learned about {user_name}'s past but don't know much about their current life yet. "
            f"This is a good opportunity to ask about what they're up to these days."
        )

    if people_strs:
        parts.append(f"People in {user_name}'s life: {', '.join(people_strs)}")

    # Coverage gaps — great for steering the greeting question
    coverage_gaps = await kg.get_coverage_gaps()
    if coverage_gaps:
        gap_items = [
            f"- {g['category']}: {g['coverage_level']} ({g['fact_count']} facts)"
            for g in coverage_gaps[:5]
        ]
        parts.append("Under-explored areas:\n" + "\n".join(gap_items))

    context = "\n\n".join(parts)
    print(f"[greet] Context ({len(context)} chars):\n{context}")
    return context


async def greet() -> str:
    """Generate a personalized greeting based on what we know about the user."""
    user_name = settings.USER_NAME

    context = await _build_greet_context(user_name)

    prompt = GREET_PROMPT.format(
        user_name=user_name,
        today=date.today().isoformat(),
    )

    greeting = await invoke_with_retry(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=context + "\n\nGenerate a warm 1-2 sentence greeting for " + user_name
                         + ". Reference ONE specific current fact if available. End with a question about an under-explored area."
                         + " Speak directly TO them. Output ONLY the greeting text:"),
        ],
        node="greet",
        max_tokens=200,
        thinking_headroom=800,
    )

    print(f"[greet] Generated: {greeting[:120]}...")
    return greeting.strip()
