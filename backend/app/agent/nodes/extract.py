"""EXTRACT node: Claude analyzes the conversation and extracts biographical data as structured JSON."""

import json
from app.agent.state import BiographerState
from app.agent.prompts import EXTRACT_PROMPT
from app.agent.tools.mutation_tools import set_conversation_id
from app.db import knowledge_graph as kg
from app.db import vector_store
from app.services.llm import invoke_with_retry
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage


# Era inference from age at the time of a fact
def _infer_era(age: int) -> str:
    if age <= 12:
        return "childhood"
    elif age <= 19:
        return "teenager"
    elif age <= 30:
        return "young_adult"
    elif age <= 60:
        return "adult"
    else:
        return "later_life"


async def _get_birth_year() -> int | None:
    """Try to find the subject's birth year from existing facts."""
    hits = await kg.search_facts("born", category="identity", limit=5)
    for h in hits:
        val = h.get("value", "")
        # Look for a 4-digit year in identity/born facts
        import re
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', val)
        if year_match:
            return int(year_match.group(1))
    # Also check date_year directly on identity facts
    all_identity = await kg.get_all_facts(category="identity")
    for f in all_identity:
        if f.get("date_year") and f.get("predicate", "").lower() in ("born_in", "born_year", "birth_date"):
            return f["date_year"]
    return None


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

    # Build a FOCUSED "Already Recorded" context — only facts/entities relevant
    # to the current message. The full biography (23K+ chars) overwhelms small models.
    import re as _re
    user_text = last_user.content if isinstance(last_user.content, str) else str(last_user.content)

    # Extract search terms from user message
    search_terms = set()
    search_terms.update(_re.findall(r'\b[A-Z][a-z]{2,}\b', user_text))  # proper nouns
    search_terms.update(_re.findall(r'\b(19\d{2}|20\d{2})\b', user_text))  # years
    role_words = _re.findall(
        r'\b(mum|mom|mother|dad|father|brother|sister|wife|husband|son|daughter|'
        r'grandma|grandmother|grandpa|grandfather|uncle|aunt|cousin)\b',
        user_text, _re.IGNORECASE,
    )
    search_terms.update(w.capitalize() for w in role_words)

    # Fetch only relevant existing data
    relevant_facts = []
    relevant_entities = []
    seen_fact_ids = set()
    for term in list(search_terms)[:5]:
        for f in await kg.search_facts(term, limit=5):
            if f["id"] not in seen_fact_ids:
                seen_fact_ids.add(f["id"])
                relevant_facts.append(f)
        for e in await kg.search_entities(term):
            relevant_entities.append(e)

    context = ""
    if relevant_facts or relevant_entities:
        parts = []
        if relevant_entities:
            ent_lines = [f"- {e['name']}: {e.get('description', '')}" for e in relevant_entities[:10]]
            parts.append("Known people/places:\n" + "\n".join(ent_lines))
        if relevant_facts:
            fact_lines = [f"- {f['value']}" for f in relevant_facts[:15]]
            parts.append("Known facts:\n" + "\n".join(fact_lines))
        context = "\n\n## Already Recorded (relevant subset)\n" + "\n\n".join(parts)

    response_text = await invoke_with_retry(
        [
            SystemMessage(content=EXTRACT_PROMPT + "\n\nCRITICAL: You are a data extraction tool. "
                          "Output ONLY a JSON object. Do NOT write conversational text, commentary, "
                          "or anything outside the JSON block. If there is nothing to extract, "
                          'output: {"entities": [], "facts": []}'),
            HumanMessage(content=f"Extract biographical information from this exchange:{context}\n\n---\n{exchange}\n\n"
                         "Respond with ONLY the JSON object now:"),
        ],
        node="extract",
        max_tokens=2048,
        thinking_headroom=400,
    )

    # Parse JSON from response
    data = _parse_json(response_text)
    if not data:
        print(f"[extract] No structured data extracted")
        return {}

    entities = data.get("entities", [])
    facts = data.get("facts", [])
    narratives = data.get("narratives", [])

    print(f"[extract] Parsed {len(entities)} entities, {len(facts)} facts, {len(narratives)} narratives")

    # Era enrichment: if a fact has date_year but no era, infer from birth year
    birth_year = await _get_birth_year()
    for fact in facts:
        if fact.get("year") and not fact.get("era") and birth_year:
            age = fact["year"] - birth_year
            if age >= 0:
                fact["era"] = _infer_era(age)
                print(f"[extract] Inferred era={fact['era']} for year={fact['year']} (age {age})")

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

            # Update description if new one is richer
            new_desc = entity.get("description", "")
            old_desc = existing[0].get("description", "")
            if new_desc and len(new_desc) > len(old_desc) and "unknown" not in new_desc.lower():
                await kg.update_entity(eid, description=new_desc)
                print(f"[extract] Updated description for '{name}': {new_desc[:60]}")

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

    # Singleton predicates where contradictions indicate a conflict (only one value should exist)
    SINGLETON_PREDICATES = {
        "born_in", "born_year", "birth_date", "died_in", "died_year", "death_date",
        "lives_in", "married_to", "birth_place", "death_place",
    }

    # Predicates that auto-flag as anchor facts (life-defining events)
    ANCHOR_PREDICATES = {
        "born_in", "born_year", "died_in", "died_year", "married",
        "graduated", "birth_date", "death_date", "birth_place", "death_place",
    }

    # Persist facts
    for fact in facts:
        value = fact.get("value", "")
        category = fact.get("category", "identity")
        if not value:
            continue

        # Check for duplicate facts — exact match first, then semantic
        existing_facts = await kg.search_facts(value[:50])
        is_duplicate = False
        for ef in existing_facts:
            if ef["value"].lower() == value.lower():
                is_duplicate = True
                await kg.increment_fact_mention(ef["id"])
                print(f"[extract] Fact re-confirmed (exact match, mention++): {value[:60]}")
                break
        if not is_duplicate:
            # Semantic dedup — check embedding similarity
            try:
                similar = await vector_store.find_similar_facts(value, threshold=0.85, limit=3)
                if similar:
                    best = similar[0]
                    is_duplicate = True
                    await kg.increment_fact_mention(best["fact_id"])
                    print(f"[extract] Fact re-confirmed (semantic {best['similarity']:.2f}, mention++): {value[:60]}")
            except Exception as e:
                print(f"[extract] Semantic dedup check failed: {e}")
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

        predicate = fact.get("predicate", "stated")
        confidence = fact.get("confidence", 0.9)

        # Contradiction detection for singleton predicates
        if predicate.lower() in SINGLETON_PREDICATES:
            contradictions = await kg.check_contradictions(
                value, category,
                subject_entity_id=subject_entity_id,
                predicate=predicate,
            )
            if contradictions:
                verified_conflicts = [c for c in contradictions if c.get("is_verified")]
                if verified_conflicts:
                    # Verified fact exists — lower confidence on new fact, don't block it
                    confidence = 0.5
                    print(f"[extract] CONTRADICTION with verified fact: new='{value[:50]}' vs verified='{verified_conflicts[0]['value'][:50]}' — lowering confidence")
                else:
                    print(f"[extract] Possible contradiction with unverified fact: new='{value[:50]}' vs existing='{contradictions[0]['value'][:50]}'")

        # Auto-set is_anchor for life-defining facts
        is_anchor = predicate.lower() in ANCHOR_PREDICATES
        if not is_anchor and category == "milestone" and fact.get("significance", 3) >= 4:
            is_anchor = True

        result = await kg.add_fact(
            value=value,
            category=category,
            predicate=predicate,
            subject_entity_id=subject_entity_id,
            date_year=fact.get("year"),
            date_month=fact.get("month"),
            era=fact.get("era"),
            confidence=confidence,
            significance=fact.get("significance", 3),
            is_anchor=is_anchor,
            conversation_id=conversation_id,
        )
        print(f"[extract] Created fact: {value[:60]} [{result['id'][:8]}]{' [ANCHOR]' if is_anchor else ''}")

        # Index fact in vector store for future semantic dedup
        try:
            await vector_store.index_fact(result["id"], value)
        except Exception as e:
            print(f"[extract] Failed to index fact embedding: {e}")

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

    # Persist narratives — story threads grouping related facts
    for narrative in narratives:
        title = narrative.get("title", "")
        summary = narrative.get("summary", "")
        if not title or not summary:
            continue

        # Resolve related_facts text to actual fact IDs
        related_texts = narrative.get("related_facts", [])
        fact_ids = []
        for fact_text in related_texts:
            hits = await kg.search_facts(fact_text[:50], limit=3)
            for h in hits:
                if h["value"].lower().startswith(fact_text[:30].lower()):
                    fact_ids.append(h["id"])
                    break

        await kg.add_narrative(
            title=title,
            summary=summary,
            fact_ids=fact_ids,
            era=narrative.get("era"),
            conversation_id=conversation_id,
        )
        print(f"[extract] Created narrative: {title}")

    # Check if new facts answer existing questions
    try:
        from app.db.knowledge_graph import get_top_questions, mark_question_answered
        top_questions = await get_top_questions(limit=10)
        for q in top_questions:
            # If we extracted facts in the same category, mark as answered
            for fact in facts:
                if fact.get("category") == q.get("category"):
                    await mark_question_answered(q["id"])
                    print(f"[extract] Question answered: {q['question_text'][:50]}")
                    break
    except Exception as e:
        print(f"[extract] Question check error: {e}")

    # Index new facts in vector store for semantic dedup
    try:
        all_new_facts = await kg.search_facts("", limit=5)  # recent facts
    except Exception:
        pass

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
