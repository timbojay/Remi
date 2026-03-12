"""STRATEGIZE node: Decides the agent's approach for this conversation turn."""

import asyncio
import json
import re
from app.agent.state import BiographerState
from app.agent.prompts import STRATEGIZE_PROMPT
from app.db import knowledge_graph as kg
from app.db import vector_store
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage


async def strategize(state: BiographerState) -> dict:
    """Decide the conversational strategy for this turn based on context."""
    intent = state.get("intent", "sharing")
    mood = state.get("mood", "neutral")
    turn_count = state.get("turn_count", 0)

    # Load biography context — cached, only rebuilds when data changes
    biography_summary = await kg.get_biography_summary()

    # Load coverage gaps and unnamed people in parallel
    coverage_gaps, unnamed_people = await asyncio.gather(
        kg.get_coverage_gaps(),
        kg.get_unnamed_people(),
    )

    gap_text = ""
    if coverage_gaps:
        gap_items = [f"- {g['category']}: {g['coverage_level']} ({g['fact_count']} facts)" for g in coverage_gaps[:5]]
        gap_text = "Under-explored areas:\n" + "\n".join(gap_items)

    unnamed_text = ""
    if unnamed_people:
        u_items = [f"- {u['label']} ({u['family_role']})" for u in unnamed_people]
        unnamed_text = "Unnamed people (ask for their real name):\n" + "\n".join(u_items)

    # Load pending verifications
    pending = await kg.get_pending_verifications(limit=3)
    verify_text = ""
    if pending:
        verify_items = [f"- \"{f['value']}\" (confidence: {f['confidence']})" for f in pending]
        verify_text = "Facts to verify:\n" + "\n".join(verify_items)

    # RAG: retrieve relevant past conversations — skip for short/simple inputs
    user_text = ""
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            user_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    rag_text = ""
    _skip_rag = intent in ("greeting", "casual") or len(user_text.strip()) < 25
    if user_text and not _skip_rag:
        try:
            similar = await vector_store.search_conversations(user_text, limit=3)
            if similar:
                rag_items = [f"- [{h['title'] or 'untitled'}] {h['content'][:150]}..." for h in similar if h['similarity'] > 0.3]
                if rag_items:
                    rag_text = "Relevant past conversations:\n" + "\n".join(rag_items)
        except Exception as e:
            print(f"[strategize] RAG error: {e}")

    # Build context for strategy decision
    context_parts = [
        f"Intent: {intent}",
        f"Mood: {mood}",
        f"Turn: {turn_count}",
    ]
    if biography_summary:
        context_parts.append(f"\nKnown biography:\n{biography_summary}")
    if unnamed_text:
        context_parts.append(f"\n{unnamed_text}")
    if gap_text:
        context_parts.append(f"\n{gap_text}")
    if verify_text:
        context_parts.append(f"\n{verify_text}")
    if rag_text:
        context_parts.append(f"\n{rag_text}")

    context = "\n".join(context_parts)

    result_text = await invoke_with_retry(
        [
            SystemMessage(content=STRATEGIZE_PROMPT),
            HumanMessage(content=context),
        ],
        node="strategize",
        max_tokens=300,
    )

    # Parse JSON result
    data = _parse_strategy_json(result_text)
    if not data:
        strategy = result_text[:200]
        tone = "warm"
    else:
        strategy = data.get("strategy", "Respond naturally to the user's message.")
        tone = data.get("tone", "warm")

    print(f"[strategize] tone={tone} strategy={strategy[:80]}")

    return {
        "strategy": strategy,
        "biography_summary": biography_summary,
    }


def _parse_strategy_json(text: str) -> dict | None:
    """Parse JSON from strategy response."""
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None
