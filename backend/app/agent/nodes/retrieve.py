"""RETRIEVE node: Targeted fact retrieval before the respond step.

Instead of injecting the full biography summary, we look at what entities
and topics are actually mentioned in the current message and fetch only
those facts. This means the LLM gets focused, relevant context — not a
wall of biographical text it can confabulate from.

Pipeline position: after STRATEGIZE, before RESPOND.
"""

import re
from langchain_core.messages import HumanMessage
from app.db import knowledge_graph as kg


# Topic words that signal what the conversation is about
_TOPIC_RE = re.compile(
    r"\b(mother|father|mum|dad|brother|sister|wife|husband|son|daughter|"
    r"child|children|school|college|university|job|work|career|"
    r"born|birth|death|died|marriage|married|house|home|"
    r"grew up|childhood|teenager|teen|young)\b",
    re.IGNORECASE,
)


async def retrieve_focused_context(state: dict) -> str:
    """Return a focused context string for the respond step.

    Priority:
      1. Named entities mentioned in the user's message → fetch their linked facts
      2. Family-role words (mum, dad) → match by family_role column
      3. Topic keyword search → fetch relevant facts
      4. Fallback → full biography_summary from state
    """
    biography_summary = state.get("biography_summary", "")

    # Get the last user message
    user_text = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    if not user_text or len(user_text.strip()) < 5:
        return biography_summary

    user_lower = user_text.lower()

    # ── 1. Match known person entities by name or role ────────────────
    all_people = await kg.get_all_entities(entity_type="person")
    mentioned: list[dict] = []
    seen_ids: set[str] = set()

    for entity in all_people:
        hit = False
        # Name match
        if entity["name"].lower() in user_lower:
            hit = True
        # Family role match (catches "mum", "dad", "mother" etc.)
        role = entity.get("family_role") or ""
        if role and role.lower() in user_lower:
            hit = True
        # Also check role aliases
        role_aliases = {
            "mother": ["mum", "mom", "mother"],
            "father": ["dad", "father", "pop"],
            "sibling": ["brother", "sister"],
        }
        for canonical, aliases in role_aliases.items():
            if role.lower() == canonical and any(a in user_lower for a in aliases):
                hit = True
        if hit and entity["id"] not in seen_ids:
            seen_ids.add(entity["id"])
            mentioned.append(entity)

    # ── 2. Build per-entity fact blocks ──────────────────────────────
    context_parts: list[str] = []
    for entity in mentioned[:3]:  # cap at 3 entities to keep context tight
        facts = await kg.search_facts(entity["name"], limit=5)
        lines = [f"About {entity['name']}:"]
        desc = entity.get("description") or ""
        if desc and "unknown" not in desc.lower():
            lines.append(f"  {desc}")
        for f in facts[:4]:
            lines.append(f"  - {f['value']}")
        if len(lines) > 1:  # only add if we have something beyond the header
            context_parts.append("\n".join(lines))

    if context_parts:
        return "\n\n".join(context_parts)

    # ── 3. Topic-keyword fallback search ─────────────────────────────
    # Proper nouns + topic words from the message
    proper_nouns = re.findall(r"\b[A-Z][a-z]{2,}\b", user_text)
    topic_words = _TOPIC_RE.findall(user_text)
    search_terms = list({t.lower() for t in proper_nouns + topic_words})[:3]

    relevant_facts: list[dict] = []
    seen_fact_ids: set[str] = set()
    for term in search_terms:
        for f in await kg.search_facts(term, limit=4):
            if f["id"] not in seen_fact_ids:
                seen_fact_ids.add(f["id"])
                relevant_facts.append(f)

    if relevant_facts:
        lines = ["Relevant facts:"]
        for f in relevant_facts[:6]:
            lines.append(f"- {f['value']}")
        return "\n".join(lines)

    # ── 4. Final fallback ─────────────────────────────────────────────
    return biography_summary
