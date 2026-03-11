"""
rag.py — Enhanced RAG retrieval using the FamilyTree graph model.

Replaces the old keyword-matching RAG with graph-aware context fetching.
The FamilyTree is used directly (same process) for efficiency.
For external clients, use the MCP server instead.
"""

from remi.family_tree import FamilyTree, BIOGRAPHY_FILE

# Topic detection keywords (carried over from v1, used for focused retrieval)
TOPIC_KEYWORDS = {
    "family": ["family", "parent", "mother", "father", "sibling", "brother", "sister",
               "spouse", "partner", "wife", "husband", "child", "children", "son",
               "daughter", "grandparent", "grandmother", "grandfather", "relative",
               "cousin", "uncle", "aunt", "married", "wedding"],
    "places": ["place", "live", "lived", "born", "grew up", "moved", "home", "city",
               "town", "country", "location", "where", "travel"],
    "education": ["school", "university", "college", "study", "studied", "degree",
                  "qualification", "graduate", "education", "learn", "course", "teacher"],
    "career": ["work", "job", "career", "employer", "company", "role", "profession",
               "occupation", "business", "employed", "retire", "salary", "boss"],
    "milestones": ["milestone", "important", "significant", "event", "happened", "memory",
                   "moment", "landmark", "turning point", "first time", "achievement",
                   "remember", "big moment"],
    "interests": ["hobby", "interest", "enjoy", "passion", "like", "love", "sport",
                  "music", "book", "film", "travel", "pastime", "fun"],
    "memories": ["remember", "story", "anecdote", "tell me about", "what was it like",
                 "describe", "recall", "once upon"],
}


def _detect_topics(text: str) -> list[str]:
    """Detect which topics are relevant to a piece of text."""
    text_lower = text.lower()
    matched = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matched.append(topic)
    return matched if matched else None  # None = include everything


def _detect_person(text: str, tree: FamilyTree) -> str | None:
    """Try to detect if the text mentions a specific person in the tree."""
    text_lower = text.lower()
    for pid, person in tree.data["people"].items():
        name = (person.get("name") or "").lower()
        preferred = (person.get("preferred_name") or "").lower()
        # Check if a name appears in the text
        if (name and len(name) > 2 and name in text_lower) or \
           (preferred and len(preferred) > 2 and preferred in text_lower):
            return pid
    return None


def retrieve(query: str, tree: FamilyTree = None) -> str:
    """
    Given a conversational turn, retrieve relevant biographical context.

    Returns a formatted string ready for prompt injection.
    """
    if tree is None:
        try:
            tree = FamilyTree()
        except (FileNotFoundError, ValueError):
            return ""

    topics = _detect_topics(query)
    person_id = _detect_person(query, tree)

    # Default to the subject
    if person_id is None:
        person_id = tree.data["_meta"].get("subject_id")

    if not person_id:
        return ""

    return tree.format_context(person_id, topics)


def retrieve_all(tree: FamilyTree = None) -> str:
    """Retrieve the full biography context for session start."""
    if tree is None:
        try:
            tree = FamilyTree()
        except (FileNotFoundError, ValueError):
            return ""

    subject_id = tree.data["_meta"].get("subject_id")
    if not subject_id:
        return ""

    # Full context for the subject (no topic filter)
    context = tree.format_context(subject_id)

    # Also append a brief family tree overview
    people = tree.list_people()
    if len(people) > 1:
        context += "\n\n[FAMILY TREE OVERVIEW]\n"
        context += f"  Total people recorded: {len(people)}\n"
        context += f"  Total relationships: {len(tree.data.get('relationships', []))}\n"
        for p in people:
            marker = " ← subject" if p["id"] == subject_id else ""
            name = p.get("preferred_name") or p.get("name") or p["id"]
            context += f"  • {name} (id: {p['id']}){marker}\n"

    return context
