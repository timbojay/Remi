"""STRATEGIZE node: Decides the agent's approach for this conversation turn.

Fully rule-based — no LLM call. This saves 25-30s per message compared to
the previous LLM-based approach, while producing equivalent strategies.
The respond node's system prompt + focused context handle the actual nuance.
"""

import asyncio
import random
from app.agent.state import BiographerState
from app.db import knowledge_graph as kg
from app.db import vector_store
from langchain_core.messages import HumanMessage


async def strategize(state: BiographerState) -> dict:
    """Decide the conversational strategy for this turn — rule-based, no LLM call."""
    intent = state.get("intent", "sharing")
    mood = state.get("mood", "neutral")

    # Load biography context — cached, only rebuilds when data changes
    biography_summary = await kg.get_biography_summary()

    # Simple intents — immediate return
    if intent in ("greeting", "casual"):
        _TEMPLATE_STRATEGIES = {
            "greeting": "Greet warmly. If there are coverage gaps, steer toward an unexplored area naturally.",
            "casual": "Respond briefly and naturally. Look for an opening to explore biography.",
        }
        print(f"[strategize] Short-circuit for intent={intent} (rule-based)")
        return {
            "strategy": _TEMPLATE_STRATEGIES[intent],
            "biography_summary": biography_summary,
        }

    # Load enrichment data in parallel (fast DB queries, no LLM)
    coverage_gaps, unnamed_people, pending, top_questions = await asyncio.gather(
        kg.get_coverage_gaps(),
        kg.get_unnamed_people(),
        kg.get_pending_verifications(limit=2),
        kg.get_top_questions(limit=2),
    )

    # Build a rule-based strategy from the available data
    strategy_parts = []

    # Core strategy by intent
    if intent == "sharing":
        strategy_parts.append("Acknowledge what they shared warmly, then ask a specific follow-up.")
    elif intent == "correcting":
        strategy_parts.append("Confirm the correction clearly and without defensiveness.")
    elif intent == "asking":
        strategy_parts.append("Answer honestly if you know, admit what you don't know.")
    else:
        strategy_parts.append("Respond naturally to the user's message.")

    # Mood modifier
    _MOOD_HINTS = {
        "emotional": "Be gentle and empathetic — this is sensitive.",
        "frustrated": "Be straightforward, no filler. Acknowledge their frustration briefly.",
        "reflective": "Match their thoughtful tone. Give space for the memory.",
        "enthusiastic": "Share their excitement! Be energetic.",
    }
    if mood in _MOOD_HINTS:
        strategy_parts.append(_MOOD_HINTS[mood])

    # Opportunistic enrichment — pick ONE thing to weave in naturally
    enrichment = None
    if unnamed_people and random.random() < 0.4:
        person = unnamed_people[0]
        enrichment = f"If natural, ask for {person['label']}'s real name."
    elif pending and random.random() < 0.3:
        fact = pending[0]
        enrichment = f"If natural, verify: \"{fact['value'][:60]}\"."
    elif coverage_gaps and random.random() < 0.3:
        gap = coverage_gaps[0]
        enrichment = f"If natural, steer toward {gap['category']} (under-explored)."
    elif top_questions and random.random() < 0.3:
        q = top_questions[0]
        enrichment = f"Consider asking: {q['question_text'][:60]}"

    if enrichment:
        strategy_parts.append(enrichment)

    strategy = " ".join(strategy_parts)
    print(f"[strategize] rule-based strategy: {strategy[:80]}")

    return {
        "strategy": strategy,
        "biography_summary": biography_summary,
    }
