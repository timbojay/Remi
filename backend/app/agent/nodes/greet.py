"""GREET node: Generates a personalized greeting for a new session."""

from datetime import date

from langchain_core.messages import SystemMessage, HumanMessage

from app.agent.prompts import GREET_PROMPT
from app.db import knowledge_graph as kg
from app.services.llm import invoke_with_retry
from app.config import settings


async def greet() -> str:
    """Generate a personalized greeting based on what we know about the user."""
    user_name = settings.USER_NAME

    # Load biography context
    biography_summary = await kg.get_biography_summary()

    # Load coverage gaps
    coverage_gaps = await kg.get_coverage_gaps()
    gap_text = ""
    if coverage_gaps:
        gap_items = [
            f"- {g['category']}: {g['coverage_level']} ({g['fact_count']} facts)"
            for g in coverage_gaps[:5]
        ]
        gap_text = "Under-explored areas:\n" + "\n".join(gap_items)

    # Build context
    context_parts = []
    if biography_summary:
        context_parts.append(f"What you know about {user_name}:\n{biography_summary}")
    else:
        context_parts.append(f"You don't know anything about {user_name} yet — this is a first conversation.")
    if gap_text:
        context_parts.append(gap_text)

    context = "\n\n".join(context_parts)

    prompt = GREET_PROMPT.format(
        user_name=user_name,
        today=date.today().isoformat(),
    )

    greeting = await invoke_with_retry(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=context),
        ],
        node="greet",
        max_tokens=200,
    )

    print(f"[greet] Generated: {greeting[:80]}...")
    return greeting.strip()
