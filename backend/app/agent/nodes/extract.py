"""EXTRACT node: Claude analyzes the conversation and extracts biographical data as structured JSON."""

import json
from app.agent.state import BiographerState
from app.agent.prompts import EXTRACT_PROMPT
from app.agent.tools.mutation_tools import set_conversation_id
from app.db import knowledge_graph as kg
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


async def extract(state: BiographerState) -> dict:
    """Run Claude to extract biographical facts, then persist them."""
    conversation_id = state["conversation_id"]
    messages = state.get("messages", [])

    # Set the conversation ID so KG functions can record provenance
    set_conversation_id(conversation_id)

    # Build a compact view of the last exchange
    last_user = None
    last_assistant = None
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and last_assistant is None:
            last_assistant = msg
        elif isinstance(msg, HumanMessage) and last_user is None:
            last_user = msg
        if last_user and last_assistant:
            break

    if not last_user:
        return {}

    exchange = f"User: {last_user.content}"
    if last_assistant:
        content = last_assistant.content if isinstance(last_assistant.content, str) else str(last_assistant.content)
        exchange += f"\nAssistant: {content}"

    # Get existing data context so Claude can avoid duplicates
    existing_summary = await kg.get_biography_summary()
    context = ""
    if existing_summary:
        context = f"\n\n## Already Recorded\n{existing_summary}"

    response_text = await invoke_with_retry(
        [
            SystemMessage(content=EXTRACT_PROMPT),
            HumanMessage(content=f"Extract biographical information from this exchange:{context}\n\n---\n{exchange}"),
        ],
        node="extract",
        max_tokens=2048,
    )

    # Parse JSON from response
    data = _parse_json(response_text)
    if not data:
        print(f"[extract] No structured data extracted")
        return {}

    entities = data.get("entities", [])
    facts = data.get("facts", [])

    print(f"[extract] Parsed {len(entities)} entities, {len(facts)} facts")

    # Create a mapping from temp entity names to real IDs
    entity_id_map: dict[str, str] = {}

    # Persist entities
    for entity in entities:
        name = entity.get("name", "")
        if not name:
            continue

        name_known = entity.get("name_known", True)
        props = {"name_known": name_known}

        # Check if this exact name already exists
        existing = await kg.search_entities(name)
        if existing:
            entity_id_map[name.lower()] = existing[0]["id"]
            print(f"[extract] Entity '{name}' already exists [{existing[0]['id'][:8]}]")
            continue

        # If we now know a real name, check whether there's an unnamed placeholder
        # stored under a role label (e.g. "Mum", "Dad") that should be upgraded.
        if name_known:
            family_role = entity.get("family_role", "")
            if family_role:
                role_candidates = await kg.search_entities(family_role, entity_type="person")
                for candidate in role_candidates:
                    cand_props = candidate.get("properties") or {}
                    if isinstance(cand_props, str):
                        try:
                            cand_props = json.loads(cand_props)
                        except Exception:
                            cand_props = {}
                    if not cand_props.get("name_known", True):
                        # Found an unnamed placeholder — upgrade it with the real name
                        await kg.update_entity(
                            candidate["id"],
                            name=name,
                            description=entity.get("description", candidate.get("description", "")),
                            properties={"name_known": True},
                        )
                        entity_id_map[name.lower()] = candidate["id"]
                        print(f"[extract] Upgraded unnamed entity: {candidate['name']} → {name} [{candidate['id'][:8]}]")
                        break
                else:
                    # No unnamed placeholder found — create fresh
                    result = await kg.add_entity(
                        name=name,
                        entity_type=entity.get("type", "person"),
                        relationship=entity.get("relationship", ""),
                        family_role=family_role,
                        description=entity.get("description", ""),
                        properties=props,
                        conversation_id=conversation_id,
                    )
                    entity_id_map[name.lower()] = result["id"]
                    print(f"[extract] Created entity: {name} (name_known=True) [{result['id'][:8]}]")
                continue  # handled either way

        # Unknown name or no family_role to match — create as-is
        result = await kg.add_entity(
            name=name,
            entity_type=entity.get("type", "person"),
            relationship=entity.get("relationship", ""),
            family_role=entity.get("family_role", ""),
            description=entity.get("description", ""),
            properties=props,
            conversation_id=conversation_id,
        )
        entity_id_map[name.lower()] = result["id"]
        print(f"[extract] Created entity: {name} (name_known={name_known}) [{result['id'][:8]}]")

    # Persist facts
    for fact in facts:
        value = fact.get("value", "")
        category = fact.get("category", "identity")
        if not value:
            continue

        # Check for duplicate facts
        existing_facts = await kg.search_facts(value[:50])
        is_duplicate = False
        for ef in existing_facts:
            if ef["value"].lower() == value.lower():
                is_duplicate = True
                print(f"[extract] Fact already exists: {value[:60]}")
                break
        if is_duplicate:
            continue

        # Resolve subject entity reference
        subject_entity_id = None
        subject_ref = fact.get("subject", "")
        if subject_ref and subject_ref.lower() in entity_id_map:
            subject_entity_id = entity_id_map[subject_ref.lower()]

        result = await kg.add_fact(
            value=value,
            category=category,
            predicate=fact.get("predicate", "stated"),
            subject_entity_id=subject_entity_id,
            date_year=fact.get("year"),
            date_month=fact.get("month"),
            era=fact.get("era"),
            confidence=fact.get("confidence", 0.9),
            significance=fact.get("significance", 3),
            conversation_id=conversation_id,
        )
        print(f"[extract] Created fact: {value[:60]} [{result['id'][:8]}]")

    # Persist relationships
    relationships = data.get("relationships", [])
    for rel in relationships:
        from_name = rel.get("from", "")
        to_name = rel.get("to", "")
        rel_type = rel.get("type", "other")

        from_id = entity_id_map.get(from_name.lower())
        to_id = entity_id_map.get(to_name.lower())

        if from_id and to_id:
            result = await kg.add_relationship(
                from_entity_id=from_id,
                to_entity_id=to_id,
                relationship_type=rel_type,
                is_bidirectional=rel.get("bidirectional", False),
                confidence=0.9,
                conversation_id=conversation_id,
            )
            if result.get("already_exists"):
                print(f"[extract] Relationship {from_name}→{to_name} already exists")
            else:
                print(f"[extract] Created relationship: {from_name} --{rel_type}--> {to_name}")
        else:
            print(f"[extract] Skipped relationship {from_name}→{to_name}: entity IDs not found")

    return {}


def _parse_json(text: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown fences."""
    # Try to find JSON block in markdown fences
    import re
    json_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try parsing the whole response as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try finding a JSON object in the text
    brace_match = re.search(r'\{.*\}', text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    print(f"[extract] Failed to parse JSON from: {text[:200]}")
    return None
