"""CORRECT node: Handles user corrections to previously recorded facts/entities."""

import json
from app.agent.state import BiographerState
from app.agent.prompts import CORRECT_PROMPT
from app.db import knowledge_graph as kg
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage


async def correct(state: BiographerState) -> dict:
    """Search for incorrect facts and apply corrections based on user's message."""
    messages = state.get("messages", [])

    # Get the last user message
    last_user = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            last_user = msg
            break
    if not last_user:
        return {}

    user_text = last_user.content if isinstance(last_user.content, str) else str(last_user.content)

    # Load all current facts and entities for context
    all_facts = await kg.get_all_facts()
    all_entities = await kg.get_all_entities()

    if not all_facts and not all_entities:
        print("[correct] No existing data to correct")
        return {}

    # Build data context
    facts_text = "\n".join(
        f"  [{f['id'][:8]}] {f['value']} (category: {f['category']}, confidence: {f['confidence']}, verified: {bool(f.get('is_verified'))})"
        for f in all_facts
    )
    entities_text = "\n".join(
        f"  [{e['id'][:8]}] {e['name']} ({e['entity_type']}) — {e.get('description', '')}"
        for e in all_entities
    )

    context = f"User's message: {user_text}\n\nExisting facts:\n{facts_text}\n\nExisting entities:\n{entities_text}"

    result_text = await invoke_with_retry(
        [
            SystemMessage(content=CORRECT_PROMPT),
            HumanMessage(content=context),
        ],
        node="correct",
        max_tokens=1024,
    )

    data = _parse_json(result_text)

    if not data:
        print("[correct] Failed to parse correction response")
        return {}

    corrections = data.get("corrections", [])
    if not corrections:
        print("[correct] No corrections needed")
        return {}

    print(f"[correct] Applying {len(corrections)} correction(s)")

    for correction in corrections:
        action = correction.get("action", "")
        target_id = correction.get("id", "")
        target_type = correction.get("type", "fact")

        if action == "update" and target_type == "fact":
            new_value = correction.get("new_value")
            if new_value and target_id:
                await kg.update_fact(target_id, value=new_value)
                print(f"[correct] Updated fact [{target_id[:8]}] → {new_value[:60]}")

        elif action == "delete" and target_type == "fact":
            if target_id:
                await kg.delete_fact(target_id, reason=correction.get("reason", "User correction"))
                print(f"[correct] Deleted fact [{target_id[:8]}]")

        elif action == "update" and target_type == "entity":
            entity_id = target_id
            updates = {}
            if correction.get("new_name"):
                updates["name"] = correction["new_name"]
            if correction.get("new_description"):
                updates["description"] = correction["new_description"]
            if updates:
                await kg.update_entity(entity_id, **updates)
                print(f"[correct] Updated entity [{entity_id[:8]}]")

        elif action == "delete" and target_type == "entity":
            if target_id:
                await kg.delete_entity(target_id, reason=correction.get("reason", "User correction"))
                print(f"[correct] Deleted entity [{target_id[:8]}]")

    return {}


def _parse_json(text: str) -> dict | None:
    """Parse JSON from correction response."""
    import re
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
