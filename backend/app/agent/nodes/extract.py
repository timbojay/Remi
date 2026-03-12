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
            eid = existing[0]["id"]
            entity_id_map[name.lower()] = eid
            # Increment mention count — tracks how often this person comes up
            await kg.increment_entity_mention(eid)
            print(f"[extract] Entity '{name}' re-mentioned [{eid[:8]}]")
            continue

        # If we now know a real name, look for an unnamed placeholder to upgrade.
        # Search by family_role column (not name text) so "Mum" is found when
        # family_role="mother" — the previous approach searched name LIKE "%mother%"
        # which never matched "Mum".
        if name_known:
            family_role = entity.get("family_role", "")
            placeholder = await kg.find_unnamed_entity_by_role(family_role) if family_role else None
            if placeholder:
                await kg.update_entity(
                    placeholder["id"],
                    name=name,
                    description=entity.get("description", placeholder.get("description", "")),
                    properties={"name_known": True},
                )
                entity_id_map[name.lower()] = placeholder["id"]
                print(f"[extract] Upgraded unnamed entity: {placeholder['name']} → {name} [{placeholder['id'][:8]}]")
            else:
                # No unnamed placeholder — create fresh
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
                # Increment mention count — this fact has been confirmed again
                await kg.increment_fact_mention(ef["id"])
                print(f"[extract] Fact re-confirmed (mention++): {value[:60]}")
                break
        if is_duplicate:
            continue

        # Resolve subject entity — check map first, then fall back to DB
        subject_entity_id = None
        subject_ref = fact.get("subject", "")
        if subject_ref:
            subject_entity_id = entity_id_map.get(subject_ref.lower())
            if not subject_entity_id:
                hits = await kg.search_entities(subject_ref)
                if hits:
                    subject_entity_id = hits[0]["id"]
                    entity_id_map[subject_ref.lower()] = subject_entity_id

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
    # entity_id_map only contains entities from THIS extraction run.
    # For cross-session relationships (e.g. Beryl introduced session 1,
    # her mother Elizabeth in session 3), we fall back to a DB name lookup
    # so the family graph doesn't silently drop inter-session edges.
    relationships = data.get("relationships", [])
    for rel in relationships:
        from_name = rel.get("from", "")
        to_name = rel.get("to", "")
        rel_type = rel.get("type", "other")

        from_id = entity_id_map.get(from_name.lower())
        to_id = entity_id_map.get(to_name.lower())

        # Cross-session fallback: look up by name in the DB
        if not from_id and from_name:
            hits = await kg.search_entities(from_name, entity_type="person")
            if hits:
                from_id = hits[0]["id"]
                entity_id_map[from_name.lower()] = from_id
                print(f"[extract] Resolved '{from_name}' from DB for relationship [{from_id[:8]}]")

        if not to_id and to_name:
            hits = await kg.search_entities(to_name, entity_type="person")
            if hits:
                to_id = hits[0]["id"]
                entity_id_map[to_name.lower()] = to_id
                print(f"[extract] Resolved '{to_name}' from DB for relationship [{to_id[:8]}]")

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
            print(f"[extract] Skipped relationship {from_name}→{to_name}: could not resolve entity IDs")

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
